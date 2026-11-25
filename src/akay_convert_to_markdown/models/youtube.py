"""One supported video URL policy, shared by wire validation and extraction."""

import re
from urllib.parse import parse_qs, urlsplit


def video_identity(value: str) -> tuple[str, str]:
    error = "An individual HTTPS YouTube video URL is required."
    if len(value) > 2048 or re.search(r"[\s\\%\x00-\x1f\x7f]", value):
        raise ValueError(error)
    url = urlsplit(value)
    if (url.scheme != "https" or url.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
            or url.username is not None or url.password is not None or url.port not in (None, 443) or url.fragment):
        raise ValueError(error)
    query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
    if any(len(values) != 1 for values in query.values()) or set(query) - {"v", "t", "si", "feature"}:
        raise ValueError(error)
    if url.hostname == "youtu.be" and "v" not in query:
        identity = url.path[1:]
    elif url.path == "/watch":
        identity = query.get("v", [""])[0]
    elif url.path.startswith("/shorts/") and "v" not in query:
        identity = url.path[len("/shorts/"):]
    else:
        raise ValueError(error)
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", identity):
        raise ValueError(error)
    return identity, f"https://www.youtube.com/watch?v={identity}"
