"""Short, actionable hints shown under a failed terminal command (missing Python package, missing Playwright browser...)."""

from __future__ import annotations

import re

_MISSING_MODULE = re.compile(r"No module named ['\"]([A-Za-z0-9_.\-]+)['\"]")
_PLAYWRIGHT_BROWSER = re.compile(r"Executable doesn't exist|playwright install|BrowserType\.launch: .*not found", re.I | re.S)
_PLAYWRIGHT_DEPS = re.compile(r"Host system is missing dependencies|install-deps|error while loading shared libraries", re.I)
_DISPLAY = re.compile(r"Missing X server|headless.*(?:false|False)|no display|cannot open display", re.I)
_INPUT = re.compile(r"EOFError: EOF when reading a line", re.I)
_GIT_LOGIN = re.compile(r"could not read (?:Username|Password)|terminal prompts disabled", re.I)
_GIT_DENIED = re.compile(r"Authentication failed|Permission to .* denied|Invalid username or (?:password|token)|The requested URL returned error: 40[13]", re.I)
_NO_GH = re.compile(r"\bgh: (?:command )?not found|'gh' is not recognized", re.I)

# import name -> pip package, for the common cases where they differ
PIP_NAMES = {
    "cv2": "opencv-python", "PIL": "pillow", "sklearn": "scikit-learn", "yaml": "pyyaml", "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv", "git": "GitPython", "skimage": "scikit-image", "dateutil": "python-dateutil",
}


def hint_for(command: str, output: str, exit_code: int | None) -> str:
    """One or two lines of advice, or an empty string when nothing helpful is known."""
    if not output or exit_code in (0, None):
        return ""
    lines: list[str] = []
    missing = _MISSING_MODULE.search(output)
    if missing:
        module = missing.group(1).split(".")[0]
        package = PIP_NAMES.get(module, module.replace("_", "-"))
        lines.append(f"Missing Python package '{module}'. Install it with: pip install {package}")
    if _PLAYWRIGHT_BROWSER.search(output):
        lines.append("Playwright has no browser yet. Run: python -m playwright install chromium")
    if _PLAYWRIGHT_DEPS.search(output):
        lines.append("The server is missing system libraries for the browser. Locally run: python -m playwright install-deps. "
                     "On Streamlit Cloud add them to packages.txt (for example libnss3, libatk1.0-0, libgbm1, libasound2).")
    if _DISPLAY.search(output):
        lines.append("There is no screen on this server. Launch the browser headless: p.chromium.launch(headless=True)")
    if _INPUT.search(output):
        lines.append("The terminal cannot answer input() prompts. Pass values as arguments or environment variables instead.")
    if _GIT_LOGIN.search(output) or _NO_GH.search(output):
        lines.append("GitHub login cannot be typed in this terminal (and the GitHub CLI is not installed). Open Settings, add a GitHub token "
                     "(classic 'repo' scope), then run a plain git push / pull / fetch again: the token is used automatically.")
    elif _GIT_DENIED.search(output):
        lines.append("GitHub rejected the token. Check that the token in Settings is valid and has write access ('repo' scope) to this repository.")
    return "\n".join(lines)
