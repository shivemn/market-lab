# Recording the demo (about 60 seconds)

A short screen recording is the fastest way for someone to understand the project. Aim for 45 to 75 seconds, no
voice-over needed, with the browser window at about 1280 x 800.

## Before you record

```
cd C:\Projects\market-lab
.\.venv\Scripts\Activate.ps1
Remove-Item practice.db -ErrorAction SilentlyContinue   # start with a fresh ₹1,00,000
marketlab run --seed 7 --out runs\demo.jsonl           # only needed for the optional last shot
marketlab serve --db practice.db
```

Open http://127.0.0.1:8000, close other tabs, and turn on a light theme with a large browser zoom (125%) so the text
is readable when the video is small.

## Recording on Windows

Press **Win + G** to open the Xbox Game Bar, then the record button (or **Win + Alt + R** to start and stop). The
file lands in `Videos\Captures`. To make a GIF for the README, ScreenToGif (free) works well; keep it under 10 MB.

## Shot list

| Seconds | What is on screen | What to do |
|---|---|---|
| 0 to 8 | The day tab | Press play. Let the price line draw for a moment. |
| 8 to 18 | The opening auction tab | Show the price where most shares trade and who got what. |
| 18 to 30 | Practice tab | Choose "₹20 brokerage per order", press Start the day, press play. |
| 30 to 42 | Order ticket | Type 5 shares, choose "Best price now", read the preview, press Buy. The day pauses on the fill. |
| 42 to 58 | Statement panel | Scroll to "What trading has cost you". Point at the charge lines and the result after charges. |
| 58 to 65 | Terminal (optional) | Run `marketlab replay runs\demo.jsonl` to show the same fingerprint coming back. |

Say or caption one line: "A practice market where every rupee is accounted for, including the taxes."

## After recording

1. Save the file as `docs/img/demo.gif` (or upload the video and link it).
2. In the README, add `![Demo](docs/img/demo.gif)` just under the first paragraph.
3. Check the repository page on GitHub: the README renders, CI is green, no `.db` file or `node_modules` is committed.
