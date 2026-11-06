"""Start the real server for a load test, with the live-day limit set by --cap so many users can play at once.

    python tools/serve_for_loadtest.py --db load.db --port 8100 --cap 5000

The cap (MAX_WORLDS_KEPT in marketlab/api/app.py) is a safety limit on days held in memory.
It was 4 until the first load test; now 500, and days idle for 30 minutes are let go.
"""

from __future__ import annotations

import argparse

import uvicorn

from marketlab.api import app as app_module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="load.db")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument(
        "--cap", type=int, default=500, help="how many live days the server keeps (default: as shipped, 500)"
    )
    args = parser.parse_args()
    app_module.MAX_WORLDS_KEPT = args.cap
    uvicorn.run(app_module.create_app(None, args.db), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
