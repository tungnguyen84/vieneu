"""Desktop Application Launcher for Sau Cánh Cửa Studio."""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import uvicorn


def start_api_server(host: str = "127.0.0.1", port: int = 8765):
    """Starts FastAPI uvicorn server."""
    uvicorn.run("studio.backend.server:app", host=host, port=port, log_level="warning")


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description="Sau Cánh Cửa Studio — Desktop Production Pipeline")
    parser.add_argument("--port", type=int, default=8765, help="Port to run backend on")
    parser.add_argument("--browser", action="store_true", help="Launch in default browser instead of native desktop window")
    parser.add_argument("--headless", action="store_true", help="Run server only without opening UI window")
    args = parser.parse_args()

    port = args.port
    app_url = f"http://127.0.0.1:{port}"

    # Start server in daemon thread
    server_thread = threading.Thread(target=start_api_server, kwargs={"port": port}, daemon=True)
    server_thread.start()
    print(f"Sau Cánh Cửa Studio Backend running at {app_url}")
    time.sleep(1.2)

    if args.headless:
        print("Running in headless mode. Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down.")
            sys.exit(0)

    # Check for pywebview native window
    has_webview = False
    if not args.browser:
        try:
            import webview
            has_webview = True
        except ImportError:
            has_webview = False

    if has_webview:
        print("Launching Sau Cánh Cửa Studio Desktop Window...")
        import webview
        window = webview.create_window(
            title="Sau Cánh Cửa Studio — Desktop Production Pipeline",
            url=app_url,
            width=1600,
            height=960,
            min_size=(1280, 720),
            background_color="#0B0F17"
        )
        webview.start()
    else:
        print(f"Opening in browser: {app_url}")
        webbrowser.open(app_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down.")
            sys.exit(0)


if __name__ == "__main__":
    main()
