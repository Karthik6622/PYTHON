"""Automation planning: approved test cases -> validated scripts -> rendered framework project -> stored bundle."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from ats.ai.agents import ScriptGenerationAgent
from ats.automation.bundle_store import BundleStore
from ats.automation.traceability import build_traceability
from ats.config import get_settings
from ats.discovery.service import build_digest
from ats.errors import GenerationError, NotFoundError
from ats.generation.adapters import FRAMEWORKS, RenderContext, ScriptCase, browsers_for, get_adapter
from ats.models import ELEMENT_ACTIONS, STEP_ACTIONS, VALUE_ACTIONS, AutomationStep, DiscoveryResult, LocatorSpec, TestCase, TestScript
from ats.repository import Project, Repository

EventCallback = Callable[[str, str], None]
BATCH_SIZE = 5
MAX_ELEMENTS = 200
ENV_RE = re.compile(r"\{\{env:[A-Za-z_][A-Za-z0-9_]*\}\}")


# ----------------------------------------------------------------------------------------
# validation (pure functions, unit tested)
# ----------------------------------------------------------------------------------------
def build_corpus(test_case: TestCase, discovery: DiscoveryResult | None) -> str:
    parts = [test_case.title, test_case.description, test_case.expected_result, *test_case.steps, *test_case.preconditions, *test_case.test_data.values()]
    if discovery:
        for page in discovery.pages:
            parts += [page.title, *page.headings]
            for element in page.elements:
                parts += [str(element.get(k) or "") for k in ("name", "label", "text", "placeholder", "value")]
            parts += [str(link.get("text", "")) if isinstance(link, dict) else str(link) for link in page.navigation]
            parts += [str(v) for item in page.forms for v in item.values() if isinstance(v, str)]
    return "\n".join(str(p) for p in parts if p).lower()


def _allowed_goto(value: str, base_url: str, extra_hosts: list[str]) -> bool:
    if not re.match(r"^https?://", value, re.I):
        return True
    host = (urlparse(value).hostname or "").lower()
    allowed = {(urlparse(base_url).hostname or "").lower(), *[h.lower() for h in extra_hosts]}
    return host in allowed


def validate_script(
    script: TestScript,
    test_case: TestCase,
    locators: dict[str, LocatorSpec],
    corpus: str,
    base_url: str,
    extra_hosts: list[str] | None = None,
) -> TestScript | None:
    """Return a safe script or ``None`` if nothing usable remains. Never invents anything; only trims or weakens."""
    notes: list[str] = [script.notes] if script.notes else []
    steps: list[AutomationStep] = []
    for index, step in enumerate(script.steps, 1):
        problem = ""
        if step.action not in STEP_ACTIONS:
            problem = f"unsupported action {step.action}"
        elif step.action in ELEMENT_ACTIONS and (not step.element or step.element not in locators):
            problem = f"unknown element '{step.element}'"
        elif step.action in VALUE_ACTIONS and step.action != "press" and not (step.value or "").strip():
            problem = "missing value"
        elif step.action == "press" and not (step.value or "").strip():
            problem = "missing key"
        elif step.action == "goto" and not _allowed_goto(step.value or "", base_url, extra_hosts or []):
            problem = "navigation outside the allowed domains"
        if problem:
            notes.append(f"Script stopped at step {index}: {problem}.")
            break
        step = step.model_copy()
        if step.action not in ELEMENT_ACTIONS:
            step.element = None
        if step.action in {"expect_text", "expect_value"} and not ENV_RE.search(step.value or ""):
            if (step.value or "").strip().lower() not in corpus:
                notes.append(f"Step {index}: expected text {step.value!r} was not found in the test case or discovery evidence; checks visibility only.")
                step = step.model_copy(update={"action": "expect_visible", "value": None})
        steps.append(step)
    if not steps:
        return None
    if steps[0].action != "goto":
        first = next((s.element for s in steps if s.element), None)
        page_url = locators[first].page_url if first else ""
        path = urlparse(page_url).path or "/" if page_url else "/"
        steps.insert(0, AutomationStep(action="goto", value=path, description="Open the page under test"))
    return TestScript(test_case_id=test_case.test_case_id, title=script.title or test_case.title, notes=" ".join(notes), steps=steps)


def bracket_balanced(text: str) -> bool:
    """Cheap structural check for languages that cannot be parsed here (JS/TS/Java)."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            i = text.find("\n", i)
            if i < 0:
                break
        elif ch == "/" and nxt == "*":
            i = text.find("*/", i + 2)
            if i < 0:
                return False
            i += 1
        elif ch in "\"'`":
            quote = ch
            i += 1
            while i < n and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
                if quote != "`" and i < n and text[i] == "\n":
                    break
        elif ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
        i += 1
    return not stack


