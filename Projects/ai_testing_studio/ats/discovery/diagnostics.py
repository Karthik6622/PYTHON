"""Explains why Chromium cannot start on a Linux host and what to install.

Playwright's Chromium links against system libraries (NSS, ALSA, GTK/ATK, ...). On a minimal host (Streamlit Community
Cloud, slim Docker images) some are missing and the browser dies at launch with an unhelpful ``TargetClosedError``.
``ldd`` on the browser binary names exactly which libraries are absent.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# Shared object name prefix -> Debian/Ubuntu package that provides it.
LIB_TO_PACKAGE = {
    "libnss3": "libnss3", "libnssutil3": "libnss3", "libsmime3": "libnss3", "libnspr4": "libnspr4", "libplc4": "libnspr4", "libplds4": "libnspr4",
    "libasound": "libasound2", "libatk-1.0": "libatk1.0-0", "libatk-bridge-2.0": "libatk-bridge2.0-0", "libatspi": "libatspi2.0-0",
    "libcups": "libcups2", "libdrm": "libdrm2", "libgbm": "libgbm1", "libxkbcommon": "libxkbcommon0", "libXcomposite": "libxcomposite1",
    "libXdamage": "libxdamage1", "libXfixes": "libxfixes3", "libXrandr": "libxrandr2", "libXext": "libxext6", "libX11": "libx11-6",
    "libxcb": "libxcb1", "libdbus-1": "libdbus-1-3", "libpango-1.0": "libpango-1.0-0", "libcairo": "libcairo2", "libglib-2.0": "libglib2.0-0",
    "libgio-2.0": "libglib2.0-0", "libgobject-2.0": "libglib2.0-0", "libxshmfence": "libxshmfence1", "libwayland-server": "libwayland-server0",
    "libexpat": "libexpat1", "libfontconfig": "libfontconfig1", "libfreetype": "libfreetype6",
}  # fmt: skip

PACKAGES_TXT_NOTE = (
    "On Streamlit Community Cloud, `packages.txt` is only read from the ROOT of the GitHub repository. This app lives in a sub-folder, "
    "so copy its `packages.txt` to the repository root, commit it and reboot the app. With Docker, rebuild the image "
    "(the Dockerfile already installs these packages)."
)


def _browser_roots() -> list[Path]:
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if custom and custom != "0":
        return [Path(custom)]
    return [Path.home() / ".cache" / "ms-playwright", Path("/ms-playwright")]


def browser_binaries() -> list[Path]:
    """Chromium executables installed by Playwright (full build and headless shell)."""
    found: list[Path] = []
    for root in _browser_roots():
        if not root.is_dir():
            continue
        for pattern in ("chromium_headless_shell-*/*/chrome-headless-shell", "chromium-*/chrome-linux*/chrome", "chromium-*/*/chrome"):
            found.extend(sorted(root.glob(pattern), reverse=True))
    return found


def missing_libraries(binary: Path | None = None) -> list[str]:
    """Shared libraries ``ldd`` cannot resolve for the Chromium binary (empty on other platforms or when all are present)."""
    if not sys.platform.startswith("linux"):
        return []
    targets = [binary] if binary else browser_binaries()[:2]
    missing: list[str] = []
    for target in targets:
        try:
            result = subprocess.run(["ldd", str(target)], capture_output=True, text=True, timeout=30, check=False)  # noqa: S603,S607
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in result.stdout.splitlines():
            if "not found" in line:
                name = line.split("=>")[0].strip()
                if name and name not in missing:
                    missing.append(name)
    return missing


def packages_for(libraries: list[str]) -> list[str]:
    packages: list[str] = []
    for library in libraries:
        prefix = re.split(r"\.so", library)[0]
        package = LIB_TO_PACKAGE.get(prefix)
        if package and package not in packages:
            packages.append(package)
    return packages


def explain_launch_failure(error_text: str = "") -> str:
    """A complete, user-readable explanation of a Chromium launch failure."""
    libraries = missing_libraries()
    if libraries:
        packages = packages_for(libraries)
        names = ", ".join(libraries[:12])
        fix = f" Install: {', '.join(packages)}." if packages else ""
        return f"Chromium cannot start because Linux system libraries are missing ({names}).{fix} {PACKAGES_TXT_NOTE}"
    first_line = (error_text or "").strip().splitlines()[0][:220] if (error_text or "").strip() else ""
    detail = f" Browser error: {first_line}" if first_line else ""
    return (
        "Chromium is installed but could not start on this host." + detail
        + " If this is a hosted container, check its memory limit (Chromium needs about 1 GB) and see the system-library list in `packages.txt`. "
        + PACKAGES_TXT_NOTE
    )
