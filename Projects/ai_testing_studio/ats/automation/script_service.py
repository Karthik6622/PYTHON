"""Automation planning: approved test cases -> validated scripts -> rendered framework project -> stored bundle."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from ats.ai.agents import MobileScriptAgent, ScriptGenerationAgent
from ats.api import design as api_design
from ats.automation.bundle_store import BundleStore
from ats.automation.script_grounding import Walk
from ats.automation.traceability import build_traceability
from ats.config import get_settings
from ats.discovery.facts import Evidence, facts_digest
from ats.discovery.service import build_digest
from ats.errors import GenerationError, ModelResponseError, NotFoundError
from ats.generation.adapters import FRAMEWORKS, RenderContext, ScriptCase, browsers_for, get_adapter, is_api_framework, layer_of
from ats.generation.adapters.common import NO_BROWSER, build_auth, build_views
from ats.generation.scenarios import page_names, resolve_page
from ats.mobile import design as mobile_design
from ats.mobile.models import MOBILE_ACTIONS
from ats.mobile.platforms import platform_for
from ats.progress import report
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
    """Text the application is known to show (discovery) plus the values the test itself types. The wording of the test case is NOT
    evidence: a model that invented a heading in its expected result would otherwise confirm itself."""
    parts = [*test_case.test_data.values()]
    if discovery:
        for page in discovery.pages:
            parts += [page.title, page.view_name, *page.headings, *page.messages, *page.texts]
            for element in page.elements:
                parts += [str(element.get(k) or "") for k in ("name", "label", "text", "placeholder", "value")]
            parts += [str(link.get("text", "")) if isinstance(link, dict) else str(link) for link in page.navigation]
            parts += [str(v) for item in page.forms for v in item.values() if isinstance(v, str)]
            for outcome in page.outcomes:
                parts += [str(outcome.get("result", "")), *[str(m) for m in outcome.get("shown_messages", [])]]
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
    evidence: Evidence | None = None,
    views: dict[str, Any] | None = None,
) -> TestScript | None:
    """Return a complete grounded script, never a passing prefix of an incomplete test."""
    return _check_script(script, test_case, locators, corpus, base_url, extra_hosts or [], evidence, views or {})[0]


def _check_script(
    script: TestScript, test_case: TestCase, locators: dict[str, LocatorSpec], corpus: str, base_url: str,
    extra_hosts: list[str], evidence: Evidence | None, views: dict[str, Any],
) -> tuple[TestScript | None, str]:
    notes: list[str] = [script.notes] if script.notes else []
    walk = Walk(locators, evidence, views or {})
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
            return None, f"Step {index}: {problem}."
        step = step.model_copy()
        if step.action not in ELEMENT_ACTIONS:
            step.element = None
        if step.action in {"expect_url_contains", "expect_title_contains"}:
            kept, _ = walk.ground_page_checks(index, step)
            if kept is None:
                return None, walk.notes[-1]
            step = kept
        grounded, why = walk.check(index, step)
        if grounded is None:
            return None, why
        step = grounded
        if evidence is None and step.action in {"expect_text", "expect_value"} and not ENV_RE.search(step.value or ""):
            if (step.value or "").strip().lower() not in corpus:
                return None, f"Step {index}: expected value is not supported by discovery."
        steps.append(step)
    notes.extend(walk.notes)
    if not any(s.action.startswith("expect_") for s in steps):
        return None, script.notes or "The plan contains no observable assertion."
    if steps[0].action != "goto":
        first = next((s.element for s in steps if s.element), None)
        page_url = locators[first].page_url if first else ""
        path = urlparse(page_url).path or "/" if page_url else "/"
        steps.insert(0, AutomationStep(action="goto", value=path, description="Open the page under test"))
    return TestScript(test_case_id=test_case.test_case_id, title=script.title or test_case.title, notes=" ".join(notes), steps=steps), ""


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
        elif rel.endswith((".ts", ".js", ".java")) and rel != "utils/actions.js" and not bracket_balanced(content):  # actions.js uses regex literals
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
    def __init__(
        self, repo: Repository, store: BundleStore | None = None, agent: ScriptGenerationAgent | None = None, connections: Any = None, mobile_agent: MobileScriptAgent | None = None
    ) -> None:
        self.repo = repo
        self.store = store or BundleStore()
        self.agent = agent or ScriptGenerationAgent(repository=repo)
        self._mobile_agent = mobile_agent
        self.connections = connections  # saved connections: their descriptors (variable NAMES) go into generated API projects

    @property
    def mobile_agent(self) -> MobileScriptAgent:
        if self._mobile_agent is None:
            self._mobile_agent = MobileScriptAgent(repository=self.repo)
        return self._mobile_agent

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _elements_payload(locators: list[LocatorSpec], batch: list[TestCase], discovery: DiscoveryResult) -> list[dict[str, Any]]:
        known = {p.page_key for p in discovery.pages}
        names = page_names(discovery)
        wanted_pages = {resolve_page(case.related_page, known, names) for case in batch} & known
        signed = {p.page_key: p.signed_in for p in discovery.pages}
        ordered = sorted(locators, key=lambda s: (s.page_key not in wanted_pages, s.page_key, s.element_key))
        out = []
        for s in ordered[:MAX_ELEMENTS]:
            item = {
                "key": s.element_key, "page": s.page_key, "signed_in": signed.get(s.page_key, False), "role": s.role or s.tag, "name": s.name,
                "intent": s.intent, "component": s.component,
            }  # fmt: skip
            shown = (s.evidence or {}).get("text") or ""
            if shown and shown != s.name:
                item["text"] = shown[:80]
            if (s.evidence or {}).get("options"):
                item["options"] = s.evidence["options"][:10]
            out.append(item)
        return out

    # ------------------------------------------------------------------ generation
    def generate(
        self,
        project: Project,
        framework: str | None = None,
        browser: str | None = None,
        on_event: EventCallback | None = None,
        progress: Callable[[str], None] | None = None,
        layer: str | None = None,
    ) -> int:
        layer = layer or (layer_of(framework) if framework else "ui")
        if layer == "api":
            return self._generate_api(project, progress)
        if layer == "mobile":
            return self._generate_mobile(project, on_event, progress)
        framework = framework or project.framework
        browser = browser or project.browser
        if framework not in FRAMEWORKS or is_api_framework(framework) or layer_of(framework) == "mobile":
            raise GenerationError("Choose a supported automation framework.")
        if browser not in browsers_for(framework):
            raise GenerationError(f"{browser} is not supported with {FRAMEWORKS[framework]['label']}.")
        cases = [t for t in self.repo.list_test_cases(project.id, status="approved", layer="ui") if t.automation_candidate]
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
        evidence, views = Evidence(discovery, locators), build_views(discovery)
        known_views, names = {p.page_key for p in discovery.pages}, page_names(discovery)
        batches = -(-len(cases) // BATCH_SIZE)
        for number, start in enumerate(range(0, len(cases), BATCH_SIZE)):
            batch = cases[start : start + BATCH_SIZE]
            report(
                progress, f"Planning automation for test cases {start + 1}-{start + len(batch)} of {len(cases)}",
                0.02 + 0.85 * number / batches, 0.02 + 0.85 * (number + 1) / batches,
            )
            batch_views = {resolve_page(c.related_page, known_views, names) for c in batch} & known_views
            payload = {
                "base_url": base_url, "test_cases": [t.model_dump() for t in batch], "elements": self._elements_payload(specs, batch, discovery),
                "page_digest": facts_digest(discovery, only=batch_views or None, max_controls=30), "allowed_actions": STEP_ACTIONS,
            }  # fmt: skip
            payload["replay_start_view"] = framework == "playwright_python"
            try:
                plan = self.agent.plan(payload, project_id=project.id, on_event=on_event)
                planned = {s.test_case_id: s for s in plan.scripts}
            except ModelResponseError:
                planned = {}
            for case in batch:
                raw = planned.get(case.test_case_id)
                def validate(candidate: TestScript | None) -> tuple[TestScript | None, str]:
                    if candidate is None:
                        return None, "The model returned no script for this case."
                    checked, reason = _check_script(candidate, case, locators, build_corpus(case, discovery), base_url, hosts, evidence, views)
                    if checked and payload["replay_start_view"] and case.related_page in known_views:
                        first = next((locators[s.element].page_key for s in checked.steps if s.element), None)
                        if first and first != case.related_page:
                            return None, f"First control is on {first}, not the case's starting view {case.related_page}."
                    return checked, reason

                checked, reason = validate(raw)
                if checked is None:
                    retry = {**payload, "test_cases": [case.model_dump()], "elements": self._elements_payload(specs, [case], discovery),
                             "validation_feedback": reason}
                    try:
                        replanned = self.agent.plan(retry, project_id=project.id, on_event=on_event)
                        checked, reason = validate(next((s for s in replanned.scripts if s.test_case_id == case.test_case_id), None))
                    except ModelResponseError as exc:
                        reason = f"{reason} Replan failed: {exc.user_message}"
                if checked is None:
                    skipped.append({"test_case_id": case.test_case_id, "reason": reason})
                else:
                    scripts[case.test_case_id] = checked
        if not scripts:
            raise GenerationError("No complete automation scripts: " + "; ".join(f"{s['test_case_id']}: {s['reason']}" for s in skipped[:3]))

        script_cases = [ScriptCase(test_case=c, script=scripts[c.test_case_id], module_key=c.module or "General") for c in cases if c.test_case_id in scripts]
        ctx = RenderContext(
            project=project, base_url=base_url, browser=browser, scenarios=scenarios, cases=script_cases, locators=locators,
            playwright_version=settings.execution.playwright_version, pages=[p.page_key for p in discovery.pages],
            views=build_views(discovery), auth=build_auth(project),
        )  # fmt: skip
        report(progress, "Rendering the automation project", 0.9)
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

    def _generate_api(self, project: Project, progress: Callable[[str], None] | None = None) -> int:
        """API tests need no model planning: the approved test cases already hold the structured requests."""
        cases = [t for t in self.repo.list_test_cases(project.id, status="approved", layer="api") if t.automation_candidate]
        if not cases:
            raise GenerationError("Approve at least one automatable API test case before generating the API automation project.")
        endpoints = self.repo.list_api_endpoints(project.id)
        if not endpoints:
            raise GenerationError("There are no API endpoints. Import a definition on the API page first.")
        descriptors = self.connections.descriptors(project.id) if self.connections is not None else {}
        report(progress, "Checking the API test cases against the definition", 0.1)
        usable: list[TestCase] = []
        skipped: list[dict[str, str]] = []
        for case in cases:
            checked, reason = api_design.validate_requests(case, endpoints, sorted(descriptors))
            if checked is None:
                skipped.append({"test_case_id": case.test_case_id, "reason": reason})
            else:
                usable.append(checked)
        if not usable:
            raise GenerationError("No API test case could be automated: " + (skipped[0]["reason"] if skipped else "no requests") + ".")
        scenarios = {s.scenario_id: s for s in self.repo.list_scenarios(project.id)}
        script_cases = [
            ScriptCase(test_case=c, script=TestScript(test_case_id=c.test_case_id, title=c.title, steps=[]), module_key=c.module or "General") for c in usable
        ]
        summary = [
            {"key": e.key, "summary": e.summary, "tags": e.tags, "statuses": [r.status for r in e.responses], "security": [s.scheme for s in e.security]} for e in endpoints
        ]
        ctx = RenderContext(
            project=project, base_url=project.api_url, browser=NO_BROWSER, scenarios=scenarios, cases=script_cases, locators={},
            api_config={"connections": descriptors, "endpoints": summary},
        )  # fmt: skip
        report(progress, "Rendering the API test project", 0.6)
        files = get_adapter("api_python").render(ctx)
        problems = check_syntax(files)
        if problems:
            raise GenerationError("The generated project failed the syntax check: " + "; ".join(problems[:3]))
        trace = build_traceability(script_cases, files, skipped, cases)
        requests = {c.test_case_id: len(c.api.requests) for c in usable if c.api}
        for row in trace:
            row["steps"] = requests.get(row["test_case_id"], 0)
        plan_doc = {
            "scripts": [], "skipped": skipped, "framework": "api_python", "browser": NO_BROWSER, "base_url": project.api_url, "files": sorted(files), "layer": "api",
            "endpoints": len(endpoints), "connections": sorted(descriptors),
        }  # fmt: skip
        bundle_id = self.repo.create_bundle(project.id, "api_python", NO_BROWSER, plan_doc, trace, layer="api")
        self.store.write(project.id, bundle_id, files)
        self.repo.audit(project.id, "system", "automation.generated", "bundle", {"bundle": bundle_id, "framework": "api_python", "layer": "api", "tests": len(usable), "skipped": len(skipped)})
        return bundle_id

    def _generate_mobile(self, project: Project, on_event: EventCallback | None = None, progress: Callable[[str], None] | None = None) -> int:
        """Mobile tests: the model plans steps on the analysed elements, validation drops everything it cannot ground, the adapter renders Appium code."""
        cases = [t for t in self.repo.list_test_cases(project.id, status="approved", layer="mobile") if t.automation_candidate]
        if not cases:
            raise GenerationError("Approve at least one automatable mobile test case before generating the mobile automation project.")
        analysis = self.repo.get_mobile_analysis(project.id)
        if analysis is None:
            raise GenerationError("Analyze the app on the Mobile page first so that real elements exist.")
        config = self.repo.get_mobile_config(project.id)
        platform = platform_for(config.platform)
        elements = analysis.elements()
        scripts: dict[str, Any] = {}
        skipped: list[dict[str, str]] = []
        batches = -(-len(cases) // BATCH_SIZE)
        for number, start in enumerate(range(0, len(cases), BATCH_SIZE)):
            batch = cases[start : start + BATCH_SIZE]
            report(
                progress, f"Planning automation for mobile test cases {start + 1}-{start + len(batch)} of {len(cases)}",
                0.02 + 0.85 * number / batches, 0.02 + 0.85 * (number + 1) / batches,
            )
            plan = self.mobile_agent.plan(mobile_design.script_payload(project, config, analysis, batch, MOBILE_ACTIONS), project_id=project.id, on_event=on_event)
            planned = {s.test_case_id: s for s in plan.scripts}
            for case in batch:
                raw = planned.get(case.test_case_id)
                if raw is None:
                    skipped.append({"test_case_id": case.test_case_id, "reason": "The model returned no script for this test case."})
                    continue
                checked = mobile_design.validate_script(raw, case, elements, mobile_design.build_corpus(case, analysis))
                if checked is None:
                    skipped.append({"test_case_id": case.test_case_id, "reason": raw.notes or "No step could be mapped to an analysed element."})
                else:
                    scripts[case.test_case_id] = checked
        if not scripts:
            raise GenerationError("No mobile test case could be converted into a validated automation script. See the skipped list for the reasons.")
        scenarios = {s.scenario_id: s for s in self.repo.list_scenarios(project.id)}
        script_cases = [ScriptCase(test_case=c, script=scripts[c.test_case_id], module_key=c.module or "General") for c in cases if c.test_case_id in scripts]
        mobile = {
            "platform": config.platform, "package": analysis.package or config.package, "activity": analysis.activity or config.activity,
            "capabilities": platform.bundle_capabilities(config.model_copy(update={"package": analysis.package or config.package, "activity": analysis.activity or config.activity})),
            "screens": [s.model_dump(exclude={"fingerprint"}) for s in analysis.screens],
        }  # fmt: skip
        ctx = RenderContext(project=project, base_url="", browser=NO_BROWSER, scenarios=scenarios, cases=script_cases, locators={}, mobile=mobile)
        report(progress, "Rendering the mobile test project", 0.9)
        files = get_adapter("appium_python").render(ctx)
        problems = check_syntax(files)
        if problems:
            raise GenerationError("The generated project failed the syntax check: " + "; ".join(problems[:3]))
        trace = build_traceability(script_cases, files, skipped, cases)
        plan_doc = {
            "scripts": [s.model_dump() for s in scripts.values()], "skipped": skipped, "framework": "appium_python", "browser": NO_BROWSER, "base_url": "", "files": sorted(files),
            "layer": "mobile", "package": mobile["package"], "screens": len(analysis.screens),
        }  # fmt: skip
        bundle_id = self.repo.create_bundle(project.id, "appium_python", NO_BROWSER, plan_doc, trace, layer="mobile")
        self.store.write(project.id, bundle_id, files)
        self.repo.audit(project.id, "agent:mobile_script", "automation.generated", "bundle", {"bundle": bundle_id, "framework": "appium_python", "layer": "mobile", "tests": len(scripts), "skipped": len(skipped)})
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
