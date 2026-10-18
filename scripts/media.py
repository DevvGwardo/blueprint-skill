#!/usr/bin/env python3
"""Blueprint media helpers: turn raw harness captures into compact, labelled page media.

  media.py web   IN.png OUT.jpg [--max 1600]                 screenshot -> compressed jpg
  media.py sheet OUT.jpg A.png B.png ... [--cols 3] [--h 900] [--labels "a|b|c"]
  media.py pair  OUT.jpg BEFORE.png AFTER.png [--labels "Before|After"]
  media.py strip OUT.jpg VIDEO.mp4 0.5 2 4 6 [--h 640]     frames of a video at given seconds
  media.py mp4   IN.mp4 OUT.mp4 [--w 540]                   web copy: h264, faststart, smaller

Needs Pillow; strip/mp4 need ffmpeg on PATH.
"""
import subprocess, sys, tempfile, os
from PIL import Image, ImageDraw, ImageFont

BG = (15, 17, 21)
INK = (232, 234, 240)

def font(size):
    for f in ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        try: return ImageFont.truetype(f, size)
        except OSError: pass
    return ImageFont.load_default()

def opt(args, name, default):
    if name in args:
        i = args.index(name); v = args[i + 1]; del args[i:i + 2]; return v
    return default

def grid(images, cols, h, labels, pad=12):
    ims = [im.convert("RGB").resize((round(im.width * h / im.height), h)) for im in images]
    lab = 40 if labels else 0
    rows = [ims[i:i + cols] for i in range(0, len(ims), cols)]
    W = max(sum(i.width for i in r) + pad * (len(r) - 1) for r in rows)
    H = len(rows) * (h + lab) + pad * (len(rows) - 1)
    out = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(out); k = 0
    tile = min(i.width for i in ims)
    def fit(text):  # largest font (<= 24px) whose label fits inside the narrowest tile
        for size in range(24, 9, -1):
            f = font(size)
            if d.textlength(text, font=f) <= tile - 8: return f
        return font(10)
    for ri, r in enumerate(rows):
        x, y = 0, ri * (h + lab + pad)
        for im in r:
            if labels: d.text((x + 4, y + 8), labels[k], fill=INK, font=fit(labels[k]))
            out.paste(im, (x, y + lab)); x += im.width + pad; k += 1
    return out

def save(im, path, maxw=1800):
    im.thumbnail((maxw, maxw * 4)); im.save(path, quality=84, optimize=True); print(path, im.size)

def main(a):
    cmd = a.pop(0)
    if cmd == "web":
        m = int(opt(a, "--max", 1600)); im = Image.open(a[0]).convert("RGB"); im.thumbnail((m, m)); im.save(a[1], quality=84, optimize=True); print(a[1], im.size)
    elif cmd in ("sheet", "pair"):
        labels = opt(a, "--labels", "Before|After" if cmd == "pair" else "")
        cols = int(opt(a, "--cols", 2 if cmd == "pair" else 3)); h = int(opt(a, "--h", 900))
        out, files = a[0], a[1:]
        save(grid([Image.open(p) for p in files], cols, h, labels.split("|") if labels else None), out)
    elif cmd == "strip":
        h = int(opt(a, "--h", 640)); out, video, times = a[0], a[1], a[2:]
        with tempfile.TemporaryDirectory() as tmp:
            frames = []
            for i, t in enumerate(times):
                p = os.path.join(tmp, f"{i}.png")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", video, "-frames:v", "1", p], check=True)
                frames.append(Image.open(p).copy())
            save(grid(frames, len(frames), h, [f"{t}s" for t in times]), out, maxw=2400)
    elif cmd == "mp4":
        w = opt(a, "--w", "540")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a[0], "-vf", f"scale={w}:-2", "-c:v", "libx264", "-crf", "26", "-preset", "slow",
                        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", a[1]], check=True); print(a[1])
    else:
        print(__doc__); sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    main(sys.argv[1:])
