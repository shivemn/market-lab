# Putting Market Lab online

The app is one process: the Python server also serves the built web page, so there is one thing to host.

## Option 1: Render for the app, Neon for the database (free, about 20 minutes)

The app needs a database that outlives restarts, and a free Render web service has none: its disk is wiped on every
restart. So the accounts and history go in a free PostgreSQL database on Neon, and Render runs the app. (Render's own
free PostgreSQL is deleted 30 days after it is created, so it is a poor fit.)

1. **Push the repository to GitHub.**
2. **Make the database.** On neon.com sign up, create a project, and pick the region nearest your visitors. On the
   project's Connect panel, **turn connection pooling off** and copy the connection string (it starts with
   `postgresql://` and contains a password). Use the direct one, not the pooled one: the app takes a PostgreSQL
   advisory lock when it migrates and uses prepared statements, and a transaction pooler does not support those.
3. **Make the web service.** On render.com choose **New > Blueprint** and pick the repository. `render.yaml` and the
   `Dockerfile` do the rest. Render asks for the value of `DATABASE_URL`: paste the Neon string there. It lives only in
   Render's settings, never in the repository.
4. When the build finishes you get an address like `https://market-lab.onrender.com`. Put it at the top of the README.

Things to know about the free plans (as of November 2026; check the current terms, they change):
- **Render web service:** sleeps after about 15 minutes without visits and takes about a minute to wake. Open it once
  before you show it to anyone. There are 750 free instance hours a month.
- **Neon:** the database server pauses after 5 minutes without activity and wakes in about a second on the next
  query. The app reopens its database connection by itself when that happens. The free plan has 1 GB of storage per
  project and a monthly allowance of compute hours.
- A practice day in progress lives in the server's memory, so a restart or sleep loses a day half played. Accounts,
  money and finished days are in the database and survive.

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
current terms. The database must use UTF-8 encoding, which hosted ones do by default. If the database drops the connection while
the app is idle, the app opens a new one by itself (inside a transaction it cannot, and that request fails and is undone).

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
