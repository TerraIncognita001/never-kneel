"""Never Kneel: story JSON -> narrated 16:9 video (pictures + Ken Burns + voice + music) + thumbnail + metadata.

python nk.py stories/<id>.json            full render -> work/<id>/final.mp4, cover.png, metadata.json
Env: TTS=edge|kokoro (edge = en-US voice on the runner; kokoro = offline, for sandboxes without WebSocket)
     VOICE (edge, default en-US-GuyNeural) / KOKORO_VOICE (default am_onyx)
     IMG=cloudflare|pollinations (cloudflare = FLUX.1 schnell, needs CF_ACCOUNT_ID + CF_API_TOKEN, free 10k neurons/day;
         pollinations = anonymous, 1024 px with a watermark that is cropped away: test only)
     MUSIC_DIR (default music/; dark ambient tracks, not in this public repo)
"""
import asyncio, base64, json, os, pathlib, random, re, subprocess, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
W, H, FPS = 1920, 1080, 30
XF = 0.8                       # crossfade between pictures, s
GAP = 0.7                      # silence between scenes, s
FONT = ROOT / "fonts/BebasNeue-Regular.ttf"
RED = (214, 32, 32)


def env(k, d=""):
    return os.environ.get(k, d)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"FAILED: {' '.join(map(str, cmd))[:300]}\n{r.stderr[-2000:]}")
    return r


def dur(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).stdout)


# ---------- voice ----------
def sentences(text):
    return [s for s in re.split(r'(?:(?<=[.!?])|(?<=[.!?]["”]))\s+(?=["“A-Z])', text.strip()) if s]


def tts_edge(text, out):
    import edge_tts
    async def go():
        await edge_tts.Communicate(text, env("VOICE", "en-US-GuyNeural"), rate=env("RATE", "-4%")).save(str(out))
    for i in range(4):
        try:
            asyncio.run(go())
            if out.stat().st_size > 1000:
                return
        except Exception as e:
            print("edge tts retry", i, e)
            time.sleep(5 * (i + 1))
    raise RuntimeError("edge tts failed")


_K = None
def tts_kokoro(text, out):
    global _K
    import numpy as np, soundfile as sf
    from kokoro_onnx import Kokoro
    kd = pathlib.Path(env("KOKORO_DIR", str(pathlib.Path.home() / "kokoro")))
    _K = _K or Kokoro(str(kd / "kokoro-v1.0.int8.onnx"), str(kd / "voices-v1.0.bin"))
    parts, sr = [], 24000
    for s in sentences(text):
        a, sr = _K.create(s, voice=env("KOKORO_VOICE", "am_onyx"), speed=float(env("KOKORO_SPEED", "0.95")), lang="en-us")
        parts += [a, np.zeros(int(sr * 0.28), dtype=a.dtype)]
    sf.write(str(out), np.concatenate(parts), sr)


def voice(scenes, wd):
    eng = env("TTS", "edge")
    files = []
    for i, sc in enumerate(scenes):
        out = wd / f"v{i:03d}.{'mp3' if eng == 'edge' else 'wav'}"
        if not out.exists():
            (tts_edge if eng == "edge" else tts_kokoro)(sc["text"], out)
        files.append(out)
        print(f"voice {i + 1}/{len(scenes)} {dur(out):.1f}s", flush=True)
    return files


# ---------- pictures ----------
def prompt(story, p):
    for k, v in story["cast"].items():
        p = p.replace("{" + k + "}", v)
    return f"{p}, {story['style']}, no text, no watermark"


def img_pollinations(p, seed, out):
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(p) + f"?width=1920&height=1080&nologo=true&seed={seed}"
    urllib.request.urlretrieve(url, out)
    from PIL import Image
    im = Image.open(out).convert("RGB")
    w, h = im.size                                   # the anonymous tier stamps 'pollinations.ai' bottom right: cut it off
    im.crop((0, 0, int(w * 0.935), int(h * 0.935))).save(out, quality=95)


def img_cloudflare(p, seed, out):
    acc, tok = env("CF_ACCOUNT_ID"), env("CF_API_TOKEN")
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-1-schnell",
        data=json.dumps({"prompt": p, "steps": 8, "seed": seed, "width": 1344, "height": 768}).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=180))
    out.write_bytes(base64.b64decode(r["result"]["image"]))


def pictures(story, items, wd):
    fn = img_cloudflare if env("IMG", "pollinations") == "cloudflare" else img_pollinations
    files = []
    for i, (p, seed) in enumerate(items):
        out = wd / f"i{i:03d}.jpg"
        for t in range(5):
            if out.exists() and out.stat().st_size > 20000:
                break
            try:
                fn(prompt(story, p), seed, out)
            except Exception as e:
                print("image retry", i, t, e)
                time.sleep(10 * (t + 1))
        if not out.exists():
            sys.exit(f"no picture for scene {i}")
        files.append(out)
        print(f"picture {i + 1}/{len(items)}", flush=True)
    return files


# ---------- render ----------
def ken_burns(img, seconds, i, out):
    n = int(round(seconds * FPS))
    zin = i % 2 == 0                                 # alternate push-in / pull-out, and the drift side
    z = f"1.0+0.12*on/{n}" if zin else f"1.12-0.12*on/{n}"
    dx = ["0.5", "0.42+0.16*on/%d" % n, "0.58-0.16*on/%d" % n][i % 3]
    vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
          f"zoompan=z='{z}':x='(iw-iw/zoom)*({dx})':y='(ih-ih/zoom)/2':d={n}:s={W}x{H}:fps={FPS},"
          f"eq=contrast=1.05:saturation=1.08,vignette=PI/5,format=yuv420p")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(img), "-vf", vf, "-frames:v", str(n),
         "-c:v", "libx264", "-preset", env("PRESET", "veryfast"), "-crf", "20", str(out)])


