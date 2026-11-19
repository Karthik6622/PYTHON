"""Benchmark: discover the bench target app, build a Playwright-Python project from hand-written scripts (no AI) and run it
with the studio's own executor. Writes bench/baseline_report.json (or --report) and bench/baseline_project/ (or --project-dir).

Usage (from the project folder, i.e. the folder that contains ``ats`` and ``bench``):
    .venv/Scripts/python.exe bench/run_bench.py [--report bench/x.json] [--project-dir bench/x_project] [--discover-only] [--no-server]

Everything (data folder, database, credentials, the Streamlit target on port 8611) is set up by this script.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from collections import Counter
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BENCH_DIR.parent
PORT = 8611
TARGET_URL = f"http://localhost:{PORT}"
USERNAME = "[REDACTED_EMAIL_ADDRESS_1]"
PASSWORD = "Secret123"


# ----------------------------------------------------------------------------------------
# environment (must be set before anything from ats is imported: settings are cached)
# ----------------------------------------------------------------------------------------
def prepare_environment(autofix: bool = False) -> Path:
    data_dir = Path(tempfile.mkdtemp(prefix="ats_bench_"))
    os.environ.update({
        "DATA_DIR": str(data_dir),
        "DATABASE_URL": "sqlite:///" + str(data_dir / "studio.db").replace("\\", "/"),
        "MODEL_API_KEY": "", "NVIDIA_API_KEY": "",
        "ALLOW_PRIVATE_NETWORK": "true", "EXECUTION_MODE": "local",
        "AUTOFIX_MAX_ROUNDS": "3" if autofix else "0", "RECHECK_FLAKY": "false",
        "TEST_APP_USERNAME": USERNAME, "TEST_APP_PASSWORD": PASSWORD,
    })  # fmt: skip
    sys.path.insert(0, str(PROJECT_DIR))
    os.chdir(PROJECT_DIR)
    import ats.config as config  # noqa: PLC0415 - the benchmark never reads .streamlit/secrets.toml (no AI, no real keys)

    config._secret = lambda name: os.environ.get(name) or None  # type: ignore[assignment]
    return data_dir


def fail(message: str) -> None:
    print(f"\nBENCHMARK ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


# ----------------------------------------------------------------------------------------
# target app
# ----------------------------------------------------------------------------------------
def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_target(log_path: Path, hard: bool = False) -> subprocess.Popen | None:
    if port_open(PORT):
        fail(f"Port {PORT} is already in use. Stop whatever runs there (an old target app?) or pass --no-server to reuse it.")
    log = log_path.open("w", encoding="utf-8")
    cmd = [sys.executable, "-m", "streamlit", "run", str(BENCH_DIR / "target_app.py"), "--server.port", str(PORT),
           "--server.headless", "true", "--browser.gatherUsageStats", "false"]  # fmt: skip
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_DIR), stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "BENCH_HARD": "1" if hard else "0"})
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            fail(f"The Streamlit target exited with code {proc.returncode}; see {log_path}")
        try:
            with urllib.request.urlopen(f"{TARGET_URL}/_stcore/health", timeout=2) as resp:
                if resp.status == 200:
                    return proc
        except OSError:
            pass
        time.sleep(0.5)
    proc.kill()
    fail(f"The Streamlit target did not become healthy within 60 s; see {log_path}")
    return None


def stop_target(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


# ----------------------------------------------------------------------------------------
# element picking: test cases refer to elements by (role, name, view); keys come from the discovered repository
# ----------------------------------------------------------------------------------------
class Picker:
    def __init__(self, specs: list, discovery) -> None:  # noqa: ANN001
        self.specs = specs
        self.pages = {p.page_key: p for p in discovery.pages}

    def view_text(self, page_key: str) -> str:
        page = self.pages.get(page_key)
        if page is None:
            return page_key.lower()
        return " ".join([page_key, page.view_name or "", page.title or "", *page.headings]).lower()

    def find(self, role: str, name: str, view: str = "", signed_in: bool | None = None) -> str | None:
        """Key of the element with this role and (case-insensitive, exact or regex) name, preferring the given view."""
        pattern = re.compile(name, re.I)
        hits = []
        for spec in self.specs:
            if role and (spec.role or spec.tag or "").lower() != role:
                continue
            if not pattern.fullmatch((spec.name or "").strip()):
                continue
            page = self.pages.get(spec.page_key)
            if signed_in is not None and page is not None and page.signed_in != signed_in:
                continue
            hits.append(spec)
        if not hits:
            return None

        def score(spec) -> tuple:  # noqa: ANN001
            page = self.pages.get(spec.page_key)
            name_hit = bool(view) and view.lower() in (page.view_name or "").lower() if page else False
            text_hit = bool(view) and view.lower() in self.view_text(spec.page_key)
            return (not name_hit, not text_hit, -spec.stability, spec.element_key)

        return sorted(hits, key=score)[0].element_key


# ----------------------------------------------------------------------------------------
# the test cases a QA engineer would write for the target
# step: (action, element_ref or None, value or None, description); element_ref = (role, name regex, view, signed_in)
# ----------------------------------------------------------------------------------------
L = ("button", "Get started", "landing", False)
CREATE = ("button", "Create account", "landing", False)
EMAIL = ("textbox", "Email", "Get started", False)
PASSWORD_BOX = ("textbox", "Password", "Get started", False)
LOGIN = ("button", "Log ?in", "Get started", False)
CHAT_MSG = ("textbox", "Message", "Chat", True)
SEND = ("button", "Send", "Chat", True)
CHAT_H = ("heading", "Chat", "Chat", True)
NAME = ("textbox", "Display name", "Profile", True)
CITY = ("textbox", "City", "Profile", True)
SAVE_PROFILE = ("button", "Save profile", "Profile", True)
EMAIL_NOTIF = ("checkbox", "Email notifications", "Settings", True)
THEME = ("combobox", "(Selected .*\\. )?Theme|Theme.*", "Settings", True)
SAVE_SETTINGS = ("button", "Save settings", "Settings", True)
RADIO_CHAT = ("radio", "Chat", "", True)
RADIO_PROFILE = ("radio", "Profile", "", True)
RADIO_SETTINGS = ("radio", "Settings", "", True)
SIGN_OUT = ("button", "Sign out", "", True)

CASES = [
    ("TC_LND_001", "Landing", "Landing page shows the Get started button", "The Get started button is visible",
     [("expect_visible", L, None, "Get started is shown")]),
    ("TC_LND_002", "Landing", "Landing page offers account creation", "The Create account button is visible and enabled",
     [("expect_visible", CREATE, None, "Create account is shown"), ("expect_enabled", CREATE, None, "Create account is enabled")]),
    ("TC_LND_003", "Landing", "Get started opens the sign-in form", "Email and Password fields and the Log in button are visible",
     [("click", L, None, "Click Get started"), ("expect_visible", EMAIL, None, "Email field is visible"),
      ("expect_visible", PASSWORD_BOX, None, "Password field is visible"), ("expect_visible", LOGIN, None, "Log in button is visible")]),
    ("TC_LOG_001", "Login", "Invalid credentials keep the user on the sign-in form", "Invalid email or password; the Log in button stays visible",
     [("fill", EMAIL, "wrong@example.com", "Enter a wrong email"), ("fill", PASSWORD_BOX, "nope", "Enter a wrong password"),
      ("click", LOGIN, None, "Click Log in"), ("expect_visible", LOGIN, None, "Still on the sign-in form")]),
    ("TC_LOG_002", "Login", "Valid credentials sign the user in", "The sidebar navigation and the chat view are shown",
     [("fill", EMAIL, "{{env:TEST_APP_USERNAME}}", "Enter the email"), ("fill", PASSWORD_BOX, "{{env:TEST_APP_PASSWORD}}", "Enter the password"),
      ("click", LOGIN, None, "Click Log in"), ("expect_visible", RADIO_CHAT, None, "Navigation is shown"),
      ("expect_visible", SEND, None, "Chat view is shown")]),
    ("TC_LOG_003", "Login", "Password visibility can be toggled", "Hide password button appears after Show password",
     [("click", ("button", "Show password", "Get started", False), None, "Click Show password"),
      ("expect_visible", ("button", "Hide password", "show_password", False), None, "Hide password is shown")]),
    ("TC_CHT_001", "Chat", "Chat view shows the message box", "Message box and Send button are visible",
     [("expect_visible", CHAT_MSG, None, "Message box is visible"), ("expect_visible", SEND, None, "Send button is visible")]),
    ("TC_CHT_002", "Chat", "Sending a message", "Message sent",
     [("fill", CHAT_MSG, "Hello there", "Type a message"), ("expect_value", CHAT_MSG, "Hello there", "The message is typed"),
      ("click", SEND, None, "Click Send"), ("expect_visible", CHAT_MSG, None, "Message box still available")]),
    ("TC_PRF_001", "Profile", "Profile form shows its fields", "Display name, City and Save profile are visible",
     [("expect_visible", NAME, None, "Display name is visible"), ("expect_visible", CITY, None, "City is visible"),
      ("expect_visible", SAVE_PROFILE, None, "Save profile is visible")]),
    ("TC_PRF_002", "Profile", "Saving the profile", "Profile saved",
     [("fill", NAME, "Karthik", "Enter a display name"), ("fill", CITY, "Chennai", "Enter a city"),
      ("click", SAVE_PROFILE, None, "Click Save profile"), ("expect_value", CITY, "Chennai", "City keeps the value")]),
    ("TC_SET_001", "Settings", "Settings view shows its controls", "Email notifications, Theme and Save settings are visible",
     [("expect_visible", EMAIL_NOTIF, None, "Email notifications is visible"), ("expect_visible", THEME, None, "Theme is visible"),
      ("expect_visible", SAVE_SETTINGS, None, "Save settings is visible")]),
    ("TC_SET_002", "Settings", "Saving the settings", "Settings saved",
     [("check", EMAIL_NOTIF, None, "Turn on email notifications"), ("click", SAVE_SETTINGS, None, "Click Save settings"),
      ("expect_visible", SAVE_SETTINGS, None, "Save settings still visible")]),
    ("TC_NAV_001", "Navigation", "Sidebar navigation reaches Profile and Settings", "Profile and Settings views open from the sidebar",
     [("click", RADIO_PROFILE, None, "Choose Profile"), ("expect_visible", NAME, None, "Profile form is shown"),
      ("click", RADIO_SETTINGS, None, "Choose Settings"), ("expect_visible", SAVE_SETTINGS, None, "Settings form is shown"),
      ("click", RADIO_CHAT, None, "Choose Chat"), ("expect_visible", SEND, None, "Chat is shown")]),
    ("TC_NAV_002", "Navigation", "Sign out returns to the landing page", "The Get started button is visible again",
     [("expect_visible", SIGN_OUT, None, "Sign out is shown"), ("click", SIGN_OUT, None, "Click Sign out"),
      ("expect_visible", L, None, "Landing page is shown")]),
]  # fmt: skip


def build_scripts(picker: Picker, project, discovery):  # noqa: ANN001, ANN201
    from ats.automation.script_service import build_corpus, validate_script
    from ats.models import AutomationStep, TestCase, TestScript

    locators = {s.element_key: s for s in picker.specs}
    cases, scripts, unmapped, mapping = [], {}, [], {}
    for tc_id, module, title, expected, steps in CASES:
        case = TestCase(test_case_id=tc_id, scenario_id=f"SC_{tc_id[3:6]}_001", module=module, title=title, steps=[s[3] for s in steps],
                        expected_result=expected, status="approved", source="bench")  # fmt: skip
        built, problem = [], ""
        for action, ref, value, description in steps:
            key = None
            if ref is not None:
                key = picker.find(*ref)
                mapping[str(ref)] = key
                if key is None:
                    problem = f"no discovered element for {ref[0]} '{ref[1]}' (view hint '{ref[2]}')"
                    break
            built.append(AutomationStep(action=action, element=key, value=value, description=description))
        if problem:
            unmapped.append({"test_case_id": tc_id, "reason": problem})
            if not built:
                continue
        raw = TestScript(test_case_id=tc_id, title=title, steps=built, notes=f"Truncated: {problem}" if problem else "")
        checked = validate_script(raw, case, locators, build_corpus(case, discovery), project.app_base_url, project.limits.allowed_domains)
        if checked is None:
            unmapped.append({"test_case_id": tc_id, "reason": "validation removed every step"})
            continue
        cases.append(case)
        scripts[tc_id] = checked
    return cases, scripts, unmapped, mapping


def render(project, discovery, specs, cases, scripts) -> dict[str, str]:  # noqa: ANN001
    from ats.automation.script_service import check_syntax
    from ats.config import get_settings
    from ats.generation.adapters import RenderContext, ScriptCase, get_adapter
    from ats.generation.adapters.common import build_auth, build_views
    from ats.models import Scenario

    scenarios = {c.scenario_id: Scenario(scenario_id=c.scenario_id, title=c.module, module=c.module, status="approved") for c in cases}
    ctx = RenderContext(
        project=project, base_url=project.app_base_url, browser="chromium", scenarios=scenarios,
        cases=[ScriptCase(test_case=c, script=scripts[c.test_case_id], module_key=c.module) for c in cases],
        locators={s.element_key: s for s in specs}, playwright_version=get_settings().execution.playwright_version,
        pages=[p.page_key for p in discovery.pages], views=build_views(discovery), auth=build_auth(project),
    )  # fmt: skip
    files = get_adapter("playwright_python").render(ctx)
    problems = check_syntax(files)
    if problems:
        fail("The rendered project failed the syntax check: " + "; ".join(problems[:3]))
    return files


def classify(message: str) -> str:
    text = message.lower()
    if "could not reach" in text:
        return "view_not_reached"
    if "strict mode violation" in text:
        return "ambiguous_locator"
    if "timeout" in text or "not found" in text or "waiting for" in text:
        return "timeout_or_not_found"
    if "sign" in text and ("in" in text) and "session" in text:
        return "sign_in"
    return "other"


def main() -> int:  # noqa: C901, PLR0915
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", default=str(BENCH_DIR / "baseline_report.json"))
    parser.add_argument("--project-dir", default=str(BENCH_DIR / "baseline_project"))
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--no-server", action="store_true", help="reuse a target app already running on port 8611")
    parser.add_argument("--hard", action="store_true", help="run the tests against the CHANGED app (BENCH_HARD=1): slower, extra primary button, renamed button")
    parser.add_argument("--autofix", action="store_true", help="after the run, let the studio repair the failures (3 attempts) and report the outcome")
    args = parser.parse_args()

    data_dir = prepare_environment(args.autofix)
    import ats  # noqa: PLC0415

    ats_path = Path(ats.__file__).resolve()
    if PROJECT_DIR not in ats_path.parents:
        fail(f"'ats' was imported from {ats_path}, not from {PROJECT_DIR}")
    from ats.config import get_settings  # noqa: PLC0415

    if get_settings().model.configured:
        fail("An AI model is configured (MODEL_API_KEY / NVIDIA_API_KEY or Streamlit secrets); the benchmark must run without AI.")
    print(f"ats package: {ats_path.parent}\ndata dir:    {data_dir}")

    report: dict = {"ats_path": str(ats_path.parent), "data_dir": str(data_dir), "target": TARGET_URL}
    proc = None if args.no_server else start_target(data_dir / "target_app.log")
    try:
        from ats.models import AuthConfig, DiscoveryLimits  # noqa: PLC0415
        from ats.services import build_services  # noqa: PLC0415

        svc = build_services()
        project = svc.repo.create_project(
            "b" * 32, name="PersonalPartner bench", url=TARGET_URL,
            auth=AuthConfig(mode="env_credentials", username_env="TEST_APP_USERNAME", password_env="TEST_APP_PASSWORD"),
            limits=DiscoveryLimits(max_pages=10, max_depth=3),
        )  # fmt: skip

        print("\n== Discovery ==")
        t0 = time.time()
        try:
            discovery = svc.discovery.run(project, on_progress=None)
        except Exception as exc:  # noqa: BLE001
            fail(f"Discovery failed: {getattr(exc, 'user_message', '') or exc}")
        report["discovery_seconds"] = round(time.time() - t0, 1)
        specs = svc.repo.list_locators(project.id)
        views = []
        for page in discovery.pages:
            views.append({"page_key": page.page_key, "view_name": page.view_name, "signed_in": page.signed_in, "url": page.final_url or page.url,
                          "nav_steps": page.nav_steps, "elements": len(page.elements)})  # fmt: skip
            print(f"- {page.page_key:<28} view={page.view_name!r} signed_in={page.signed_in} elements={len(page.elements)}")
            for step in page.nav_steps:
                print(f"      nav: {json.dumps(step)}")
        report["views"] = views
        report["discovery_warnings"] = discovery.warnings
        if discovery.warnings:
            print("warnings:", *discovery.warnings, sep="\n  ")
        print(f"\n== Locator repository ({len(specs)}) ==")
        repo_rows = []
        for spec in specs:
            row = {"key": spec.element_key, "page": spec.page_key, "role": spec.role or spec.tag, "name": spec.name,
                   "preferred": spec.preferred.display(), "alternatives": [a.kind for a in spec.alternatives], "stability": spec.stability}  # fmt: skip
            repo_rows.append(row)
            print(f"- {row['key']:<45} {row['preferred']:<60} alts={','.join(row['alternatives'])} stab={row['stability']}")
        report["locators"] = repo_rows
        if args.discover_only:
            return 0

        print("\n== Automation (no AI) ==")
        picker = Picker(specs, discovery)
        cases, scripts, unmapped, mapping = build_scripts(picker, project, discovery)
        report["element_mapping"] = mapping
        report["unmapped"] = unmapped
        for item in unmapped:
            print(f"  ! {item['test_case_id']}: {item['reason']}")
        if not scripts:
            fail("No test case could be mapped to discovered elements.")
        svc.repo.save_test_cases(project.id, cases)
        files = render(project, discovery, specs, cases, scripts)
        out = Path(args.project_dir)
        shutil.rmtree(out, ignore_errors=True)
        for rel, content in files.items():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text(content, encoding="utf-8", newline="\n")
        report["scripts"] = {k: [s.model_dump() for s in v.steps] for k, v in scripts.items()}
        print(f"  {len(scripts)} scripts rendered into {len(files)} files -> {out}")

        if args.hard and not args.no_server:
            print("\n== The application changes (BENCH_HARD=1) ==")
            stop_target(proc)
            time.sleep(1)
            proc = start_target(data_dir / "target_app_hard.log", hard=True)

        print("\n== Execution ==")
        t0 = time.time()
        try:
            execution_id = svc.executor.run(
                project, files, secrets={"TEST_APP_USERNAME": USERNAME, "TEST_APP_PASSWORD": PASSWORD},
                framework="playwright_python", browser="chromium", mode="local", analyze=False,
            )  # fmt: skip
        except Exception as exc:  # noqa: BLE001
            fail(f"Execution failed to start: {exc}")
        run_seconds = time.time() - t0
        execution = svc.repo.get_execution(execution_id) or {}
        if execution.get("status") != "completed":
            print(svc.executor.log_tail(project.id, execution_id, 60))
            fail(f"Execution ended with status {execution.get('status')}: {execution.get('error')}")
        results = svc.repo.list_results(execution_id)
        rows, failures = [], Counter()
        for r in results:
            failure = (r.get("evidence") or {}).get("failure") or {}
            row = {"test_case_id": r["test_case_id"], "status": r["status"], "duration": r.get("duration"), "message": (r.get("message") or "")[:300]}
            if r["status"] != "PASS":
                key = failure.get("element") or ""
                spec = next((s for s in specs if s.element_key == key), None)
                row.update({"failed_step": failure.get("step"), "failed_action": failure.get("action"), "failed_element": key,
                            "preferred": spec.preferred.display() if spec else "", "category": classify(r.get("message") or failure.get("error") or "")})  # fmt: skip
                failures[row["category"]] += 1
            if (r.get("evidence") or {}).get("fallbacks"):
                row["fallbacks"] = r["evidence"]["fallbacks"]
            rows.append(row)
        totals = execution.get("totals") or {}
        passed = sum(r["status"] == "PASS" for r in rows)
        report.update({
            "execution_id": execution_id, "tests": len(rows), "passed": passed, "failed": len(rows) - passed,
            "run_seconds": round(run_seconds, 1), "seconds_per_test": round(run_seconds / max(len(rows), 1), 1),
            "executor_duration": totals.get("duration"), "failure_types": dict(failures), "results": rows,
            "log_tail": svc.executor.log_tail(project.id, execution_id, 40),
        })  # fmt: skip
        print()
        for row in rows:
            extra = f"  [{row.get('category')}] {row.get('failed_action')} {row.get('failed_element')} ({row.get('preferred')}): {row['message'][:160]!r}" if row["status"] != "PASS" else ""
            print(f"  {row['test_case_id']:<11} {row['status']:<5} {row['duration'] or 0:6.1f}s{extra}")
        print(f"\nSUMMARY: tests={len(rows)} passed={passed} failed={len(rows) - passed} unmapped={len(unmapped)} "
              f"run={run_seconds:.1f}s per_test={run_seconds / max(len(rows), 1):.1f}s failure_types={dict(failures)}")  # fmt: skip
        if args.autofix:
            print("\n== Auto-fix (3 attempts, no AI model) ==")
            secrets = {"TEST_APP_USERNAME": USERNAME, "TEST_APP_PASSWORD": PASSWORD}
            t0 = time.time()
            svc.analysis.post_run(svc.analysis.context_for(project, execution_id, secrets))
            fix_seconds = time.time() - t0
            final = {r["test_case_id"]: r["status"] for r in svc.repo.list_results(execution_id)}
            summary = ((svc.repo.get_execution(execution_id) or {}).get("totals") or {}).get("autofix") or {}
            report.update({"autofix_seconds": round(fix_seconds, 1), "final_status": final, "autofix_summary": summary})
            for tc, status in sorted(final.items()):
                print(f"  {tc:<11} {status}")
            print(f"\nAUTOFIX: {fix_seconds:.1f}s  final={dict(Counter(final.values()))}  summary={ {k: v for k, v in summary.items() if v} }")
        return 0
    finally:
        stop_target(proc)
        Path(args.report).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"report: {args.report}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        fail("Unexpected error (traceback above).")
