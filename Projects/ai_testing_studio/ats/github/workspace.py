"""Inspect an automation workspace: a branch of a repository. Which channels (Web / API / Mobile) does it already hold?"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ats.github.client import GitHubClient, repo_slug, workspace_key
from ats.github.merge import MANIFEST_PATH, SHARED_FILES, Manifest
from ats.models import CHANNEL_LABELS, CHANNELS

__all__ = ["ChannelState", "WorkspaceInfo", "analyze_tree", "check_compatible", "inspect_workspace", "repo_slug", "workspace_key"]

EXISTING, NOT_PRESENT = "existing", "not present"
CHANNEL_PREFIXES = {"web": ("tests/web/",), "api": ("tests/api/",), "mobile": ("tests/mobile/", "screens/mobile/", "mobile_config/")}
# Files that identify the generator that produced a channel when the manifest does not say.
FRAMEWORK_HINTS = {
    "web": (("utils/element.py", "selenium_python"), ("utils/nav.py", "playwright_python"), ("utils/app.py", "playwright_python")),
    "api": (("utils/api.py", "api_python"),),
    "mobile": (("drivers/appium_driver.py", "appium_python"),),
}
SUPPORT_PREFIXES = ("pages/", "utils/", "config/", "screens/", "drivers/", "mobile_config/", ".ats/", "tests/")
LAYOUT_EMPTY, LAYOUT_CHANNELS, LAYOUT_FOREIGN = "empty", "channels", "foreign"


@dataclass
class ChannelState:
    channel: str
    status: str = NOT_PRESENT
    framework: str = ""
    files: int = 0
    source: str = ""  # "manifest" (published by the studio) | "detected" (found by folder)

    @property
    def existing(self) -> bool:
        return self.status == EXISTING

    @property
    def label(self) -> str:
        return f"{'✅' if self.existing else '➕'} {CHANNEL_LABELS[self.channel]}"


@dataclass
class WorkspaceInfo:
    repo: str  # owner/name, lower case
    branch: str
    exists: bool = False
    head_sha: str = ""
    channels: dict[str, ChannelState] = field(default_factory=lambda: {c: ChannelState(c) for c in CHANNELS})
    layout: str = LAYOUT_EMPTY
    foreign: str = ""  # what keeps its own layout (e.g. "playwright_typescript"), when layout == "foreign"
    other_files: list[str] = field(default_factory=list)
    manifest: Manifest = field(default_factory=Manifest)
    tree: dict[str, str] = field(default_factory=dict)  # path -> blob sha of every file on the branch

    @property
    def key(self) -> str:
        return workspace_key(self.repo, self.branch)

    def status_of(self, channel: str) -> str:
        return self.channels[channel].status

    def existing_channels(self) -> list[str]:
        return [c for c in CHANNELS if self.channels[c].existing]


def _foreign_framework(tree: dict[str, str]) -> str:
    """The non-Python (or old single-folder) layout the branch holds, if any."""
    paths = set(tree)
    if "package.json" in paths and any(re.fullmatch(r"playwright\.config\.(ts|js|mjs)", p) for p in paths):
        return "playwright_typescript" if "playwright.config.ts" in paths else "playwright_javascript"
    if "pom.xml" in paths or any(p.startswith("src/test/java/") for p in paths):
        return "selenium_java"
    if "conftest.py" in paths and any(re.fullmatch(r"tests/[^/]+\.py", p) and not p.endswith("__init__.py") for p in paths):
        return "legacy_python"  # the studio's earlier single-channel layout: tests/test_*.py and a root conftest.py
    return ""


def analyze_tree(tree: dict[str, str], manifest: Manifest) -> tuple[dict[str, ChannelState], str, str, list[str]]:
    """``(channel states, layout, foreign framework, other files)`` for the files of a branch. Pure."""
    states = {c: ChannelState(c) for c in CHANNELS}
    claimed: set[str] = set()
    for channel in CHANNELS:
        listed = [p for p in manifest.files_of(channel) if p in tree]
        found = [p for p in tree if p.startswith(CHANNEL_PREFIXES[channel])]
        if listed or found:
            hints = [fw for marker, fw in FRAMEWORK_HINTS[channel] if marker in tree]
            states[channel] = ChannelState(
                channel, EXISTING, manifest.framework_of(channel) or (hints[0] if hints else ""), len({*listed, *found}), "manifest" if listed else "detected"
            )
            claimed.update(listed, found)
    web = states["web"]
    if web.existing and web.framework and not _is_python(web.framework):
        foreign = web.framework  # published by the studio with a framework that keeps its own layout
    else:
        foreign = _foreign_framework(tree) if tree and not any(s.existing for s in states.values()) else ""
        if foreign:
            states["web"] = ChannelState("web", EXISTING, foreign, sum(1 for p in tree if "test" in p.lower()), "detected")
    layout = LAYOUT_FOREIGN if foreign else (LAYOUT_CHANNELS if tree else LAYOUT_EMPTY)
    other = sorted(p for p in tree if p not in claimed and p not in SHARED_FILES and p != MANIFEST_PATH and not p.startswith(SUPPORT_PREFIXES))
    return states, layout, foreign, other


def _is_python(framework: str) -> bool:
    return framework.endswith("_python")


def check_compatible(info: WorkspaceInfo, frameworks: dict[str, str]) -> str:
    """Empty when the selected channels (``{channel: framework}``) can be added to the branch, else the reason in plain words."""
    others = {c for c in frameworks if c != "web"}
    web_fw = frameworks.get("web", "")
    if web_fw and not _is_python(web_fw) and (others or [c for c in info.existing_channels() if c != "web"]):
        return (
            f"{web_fw.replace('_', ' ').title()} keeps its own repository layout, so it cannot share a branch with API or Mobile tests. "
            "Publish the Web tests to their own branch, or choose a Python Web framework."
        )
    if info.layout == LAYOUT_FOREIGN and (others or (web_fw and web_fw != info.foreign)):
        label = "the studio's earlier single-folder layout" if info.foreign == "legacy_python" else info.foreign.replace("_", " ").title()
        return f"This branch holds {label}, which keeps its own layout. Adding other channels to it is not supported: publish to another branch."
    return ""


def inspect_workspace(client: GitHubClient, owner: str, name: str, branch: str) -> WorkspaceInfo:
    """Read the branch tree through the Git Data API (no clone). A missing branch is a valid answer: ``exists`` is False."""
    info = WorkspaceInfo(repo=f"{owner}/{name}".lower(), branch=branch)
    head = client.branch_head(owner, name, branch)
    if head is None:
        return info
    info.exists, info.head_sha = True, head
    tree = client.get_tree(owner, name, client.get_commit(owner, name, head)["tree"])
    info.tree = {path: entry["sha"] for path, entry in tree.items()}
    if MANIFEST_PATH in info.tree:
        info.manifest = Manifest.parse(client.get_blob_text(owner, name, info.tree[MANIFEST_PATH]))
    info.channels, info.layout, info.foreign, info.other_files = analyze_tree(info.tree, info.manifest)
    return info
