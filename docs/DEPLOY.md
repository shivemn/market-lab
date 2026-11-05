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
- The disk is wiped on every restart, so practice accounts and the saved history disappear then. That is fine for a
  demo. To keep them, attach a disk at `/data` (a paid feature on Render).

## Option 2: any machine with Docker

```
docker build -t market-lab .
docker run -p 8000:8000 -v marketlab-data:/data market-lab
```

Open http://localhost:8000. The named volume keeps `practice.db` between runs.

## Before you share the link

- There is no login. Anyone who types an account name uses that account, so treat a public copy as a shared demo and
  do not put anything personal in it.
- Everything is simulated and says so on every screen. Keep that wording if you change the text.
- Run `curl https://your-address/api/health`: it should answer `{"status":"ok"}`.
