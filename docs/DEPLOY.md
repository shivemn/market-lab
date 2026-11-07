# Putting Market Lab online

The app is one process: the Python server also serves the built web page, so there is one thing to host.

## Option 1: Render (free, about five minutes)

1. Push the repository to GitHub.
2. On render.com choose **New > Blueprint**, pick the repository. `render.yaml` and the `Dockerfile` do the rest.
3. When the build finishes you get a public address like `https://market-lab.onrender.com`. Put it at the top of the
   README.

Things to know about the free plan:
- The service sleeps after about 15 minutes without visits and takes around 30 seconds to wake. Open it once before
  you show it to anyone.
- The disk is wiped on every restart, so **accounts**, practice money and the saved history disappear then, and everyone
  has to sign up again. That is fine for a demo. To keep them, attach a disk at `/data` (a paid feature on Render).

## Option 2: any machine with Docker

```
docker build -t market-lab .
docker run -p 8000:8000 -v marketlab-data:/data market-lab
```

Open http://localhost:8000. The named volume keeps `practice.db` between runs.
The container starts the server with `--behind-proxy`, so the attempt limits see each visitor's own address. Use that
flag only when a proxy such as Render's or nginx sits in front; run directly on the internet it lets visitors fake
their address.

## Keeping accounts between restarts: a PostgreSQL database

A free web service forgets its disk when it restarts. To keep accounts, money and history, give the app a PostgreSQL
database: set the environment variable `DATABASE_URL` to its `postgresql://...` address (in Render, under the service's
Environment settings, never in the repository, because the address contains a password). The container uses it
automatically; if it is not set it falls back to the file in `/data`. Several hosting companies offer a free PostgreSQL
tier (for example Neon and Supabase, and Render has its own); free tiers change and some expire or pause, so check the
current terms. The database must use UTF-8 encoding, which hosted ones do by default.

Locally, the same works with `marketlab serve --db postgresql://user:password@localhost/marketlab` after
`pip install -e ".[api,postgres]"`. The tables are created on first start.

## Several worker processes

```
marketlab cluster --workers 4 --db postgresql://user:password@host/database
```

This starts four server processes and a router on the public port; the workers use the next ports up. It needs
PostgreSQL (SQLite is one file for one program) and is only worth it on a machine with spare cores: on a single shared
CPU, which is what free plans give, it adds overhead and nothing else (see `docs/LOADTEST.md`). The router must be the
only thing reachable from outside; the workers listen on the local address only. If a proxy such as Render's sits in
front, add `--behind-proxy`. The Dockerfile starts a single `marketlab serve`; to use the cluster there, change its last
line to `marketlab cluster --host 0.0.0.0 --port ${PORT} --behind-proxy` with `DATABASE_URL` set.

## Before you share the link

- Sign-in is on: people pick a username and a word-and-number secret, or play as a guest. It is light on purpose (no
  email, no recovery). Say so to anyone you send the link to, and do not put anything personal in it.
- Everything is simulated and says so on every screen. Keep that wording if you change the text.
- Run `curl https://your-address/api/health`: it should answer `{"status":"ok"}`.
