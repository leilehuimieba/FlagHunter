"""LLM-differentiating fixture: a flag reachable only by an *inferred* path.

The landing page links to an extensionless export archive
(``/exports/<archive id>``) and states that exports are served as ``.txt``
files. The flag does not live at that link — it lives at the *constructed* path
``/exports/<archive id>.txt``. Recon surfaces the link into the agent's
ExplorationAgenda (so the archive id reaches the planner on the very first LLM
turn), but nothing serves the flag until the planner *infers* the ``.txt``
sibling of the advertised archive path. A capable model reads the id off the
agenda and builds the URL on its first action; a weak model fetches a literal
guess (or gives up) and fails. This is what lets the model matrix actually
discriminate between models (the deterministic dispatcher, with ``llm=None``,
never builds the path and honestly returns no flag).

Exposed as a plain generator (yields once) so the benchmark runner can drive it
through ``_fixture_server`` exactly like the integration fixtures' ``.__wrapped__``.
"""

from __future__ import annotations

import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator
from urllib.parse import urlparse

FLAG_VALUE = "flag{llm_inferred_export_path}"
ARCHIVE_ID = "7f3a"
ARCHIVE_PATH = f"/exports/{ARCHIVE_ID}"
FLAG_PATH = f"/exports/{ARCHIVE_ID}.txt"


def llm_inferred_path_server() -> Iterator[dict[str, Any]]:
    """Spin a deterministic server whose flag sits at an inferred export path."""
    recorded: list[dict[str, Any]] = []

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            pass

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            recorded.append({"method": "GET", "path": parsed.path, "query": parsed.query})

            if parsed.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    (
                        "<html><body>"
                        "<h1>export portal</h1>"
                        "<p>no forms, no upload, no backup, no standard challenge shape</p>"
                        f'<a href="{ARCHIVE_PATH}">your export archive</a>'
                        "<p>exports are served as .txt files</p>"
                        "</body></html>"
                    ).encode("utf-8")
                )
                return

            if parsed.path == FLAG_PATH:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(FLAG_VALUE.encode("utf-8"))
                return

            # The advertised archive path itself does not serve the flag — only
            # its inferred ``.txt`` sibling does.
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{server.server_port}"
    for _ in range(20):
        try:
            with urllib.request.urlopen(base_url, timeout=2):
                break
        except Exception:
            continue

    try:
        yield {"base_url": base_url, "requests": recorded}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
