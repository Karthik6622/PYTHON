"""RAJU BHAI - Part 1: The Driverless Bus. Builds the silent master once, then one finished video per language (voice + burned subtitles)."""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import raju_lib as L  # noqa: E402
from raju_lib import FPS, SR, VH, VW, Image, ImageDraw  # noqa: E402

ROOT = Path(__file__).parent.parent / "raju_bhai" / "episodes" / "part01"
WORK = ROOT / "work"
WORK.mkdir(parents=True, exist_ok=True)
TOTAL = 45.0

# (start, end of the slot, speaker, {language: line})
LINES = [
    (0.7, 6.6, "narrator", {
        "en": "Midnight. Metro Nagar. A bus is racing through the rain... with no driver.",
        "ta": "நள்ளிரவு. மெட்ரோ நகரம். டிரைவரே இல்லாமல் ஒரு பஸ் மழையில் பாய்ந்து செல்கிறது.",
        "hi": "आधी रात। मेट्रो नगर। बारिश में एक बस दौड़ रही है... बिना ड्राइवर के।"}),
    (7.5, 12.8, "raju", {
        "en": "That bus is heading for the crowded junction. Not tonight.",
        "ta": "அந்த பஸ் கூட்டமான சந்திப்பை நோக்கிப் போகுது. இன்னைக்கு இல்ல.",
        "hi": "वो बस भीड़ वाले चौराहे की तरफ जा रही है। आज रात नहीं।"}),
    (14.0, 19.0, "raju", {
        "en": "Hold on, Metro Nagar. Raju Bhai is coming.",
        "ta": "கொஞ்சம் பொறு மெட்ரோ நகரமே. ராஜு பாய் வந்துட்டான்.",
        "hi": "ठहर जा मेट्रो नगर। राजू भाई आ रहा है।"}),
    (23.2, 29.6, "narrator", {
        "en": "Inside the empty bus... a small child. Holding a strange metal box.",
        "ta": "காலியான பஸ்ஸுக்குள்... ஒரு சின்னக் குழந்தை. கையில் ஒரு விசித்திரமான உலோகப் பெட்டி.",
        "hi": "खाली बस के अंदर... एक छोटा बच्चा। हाथ में एक अजीब सी धातु की पेटी।"}),
    (30.6, 34.4, "narrator", {
        "en": "And then... the box opened.",
        "ta": "அப்போது... அந்தப் பெட்டி திறந்தது.",
        "hi": "और फिर... वो पेटी खुल गई।"}),
    (39.4, 44.6, "narrator", {
        "en": "Something is waking up in Metro Nagar. Part two. Don't miss it.",
        "ta": "மெட்ரோ நகரில் ஏதோ ஒன்று விழித்துக்கொண்டிருக்கிறது. பாகம் இரண்டு. தவறவிடாதீர்கள்.",
        "hi": "मेट्रो नगर में कुछ जाग रहा है। पार्ट टू। मिस मत करना।"}),
]
LANGS = {"en": "English", "ta": "Tamil", "hi": "Hindi"}
VOICE_BY_LANG = {"en": {}, "ta": {"narrator": "ta-IN-ValluvarNeural", "raju": "ta-IN-ValluvarNeural", "child": "ta-IN-PallaviNeural"},
                 "hi": {"narrator": "hi-IN-MadhurNeural", "raju": "hi-IN-MadhurNeural", "child": "hi-IN-SwaraNeural"}}


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


