"""Start the real server for a load test, with the 4-day memory cap lifted so many users can play at once.

    python tools/serve_for_loadtest.py --db load.db --port 8100 --cap 1000

The cap (MAX_WORLDS_KEPT in marketlab/api/app.py) is a safety limit for a laptop. Leaving it at 4 shows
the first limit a crowd would hit; raising it shows the next one. Nothing else is changed.
"""

from __future__ import annotations

import argparse

import uvicorn

from marketlab.api import app as app_module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="load.db")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--cap", type=int, default=4, help="how many live days the server keeps (default: as shipped)")
    args = parser.parse_args()
    app_module.MAX_WORLDS_KEPT = args.cap
    uvicorn.run(app_module.create_app(None, args.db), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
