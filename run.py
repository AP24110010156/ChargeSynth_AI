"""Local launcher. The demo binds to your own computer by default."""
import argparse
import os
import threading
import webbrowser
from backend.app import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local ChargeSynth web application.")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "5000")))
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--strictPort", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    port = args.port
    host = args.host
    url = f"http://127.0.0.1:{port}"
    print(f"\nChargeSynth AI is starting at {url}\nPress Ctrl+C to stop.\n", flush=True)
    if os.getenv("OPEN_BROWSER", "1") == "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False, use_reloader=False)