class Show:
    def __init__(self) -> None:
        self.s = {n: getattr(L, f"scene_{n}")() for n in ("bus", "chase", "interior", "closeup", "shock", "cobra")}
        self.rain, self.vig = L.rain_layer(), L.vignette()

    def overlay_rain(self, fr: Image.Image, t: float, amount: float = 1.0) -> None:
        off = int((t * 1700) % VH)
        fr.alpha_composite(self.rain.crop((0, VH - off, VW, 2 * VH - off)) if amount else self.rain.crop((0, 0, VW, VH)))

    def frame(self, t: float, f: int) -> Image.Image:
        rnd = random.Random(f)
        if t < 4.8:  # S1 wide: the driverless bus
            u = t / 4.8
            fr = L.camera(self.s["bus"], u, 1.0, 1.35, (0.0, 0.05), shake=6, seed=f)
            title = 1 if t < 3.2 else 0
        elif t < 7.0:  # S1b: push into the empty cab
            u = (t - 4.8) / 2.2
            fr = L.camera(self.s["bus"], u, 1.5, 3.4, (0.18, -0.05), shake=10, seed=f)
            title = 0
        elif t < 13.5:  # S2: Raju on the rooftop
            u = (t - 7.0) / 6.5
            fr = L.camera(self.s["closeup"], u, 1.0, 1.22, (0.0, -0.04), shake=3, seed=f)
            title = 0
        elif t < 23.0:  # S3: the chase
            u = (t - 13.5) / 9.5
            fr = L.camera(self.s["chase"], u, 1.0, 1.5, (0.0, 0.0), shake=16 + 14 * u, seed=f)
            title = 0
        elif t < 30.5:  # S4: inside the empty bus
            u = (t - 23.0) / 7.5
            fr = L.camera(self.s["interior"], u, 1.0, 1.5, (0.0, 0.1), shake=5, seed=f)
            title = 0
        elif t < 32.0:  # S5a: the box seam glows
            u = (t - 30.5) / 1.5
            fr = L.camera(self.s["interior"], u, 1.5, 2.4, (0.0, 0.35), shake=12, seed=f)
            title = 0
        elif t < 33.2:  # S5b: Raju's shocked face
            fr = L.camera(self.s["shock"], (t - 32.0) / 1.2, 1.0, 1.2, shake=14, seed=f)
            title = 0
        elif t < 38.2:  # S5c: the cobra rises
            u = (t - 33.2) / 5.0
            fr = L.camera(self.s["cobra"], u, 1.0, 1.35, (0.0, -0.08), shake=7 * (1 - u) + 3, seed=f)
            title = 0
        else:
            fr = Image.new("RGB", (VW, VH), (0, 0, 0))
            title = 0
        fr = fr.convert("RGBA")
        if t < 38.0 and not (30.5 <= t < 33.2 and False):
            self.overlay_rain(fr, t)
        if 13.5 <= t < 23.0:
            L.speed_lines(fr, (VW // 2, VH * 0.52), 0.5 + 0.8 * (t - 13.5) / 9.5, rnd)
        if t < 38.0:
            fr.alpha_composite(self.vig)
        for flash_t in (7.0, 20.5, 33.2):  # lightning
            k = t - flash_t
            if 0 <= k < 0.45:
                a = int(210 * max(0.0, 1 - k / 0.45) * (1 if int(k * 24) % 2 == 0 else 0.55))
                fr.alpha_composite(Image.new("RGBA", fr.size, (225, 235, 255, a)))
        if 23.0 <= t < 30.5 and int(t * 12) % 9 == 0:  # the bus lights flicker
            fr.alpha_composite(Image.new("RGBA", fr.size, (0, 0, 0, 120)))
        if 30.5 <= t < 33.2:  # the box glow pulses
            pulse = int(70 + 60 * math.sin((t - 30.5) * 14))
            fr.alpha_composite(Image.new("RGBA", fr.size, (30, 255, 140, max(pulse, 0) // 2)))
        if t >= 38.0:
            self.end_card(fr, t - 38.0)
        layer = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
        if title:
            a = ease(min((t - 0.2) / 0.5, 1)) * (1 - ease((t - 2.7) / 0.5))
            tl = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
            L.title_text(tl, "RAJU BHAI", 520, 230, stroke=16)
            L.title_text(tl, "PART 1", 700, 120, colour=(255, 255, 255), stroke=10)
            L.title_text(tl, "THE DRIVERLESS BUS", 840, 78, colour=(255, 140, 30), stroke=8)
            tl.putalpha(tl.getchannel("A").point(lambda v: int(v * a)))
            layer.alpha_composite(tl)
        fr.alpha_composite(layer)
        return fr

    def end_card(self, fr: Image.Image, u: float) -> None:
        if 0.2 < u < 1.8:  # a red eye opens in the dark
            k = ease((u - 0.2) / 0.6)
            ey = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
            d = ImageDraw.Draw(ey)
            for sx in (-1, 1):
                x = VW // 2 + sx * 90
                for rr, a in ((120, 24), (70, 50), (34, 120)):
                    d.ellipse([x - rr * k, 1180 - rr * k * 0.6, x + rr * k, 1180 + rr * k * 0.6], fill=(255, 20, 20, int(a * k)))
                d.ellipse([x - 16 * k, 1180 - 8 * k, x + 16 * k, 1180 + 8 * k], fill=(255, 80, 80, int(255 * k)))
            fr.alpha_composite(ey.filter(L.ImageFilter.GaussianBlur(2)))
        if u > 2.0:
            a = ease((u - 2.0) / 0.5)
            tl = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
            L.title_text(tl, "TO BE CONTINUED", 640, 120, colour=(255, 255, 255), stroke=10)
            L.title_text(tl, "RAJU BHAI", 820, 190, stroke=14)
            L.title_text(tl, "PART 2 - COMING NEXT", 990, 80, colour=(255, 140, 30), stroke=8)
            L.title_text(tl, "SUBSCRIBE SO YOU DON'T MISS IT", 1640, 58, colour=(255, 255, 255), stroke=8)
            tl.putalpha(tl.getchannel("A").point(lambda v: int(v * a)))
            fr.alpha_composite(tl)


# ----------------------------------------------------------------------------------------
# sound
# ----------------------------------------------------------------------------------------
def sound_bed() -> np.ndarray:
    n = int(TOTAL * SR)
    t = np.arange(n) / SR
    mix = np.zeros(n, "float32")
    rain = L.lowpass(L.noise(n, 1), 5) * 0.30 + L.noise(n, 2) * 0.03
    rain *= np.interp(t, [0, 1, 36, 38.5, TOTAL], [0.0, 0.8, 0.8, 0.0, 0.0])
    mix += rain
    chord = sum(L.tone(f, n) for f in (55.0, 82.4, 110.0, 130.8)) * 0.045 * (0.6 + 0.4 * np.sin(t * 0.7))  # dark Am drone
    mix += chord * np.interp(t, [0, 2, 36, 38.5, 44, TOTAL], [0, 1, 1, 1.4, 0.6, 0])
    for (a, b, f0, f1, vol) in ((0.5, 7.0, 46, 62, 0.20), (13.0, 23.0, 78, 170, 0.33), (22.5, 30.5, 40, 48, 0.12)):  # bus and bike engines
        m = int((b - a) * SR)
        freq = np.linspace(f0, f1, m).astype("float32")
        eng = (L.tone(freq, m) + 0.5 * L.tone(freq * 2, m) + 0.3 * L.tone(freq * 3.01, m)) * (1 + 0.25 * L.tone(np.full(m, 11.0), m))
        eng = np.tanh(eng * 1.6) * vol * L.envelope(m, 0.4, 0.5)
        mix[int(a * SR): int(a * SR) + m] += eng
    bpm = 150
    for beat in range(int(13.5 * bpm / 60), int(23.0 * bpm / 60)):  # chase pulse
        s = int((beat * 60 / bpm) * SR)
        m = int(0.22 * SR)
        k = L.tone(np.linspace(150, 42, m).astype("float32"), m) * np.exp(-np.linspace(0, 7, m)) * 0.55
        mix[s: s + m] += k[: max(0, min(m, n - s))]
        h = int((beat * 60 / bpm + 0.2) * SR)
        mix[h: h + 2200] += L.noise(2200, beat)[: max(0, min(2200, n - h))] * np.exp(-np.linspace(0, 9, 2200)) * 0.07
    for at, dur, vol in ((7.0, 2.4, 0.6), (20.5, 2.0, 0.5), (33.2, 2.6, 0.5)):  # thunder
        m = int(dur * SR)
        th = L.lowpass(L.noise(m, int(at)), 160) * np.exp(-np.linspace(0, 4, m)) * vol * 14
        mix[int(at * SR): int(at * SR) + m] += th[: n - int(at * SR)]
    m = int(2.8 * SR)  # tension riser into the box opening
    rise = L.tone(np.linspace(180, 1400, m).astype("float32"), m) * np.linspace(0, 0.3, m) ** 1.5 * 0.7
    mix[int(30.4 * SR): int(30.4 * SR) + m] += rise
    m = int(1.6 * SR)  # the box hisses open, metal rings
    hiss = L.lowpass(L.noise(m, 9), 2) * np.exp(-np.linspace(0, 3, m)) * 0.35
    ring = (L.tone(1760.0, m) + 0.6 * L.tone(2637.0, m)) * np.exp(-np.linspace(0, 5, m)) * 0.2
    mix[int(33.2 * SR): int(33.2 * SR) + m] += hiss + ring
    m = int(1.8 * SR)  # the cut to black
    boom = L.tone(np.linspace(90, 30, m).astype("float32"), m) * np.exp(-np.linspace(0, 3, m)) * 0.9
    mix[int(38.0 * SR): int(38.0 * SR) + m] += boom
    for hb in (39.0, 39.55, 40.2, 40.75):  # heartbeat under the end card
        m = int(0.18 * SR)
        mix[int(hb * SR): int(hb * SR) + m] += L.tone(np.linspace(70, 40, m).astype("float32"), m) * np.exp(-np.linspace(0, 6, m)) * 0.35
    return mix


def voice_track(lang: str) -> tuple[np.ndarray, list[tuple[float, float, str, str]]]:
    n = int(TOTAL * SR)
    track = np.zeros(n, "float32")
    cues = []
    for i, (a, b, speaker, text) in enumerate(LINES):
        line = text[lang]
        override = VOICE_BY_LANG[lang].get(speaker)
        if override:
            L.VOICES[speaker] = (override, L.VOICES[speaker][1], "-6Hz" if speaker == "raju" else "+0Hz")
        raw = WORK / f"{lang}_{i}.wav"
        dur = L.speak(line, speaker, raw)
        data = L.read_wav(raw)
        slot = b - a
        if dur > slot:  # a long line is sped up, never cut
            tempo = min(dur / slot, 1.45)
            fitted = WORK / f"{lang}_{i}_fit.wav"
            L.subprocess.run([L.FFMPEG, "-y", "-loglevel", "error", "-i", str(raw), "-filter:a", f"atempo={tempo:.3f}", str(fitted)], check=True)
            data, dur = L.read_wav(fitted), dur / tempo
        s = int(a * SR)
        track[s: s + len(data)] += data[: n - s]
        cues.append((a, a + dur + 0.15, speaker, line))
    return track, cues


def ass_time(x: float) -> str:
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


def write_ass(lang: str, cues, path: Path) -> None:
    fnt = "Nirmala UI" if lang != "en" else "Arial Black"
    colour = {"raju": "&H0AD6FF&", "child": "&HFFEB78&", "narrator": "&HFFFFFF&"}
    head = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {VW}\nPlayResY: {VH}\n\n[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Default,{fnt},68,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,2,90,90,330,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    body = "".join(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{{\\c{colour[sp]}}}{text}\n" for a, b, sp, text in cues)
    path.write_text(head + body, encoding="utf-8-sig")


STUDIO_PY = Path(r"C:\Users\karthik.r\OneDrive - ascendion\Desktop\github_repo\PYTHON\Projects\ai_testing_studio\.venv\Scripts\python.exe")  # has Playwright + Chromium


def subtitle_cards(lang: str, cues) -> dict:
    """One transparent PNG per spoken line, drawn by Chromium so Tamil and Hindi are shaped correctly."""
    import json

    jobs = [{"out": str(WORK / f"sub_{lang}_{i}.png"), "text": c[3], "speaker": c[2], "lang": lang} for i, c in enumerate(cues)]
    spec = WORK / f"subs_{lang}.json"
    spec.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    L.subprocess.run([str(STUDIO_PY), str(Path(__file__).parent / "render_subs.py"), str(spec)], check=True)
    return {i: Image.open(j["out"]).convert("RGBA") for i, j in enumerate(jobs)}

def main() -> None:
    show = Show()
    bed = sound_bed()
    only = [a for a in sys.argv[1:] if a in LANGS]
    for lang, name in LANGS.items():
        if only and lang not in only:
            continue
        voice, cues = voice_track(lang)
        duck = np.ones_like(bed)
        for a, b, _, _ in cues:  # the music and rain dip under every spoken line
            duck[int(max(a - 0.2, 0) * SR): int((b + 0.3) * SR)] = 0.55
        mixed = np.tanh((bed * L.lowpass(duck, 4000) + voice * 1.25) * 1.1) * 0.92
        wav = WORK / f"mix_{lang}.wav"
        L.write_wav(wav, mixed)
        total, cards = int(TOTAL * FPS), subtitle_cards(lang, cues)

        def frames():
            for f in range(total):
                if f % 150 == 0:
                    print(f"{lang} frame {f}/{total}", flush=True)
                t = f / FPS
                fr = show.frame(t, f)
                idx = next((i for i, c in enumerate(cues) if c[0] <= t < c[1]), None)
                if idx is not None:
                    fr.alpha_composite(cards[idx])
                yield fr

        out = ROOT / f"RajuBhai_Part01_{name}.mp4"
        L.render_video(frames(), wav, out)
        print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