def check_syntax(files: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for rel, content in files.items():
        if rel.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as exc:
                problems.append(f"{rel}: line {exc.lineno}: {exc.msg}")
        elif rel.endswith((".ts", ".js", ".java")) and not bracket_balanced(content):
            problems.append(f"{rel}: unbalanced brackets or quotes")
        elif rel.endswith(".json"):
            try:
                json.loads(content)
            except ValueError as exc:
                problems.append(f"{rel}: invalid JSON ({exc})")
    return problems


# ----------------------------------------------------------------------------------------
# service
# ----------------------------------------------------------------------------------------
class ScriptService:
    def __init__(self, repo: Repository, store: BundleStore | None = None, agent: ScriptGenerationAgent | None = None) -> None:
        self.repo = repo
        self.store = store or BundleStore()
        self.agent = agent or ScriptGenerationAgent(repository=repo)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _elements_payload(locators: list[LocatorSpec], batch: list[TestCase], discovery: DiscoveryResult) -> list[dict[str, Any]]:
        wanted_pages = {
            p.page_key
            for p in discovery.pages
            for case in batch
            if case.related_page and case.related_page in {p.page_key, p.url, p.final_url, urlparse(p.final_url or p.url).path}
        }
        ordered = sorted(locators, key=lambda s: (s.page_key not in wanted_pages, s.page_key, s.element_key))
        return [
            {"key": s.element_key, "page": s.page_key, "page_url": s.page_url, "role": s.role or s.tag, "name": s.name, "intent": s.intent, "component": s.component}
            for s in ordered[:MAX_ELEMENTS]
        ]

    # ------------------------------------------------------------------ generation
    def generate(
        self,
        project: Project,
        framework: str | None = None,
        browser: str | None = None,
        on_event: EventCallback | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> int:
        framework = framework or project.framework
        browser = browser or project.browser
        if framework not in FRAMEWORKS:
            raise GenerationError("Choose a supported automation framework.")
        if browser not in browsers_for(framework):
            raise GenerationError(f"{browser} is not supported with {FRAMEWORKS[framework]['label']}.")
        say = progress or (lambda _m: None)
        cases = [t for t in self.repo.list_test_cases(project.id, status="approved") if t.automation_candidate]
        if not cases:
            raise GenerationError("Approve at least one automatable test case before generating automation.")
        discovery = self.repo.latest_successful_discovery(project.id)
        specs = self.repo.list_locators(project.id)
        if discovery is None or not specs:
            raise GenerationError("Run website discovery first so that real locators exist.")
        locators = {s.element_key: s for s in specs}
        base_url = project.app_base_url
        settings = get_settings()
        hosts = project.limits.allowed_domains
        scenarios = {s.scenario_id: s for s in self.repo.list_scenarios(project.id)}

        scripts: dict[str, TestScript] = {}
        skipped: list[dict[str, str]] = []
        for start in range(0, len(cases), BATCH_SIZE):
            batch = cases[start : start + BATCH_SIZE]
            say(f"Planning automation for test cases {start + 1}-{start + len(batch)} of {len(cases)}")
            payload = {
                "base_url": base_url, "test_cases": [t.model_dump() for t in batch], "elements": self._elements_payload(specs, batch, discovery),
                "page_digest": build_digest(discovery, max_items=20), "allowed_actions": STEP_ACTIONS,
            }  # fmt: skip
            plan = self.agent.plan(payload, project_id=project.id, on_event=on_event)
            planned = {s.test_case_id: s for s in plan.scripts}
            for case in batch:
                raw = planned.get(case.test_case_id)
                if raw is None:
                    skipped.append({"test_case_id": case.test_case_id, "reason": "The model returned no script for this test case."})
                    continue
                checked = validate_script(raw, case, locators, build_corpus(case, discovery), base_url, hosts)
                if checked is None:
                    skipped.append({"test_case_id": case.test_case_id, "reason": raw.notes or "No step could be mapped to a discovered element."})
                else:
                    scripts[case.test_case_id] = checked
        if not scripts:
            raise GenerationError("No test case could be converted into a validated automation script. See the skipped list for the reasons.")

        script_cases = [ScriptCase(test_case=c, script=scripts[c.test_case_id], module_key=c.module or "General") for c in cases if c.test_case_id in scripts]
        ctx = RenderContext(
            project=project, base_url=base_url, browser=browser, scenarios=scenarios, cases=script_cases, locators=locators,
            playwright_version=settings.execution.playwright_version, pages=[p.page_key for p in discovery.pages],
        )  # fmt: skip
        say("Rendering the automation project")
        files = get_adapter(framework).render(ctx)
        problems = check_syntax(files)
        if problems:
            raise GenerationError("The generated project failed the syntax check: " + "; ".join(problems[:3]))
        trace = build_traceability(script_cases, files, skipped, cases)
        plan_doc = {
            "scripts": [s.model_dump() for s in scripts.values()], "skipped": skipped, "framework": framework, "browser": browser,
            "base_url": base_url, "files": sorted(files),
        }  # fmt: skip
        bundle_id = self.repo.create_bundle(project.id, framework, browser, plan_doc, trace)
        self.store.write(project.id, bundle_id, files)
        self.repo.update_project(project.id, framework=framework, browser=browser)
        self.repo.audit(project.id, "agent:script", "automation.generated", "bundle", {"bundle": bundle_id, "framework": framework, "scripts": len(scripts), "skipped": len(skipped)})
        return bundle_id

    # ------------------------------------------------------------------ bundle operations
    def approve(self, project_id: str, bundle_id: int) -> None:
        self._require(project_id, bundle_id)
        self.repo.update_bundle(bundle_id, status="approved")
        self.repo.audit(project_id, "user", "automation.approved", "bundle", {"bundle": bundle_id})

    def _require(self, project_id: str, bundle_id: int) -> dict[str, Any]:
        bundle = self.repo.get_bundle(bundle_id)
        if not bundle or bundle["project_id"] != project_id:
            raise NotFoundError()
        return bundle

    def save_file(self, project_id: str, bundle_id: int, rel: str, content: str) -> None:
        """Manual edit of a generated file. The bundle goes back to draft and must be approved again."""
        self._require(project_id, bundle_id)
        problems = check_syntax({rel: content})
        if problems:
            raise GenerationError("The edited file has a problem: " + problems[0])
        self.store.write_file(project_id, bundle_id, rel, content)
        self.repo.update_bundle(bundle_id, status="draft")
        self.repo.audit(project_id, "user", "automation.file_edited", "bundle", {"bundle": bundle_id, "path": rel})

    def ai_edit_file(self, project_id: str, bundle_id: int, rel: str, instruction: str) -> str:
        bundle = self._require(project_id, bundle_id)
        if not instruction.strip():
            raise GenerationError("Describe the change you want.")
        current = self.store.read_file(project_id, bundle_id, rel)
        keys = sorted(self.store.load_locators(project_id, bundle_id))
        fixed = self.agent.fix(
            {"path": rel, "framework": bundle["framework"], "content": current, "instruction": instruction, "element_keys": keys[:200]},
            project_id=project_id,
        )
        problems = check_syntax({rel: fixed.content})
        if problems:
            raise GenerationError("The model's edit was rejected by the syntax check: " + problems[0])
        self.store.write_file(project_id, bundle_id, rel, fixed.content)
        self.repo.update_bundle(bundle_id, status="draft")
        self.repo.audit(project_id, "agent:script", "automation.file_ai_edited", "bundle", {"bundle": bundle_id, "path": rel, "instruction": instruction[:200]})
        return fixed.explanation
