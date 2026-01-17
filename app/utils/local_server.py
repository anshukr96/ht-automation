import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

_SERVER_STARTED = False
_SERVER_URL: Optional[str] = None


def ensure_asset_server(asset_dir: Path) -> None:
    global _SERVER_STARTED, _SERVER_URL
    if _SERVER_STARTED:
        return
    if os.getenv("LOCAL_ASSET_SERVER", "1").lower() not in {"1", "true", "yes"}:
        return
    if not asset_dir.exists():
        return

    port = int(os.getenv("LOCAL_ASSET_PORT", "8777"))
    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=str(asset_dir), **kwargs
    )
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _SERVER_STARTED = True
    _SERVER_URL = f"http://localhost:{port}"


def get_asset_url(filename: str) -> Optional[str]:
    if not _SERVER_URL:
        return None
    return f"{_SERVER_URL}/{filename}"