def join(segs, lens, out):
    inp, fc, last, off = [], [], "0:v", 0.0
    for s in segs:
        inp += ["-i", str(s)]
    for k in range(1, len(segs)):
        off += lens[k - 1] - XF
        fc.append(f"[{last}][{k}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[x{k}]")
        last = f"x{k}"
    run(["ffmpeg", "-y", "-loglevel", "error", *inp, "-filter_complex", ";".join(fc), "-map", f"[{last}]",
         "-c:v", "libx264", "-preset", env("PRESET", "veryfast"), "-crf", "20", "-pix_fmt", "yuv420p", str(out)])


def music_bed(total, wd):
    md = pathlib.Path(env("MUSIC_DIR", str(ROOT / "music")))
    tracks = sorted(md.glob("*.mp3"))
    if not tracks:
        print("no music: voice only")
        return None, []
    random.seed(total)
    random.shuffle(tracks)
    pick, t = [], 0.0
    while t < total + 5:
        tr = tracks[len(pick) % len(tracks)]
        pick.append(tr)
        t += dur(tr)
    lst = wd / "music.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in pick))
    out = wd / "music.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-t", f"{total:.2f}",
         "-af", f"loudnorm=I={env('MUSIC_LUFS', '-31')}:TP=-3,afade=t=in:d=3,afade=t=out:st={max(total - 6, 0):.2f}:d=6",
         "-ar", "48000", "-ac", "2", str(out)])
    return out, [p.stem for p in dict.fromkeys(pick)]


def cover(story, img, out):
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance
    im = Image.open(img).convert("RGB")
    s = max(1280 / im.width, 720 / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    im = im.crop(((im.width - 1280) // 2, (im.height - 720) // 2, (im.width - 1280) // 2 + 1280, (im.height - 720) // 2 + 720))
    im = ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(1.2)).enhance(1.1)
    d = ImageDraw.Draw(im)
    bar = 150
    d.rectangle((0, 0, 1280, bar), fill=(8, 8, 8))
    d.rectangle((0, bar, 1280, bar + 8), fill=RED)    # the channel's red line under the bar
    words, key = story["thumb"]["words"].split(), story["thumb"]["key"]
    size = 150
    while True:
        f = ImageFont.truetype(str(FONT), size)
        sp = f.getlength(" ")
        width = sum(f.getlength(w) for w in words) + sp * (len(words) - 1)
        if width <= 1200 or size < 60:
            break
        size -= 4
    x = (1280 - width) / 2
    y = (bar - size * 0.86) / 2 - size * 0.04
    for w in words:
        d.text((x, y), w, font=f, fill=RED if w.strip("?!.,:") == key else (255, 255, 255))
        x += f.getlength(w) + sp
    im.save(out)


def main(path):
    story = json.loads(pathlib.Path(path).read_text())
    wd = ROOT / "work" / story["id"]
    wd.mkdir(parents=True, exist_ok=True)
    sc = story["scenes"]
    vfiles = voice(sc, wd)
    imgs = pictures(story, [(s["img"], s.get("seed", i + 1)) for i, s in enumerate(sc)] +
                    [(story["thumb"]["image"], story["thumb"].get("seed", 99))], wd)
    lens = [dur(v) + GAP for v in vfiles]
    lens[0] += 0.5                                     # a breath before the first word
    # voice track: 0.5 s lead, each scene + GAP
    parts = []
    for i, v in enumerate(vfiles):
        parts += ["-i", str(v)]
    fc = "".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur={GAP}{',adelay=500|500' if i == 0 else ''}[a{i}];"
                 for i in range(len(vfiles)))
    fc += "".join(f"[a{i}]" for i in range(len(vfiles))) + f"concat=n={len(vfiles)}:v=0:a=1,loudnorm=I=-16:TP=-1.5[v]"
    vtrack = wd / "voice.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", *parts, "-filter_complex", fc, "-map", "[v]", "-ar", "48000", str(vtrack)])
    total = dur(vtrack)
    lens[-1] = total - sum(lens[:-1])                   # picture lengths add up to the voice exactly
    seg_lens = [l + (XF if k < len(lens) - 1 else 0) for k, l in enumerate(lens)]
    segs = []
    for i, (img, l) in enumerate(zip(imgs, seg_lens)):
        out = wd / f"s{i:03d}.mp4"
        if not out.exists():
            ken_burns(img, l, i, out)
        segs.append(out)
        print(f"shot {i + 1}/{len(seg_lens)} {l:.1f}s", flush=True)
    video = wd / "video.mp4"
    join(segs, [dur(s) for s in segs], video)
    bed, credits = music_bed(total, wd)
    final = wd / "final.mp4"
    if bed:
        mix = (f"[1:a][2:a]amix=inputs=2:duration=first:normalize=0,"
               f"loudnorm=I=-14:TP=-2,alimiter=limit=0.79:level=false[a]")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(vtrack), "-i", str(bed),
             "-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", "-movflags", "+faststart", str(final)])
    else:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(vtrack), "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final)])
    cover(story, imgs[-1], wd / "cover.png")
    desc = story["description"] + "\n\n"
    if credits:
        desc += "Music: " + ", ".join(credits) + " (YouTube Audio Library)\n"
    desc += "An original story. Voice and pictures are AI-generated.\n\n" + story["hashtags"]
    meta = {"title": story["title"][:100], "description": desc, "tags": story["tags"], "categoryId": "24",
            "minutes": round(dur(final) / 60, 1), "tts": env("TTS", "edge"), "img": env("IMG", "pollinations")}
    (wd / "metadata.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(json.dumps(meta, indent=1, ensure_ascii=False))
    print("DONE", final)


if __name__ == "__main__":
    main(sys.argv[1])
