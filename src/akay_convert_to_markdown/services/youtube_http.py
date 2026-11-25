"""Restricted HTTPS for extractor metadata and direct audio; no ambient proxies.

Resolve every hop once, reject any non-public answer, then connect to that exact
numeric address while retaining the original TLS hostname/certificate check.
"""

from contextlib import contextmanager
import http.client
import ipaddress
from pathlib import Path
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

from akay_convert_to_markdown.errors.exceptions import DocumentTooLargeError, PermanentError, TransientError


class YouTubeError(PermanentError):
    code = "YOUTUBE_SOURCE_UNAVAILABLE"


class YouTubeTransientError(TransientError):
    code = "YOUTUBE_TEMPORARILY_UNAVAILABLE"


def destination(value: str):
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if (url.scheme != "https" or url.username is not None or url.password is not None
                or url.port not in (None, 443) or url.fragment or re.search(r"[\s\\\x00-\x1f\x7f]", value)
                or not (host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtubei.googleapis.com"}
                        or re.fullmatch(r"[a-z0-9-]+\.googlevideo\.com", host))):
            raise ValueError
        return url
    except ValueError:
        raise YouTubeError("The YouTube network destination is not allowed.", code="YOUTUBE_UNSAFE_DESTINATION") from None


def _connect(host: str, address: str, timeout: float):
    connection = http.client.HTTPSConnection(host, timeout=timeout, context=ssl.create_default_context())
    # http.client otherwise performs a second DNS lookup inside connect().
    raw = socket.create_connection((address, 443), timeout=timeout)
    try:
        connection.sock = connection._context.wrap_socket(raw, server_hostname=host)
    except BaseException:
        raw.close()
        raise
    return connection


def _public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address):
        # Reject IPv4 transition mechanisms rather than trusting the enclosing
        # global IPv6 prefix to prove the embedded destination is public.
        if (address.ipv4_mapped is not None or address.sixtofour is not None or address.teredo is not None
                or address in ipaddress.IPv6Network("64:ff9b::/96")
                or address in ipaddress.IPv6Network("64:ff9b:1::/48")):
            return False
    return address.is_global and not address.is_multicast and not address.is_reserved


class YouTubeHTTP:
    def __init__(self, *, max_bytes: int, timeout: float, resolver=socket.getaddrinfo, connector=_connect):
        self.max_bytes = max_bytes
        self.deadline = time.monotonic() + timeout
        self._resolve, self._connect = resolver, connector
        self._requests = 0
        self._metadata_bytes = 0
        # yt-dlp may suppress a failed optional fetch; retain security/transient failures.
        self.failure = None

    def _remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise YouTubeError("YouTube retrieval exceeded its time budget.", code="PROCESSING_TIMEOUT")
        return min(10, remaining)

    @contextmanager
    def _open(self, value, *, method="GET", data=None, headers=None):
        connection = response = None
        try:
            if method not in {"GET", "POST", "HEAD"} or (data is not None and (not isinstance(data, bytes) or len(data) > 1024 * 1024)):
                raise YouTubeError("The extractor request is unsupported.")
            allowed = {"user-agent", "accept", "accept-language", "content-type", "origin",
                       "x-youtube-client-name", "x-youtube-client-version", "x-goog-visitor-id"}
            safe_headers = {key: val for key, val in (headers or {}).items() if key.lower() in allowed}
            safe_headers.update({"Accept-Encoding": "identity", "Connection": "close"})
            for hop in range(5):
                url = destination(value)
                self._requests += 1
                if self._requests > 64:
                    raise YouTubeError("The extractor request budget was exceeded.")
                answers = self._resolve(url.hostname, 443, type=socket.SOCK_STREAM)
                addresses = [entry[4][0] for entry in answers]
                if not addresses or not all(_public_address(ip) for ip in addresses):
                    raise YouTubeError("The YouTube network destination is not public.", code="YOUTUBE_UNSAFE_DESTINATION")
                connection = self._connect(url.hostname, addresses[0], self._remaining())
                connection.request(method, url.path + ("?" + url.query if url.query else "") or "/",
                                   body=data, headers=safe_headers)
                response = connection.getresponse()
                if response.status not in {301, 302, 303, 307, 308}:
                    break
                location = response.getheader("Location")
                if not location or hop == 4:
                    raise YouTubeError("The YouTube redirect limit was exceeded.")
                value = urljoin(value, location)
                if response.status == 303 or (response.status in {301, 302} and method == "POST"):
                    method, data = "GET", None
                response.close()
                connection.close()
            if response.status == 429 or response.status >= 500:
                raise YouTubeTransientError("YouTube is temporarily unavailable.")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise YouTubeError("The YouTube response encoding is unsupported.")
            yield response, value
        except (PermanentError, TransientError) as exc:
            self.failure = exc
            raise
        except (OSError, http.client.HTTPException, ValueError):
            self.failure = YouTubeTransientError("YouTube retrieval failed temporarily.")
            raise self.failure from None
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                connection.close()

    def metadata(self, value, **kwargs):
        with self._open(value, **kwargs) as (response, final_url):
            parts, size = [], 0
            while block := response.read(65536):
                self._remaining()
                size += len(block)
                self._metadata_bytes += len(block)
                if size > 8 * 1024 * 1024 or self._metadata_bytes > 16 * 1024 * 1024:
                    raise YouTubeError("The YouTube metadata budget was exceeded.")
                parts.append(block)
            return b"".join(parts), final_url, dict(response.headers), response.status

    def download(self, value: str, path: Path):
        try:
            with self._open(value) as (response, _):
                if response.status != 200:
                    raise YouTubeError("The YouTube audio is unavailable.")
                length = response.getheader("Content-Length")
                expected = None if length is None else int(length)
                if expected is not None and (expected < 0 or expected > self.max_bytes):
                    raise DocumentTooLargeError("The downloaded audio exceeds the configured size limit.")
                size = 0
                with path.open("xb") as stream:
                    while block := response.read(min(65536, self.max_bytes - size + 1)):
                        self._remaining()
                        size += len(block)
                        if size > self.max_bytes:
                            raise DocumentTooLargeError("The downloaded audio exceeds the configured size limit.")
                        stream.write(block)
                if not size or (expected is not None and size != expected):
                    raise YouTubeTransientError("The YouTube audio download was incomplete.")
        except BaseException:
            path.unlink(missing_ok=True)
            raise
