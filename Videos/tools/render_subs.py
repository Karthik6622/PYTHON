"""Render subtitle cards (transparent PNG, 1080x1920) with Chromium, which shapes Tamil and Hindi correctly.
Usage: render_subs.py <jobs.json>   jobs: [{"out": path, "text": str, "speaker": "raju|child|narrator", "lang": "en|ta|hi"}]"""

import html
import json
import sys

from playwright.sync_api import sync_playwright

COLOURS = {"raju": "#FFD60A", "child": "#78EBFF", "narrator": "#FFFFFF"}
PAGE = """<html><body style="margin:0;background:transparent;width:1080px;height:1920px;position:relative">
<div style="position:absolute;left:70px;right:70px;top:1330px;transform:translateY(-50%);text-align:center;
font-family:{family};font-weight:900;font-size:{size}px;line-height:1.38;color:{colour};
-webkit-text-stroke:11px #000;paint-order:stroke fill;text-shadow:0 6px 14px rgba(0,0,0,.65)">{text}</div></body></html>"""

jobs = json.load(open(sys.argv[1], encoding="utf-8"))
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1080, "height": 1920})
    for job in jobs:
        family = "'Arial Black','Segoe UI',sans-serif" if job["lang"] == "en" else "'Nirmala UI','Segoe UI',sans-serif"
        size = 74 if job["lang"] == "en" else 68
        page.set_content(PAGE.format(family=family, size=size, colour=COLOURS[job["speaker"]], text=html.escape(job["text"])))
        page.screenshot(path=job["out"], omit_background=True)
    browser.close()
print("rendered", len(jobs))
