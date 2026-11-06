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

## Before you share the link

- Sign-in is on: people pick a username and a word-and-number secret, or play as a guest. It is light on purpose (no
  email, no recovery). Say so to anyone you send the link to, and do not put anything personal in it.
- Everything is simulated and says so on every screen. Keep that wording if you change the text.
- Run `curl https://your-address/api/health`: it should answer `{"status":"ok"}`.
