"""Fixture-only callback receiver; loopback, bounded memory, no domain persistence."""

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Lock

from akay_convert_to_markdown.contracts.events import idempotency_key, parse_event
from akay_convert_to_markdown.errors.exceptions import InvalidMessageError

MAX_BODY_BYTES = 1024 * 1024


class CallbackInbox:
    """Transport example only. Restarting forgets receipts; never approves content."""

    def __init__(self, api_key, *, fail_after_accept=False, max_events=1000):
        if not isinstance(api_key, str) or not api_key.strip() or max_events < 1:
            raise ValueError("An explicit nonblank fixture key and positive capacity are required.")
        self._key = api_key
        self._events = {}
        self._lock = Lock()
        self._fail = fail_after_accept
        self._max_events = max_events
        self.deliveries = 0

    @property
    def events(self):
        with self._lock:
            return [json.loads(value) for value in self._events.values()]

    def lose_next_acknowledgement(self):
        with self._lock:
            self._fail = True

    def accept(self, raw, api_key, key):
        if not hmac.compare_digest(str(api_key).encode(), self._key.encode()):
            return 401
        if len(raw) > MAX_BODY_BYTES:
            return 413
        try:
            event = parse_event(raw)
            if key != idempotency_key(event):
                return 400
            value = json.dumps(event.model_dump(mode="json", by_alias=True), sort_keys=True, allow_nan=False)
        except (InvalidMessageError, ValueError, TypeError):
            return 400
        with self._lock:
            self.deliveries += 1
            previous = self._events.get(key)
            if previous is not None:
                return 200 if previous == value else 409
            if len(self._events) >= self._max_events:
                return 503
            self._events[key] = value
            if self._fail:
                self._fail = False
                return 503  # Simulate an accepted event with a lost acknowledgement.
        return 200


def create_server(inbox, *, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.connection.settimeout(5)
            status = 400
            if self.path != "/callbacks":
                status = 404
            elif self.headers.get("Transfer-Encoding") is None:
                lengths = self.headers.get_all("Content-Length", [])
                try:
                    size = int(lengths[0]) if len(lengths) == 1 else -1
                    if size > MAX_BODY_BYTES:
                        status = 413
                    elif size >= 0:
                        raw = self.rfile.read(size)
                        if len(raw) == size:
                            status = inbox.accept(raw, self.headers.get("X-Api-Key", ""),
                                                  self.headers.get("Idempotency-Key", ""))
                except (ValueError, OSError):
                    pass
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.close_connection = True

        def log_message(self, *args):
            pass  # Never print callback bodies, keys, URLs or request headers.

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", required=True, help="Explicit synthetic local key, never a production credential")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--fail-after-accept", action="store_true")
    args = parser.parse_args()
    inbox = CallbackInbox(args.api_key, fail_after_accept=args.fail_after_accept)
    with create_server(inbox, port=args.port) as server:
        print(f"Fixture callbacks: http://127.0.0.1:{server.server_port}/callbacks", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    print(f"Accepted {len(inbox.events)} unique fixture events; {inbox.deliveries} validated deliveries.")


if __name__ == "__main__":
    main()
