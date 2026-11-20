"""Grounding: test cases, scripts and repairs are judged against what discovery observed, not against what a model wrote."""

from __future__ import annotations

import json

import pytest

from ats.analysis.autofix import apply_repair
from ats.analysis.expectations import parse_claim, repair_expectation
from ats.automation.script_service import build_corpus, validate_script
from ats.discovery.facts import Evidence, facts_digest
from ats.generation.grounding import ground_cases
from ats.generation.scenarios import ScenarioService, page_names
from ats.locators.builder import build_locators
from ats.models import AutomationStep, DiscoveryResult, PageSnapshot, Scenario, TestCase, TestScript
from ats.generation.adapters.common import build_views


def el(role: str, name: str, tag: str = "", *, visible: bool = True, **extra) -> dict:
    return {"role": role, "name": name, "text": extra.pop("text", name), "tag": tag or {"button": "button", "textbox": "input", "heading": "h2", "radio": "input"}.get(role, "div"),
            "visible": visible, "xpath": f"//{role}[{name}]", "css": f"{role}.{name}", "counts": {}, **extra}  # fmt: skip


def nav() -> list[dict]:
    return [el("radio", "Chat"), el("radio", "Profile"), el("radio", "Settings"), el("button", "Sign out")]


def app() -> DiscoveryResult:
    def signed(key: str, name: str, heading: str, body: list[dict], steps: list[dict]) -> PageSnapshot:
        return PageSnapshot(
            url="https://app.test/", page_key=key, view_name=name, signed_in=True, title="WithYou", headings=[f"h2: {heading}"],
            elements=[el("heading", heading), *body, *nav()], reached_by=["Sign in with the test account"], nav_steps=steps,
        )  # fmt: skip

    pages = [
        PageSnapshot(
            url="https://app.test/", page_key="landing", view_name="WithYou", title="WithYou", headings=["h1: WithYou"],
            elements=[el("heading", "WithYou"), el("button", "Get started")], texts=["A personal AI companion"],
        ),
        PageSnapshot(
            url="https://app.test/", page_key="get_started", view_name="WithYou", title="WithYou", has_password=False,
            elements=[el("textbox", "Email"), el("textbox", "Password"), el("button", "Log in")],
            nav_steps=[{"role": "button", "label": "Get started", "nth": 0, "href": ""}],
            outcomes=[{"action": "Submit the sign-in form with an unknown email and a wrong password", "result": "Invalid email or password", "shown_messages": ["Invalid email or password"]}],
        ) if False else PageSnapshot(
            url="https://app.test/", page_key="get_started", view_name="WithYou", title="WithYou",
            elements=[el("textbox", "Email"), el("textbox", "Password"), el("button", "Log in")],
            nav_steps=[{"role": "button", "label": "Get started", "nth": 0, "href": ""}],
            outcomes=[{"action": "Submit the sign-in form with an unknown email and a wrong password", "result": "Invalid email or password", "shown_messages": ["Invalid email or password"]}],
        ),
        signed("home", "Chat", "Chat", [el("textbox", "Message"), el("button", "Send")], []),
        signed("profile", "Profile", "Profile", [el("textbox", "Display name"), el("button", "Save profile")], [{"role": "radio", "label": "Profile", "nth": 0, "href": ""}]),
        signed("settings", "Settings", "Settings", [el("checkbox", "Email notifications", "input"), el("button", "Save settings")], [{"role": "radio", "label": "Settings", "nth": 0, "href": ""}]),
    ]  # fmt: skip
    return DiscoveryResult(start_url="https://app.test/", pages=pages)


@pytest.fixture()
def world():
    discovery = app()
    specs = {s.element_key: s for s in build_locators(discovery)}
    return discovery, specs, Evidence(discovery, specs), build_views(discovery)


def key(specs, view: str, role: str, name: str) -> str:
    return next(k for k, s in specs.items() if s.page_key == view and (s.role or s.tag) == role and s.name == name)


def case(**fields) -> TestCase:
    return TestCase(**{"test_case_id": "TC_X_001", "scenario_id": "SC_X_001", "title": "t", "steps": ["s"], "expected_result": "r", **fields})


def script(*steps: tuple) -> TestScript:
    return TestScript(test_case_id="TC_X_001", title="t", steps=[AutomationStep(action=a, element=e, value=v, description="d") for a, e, v in steps])


def check(world, *steps) -> TestScript:
    discovery, specs, evidence, views = world
    out = validate_script(script(*steps), case(), specs, build_corpus(case(), discovery), "https://app.test", [], evidence, views)
    assert out is not None
    return out


# ------------------------------------------------------------------------------------------ discovery facts
def test_facts_list_each_views_content_once_and_the_shared_menu_once(world):
    discovery, *_ = world
    digest = facts_digest(discovery)
    chrome = digest["shared_controls_on_most_views"]["after sign-in"]
    assert "radio 'settings'" in chrome and "button 'sign out'" in chrome
    settings = next(v for v in digest["views"] if v["page_key"] == "settings")
    assert settings["signed_in"] is True and settings["headings"] == ["Settings"] and settings["reached_by"][0].startswith("Sign in")
    assert {c["name"] for c in settings["controls"]} == {"Email notifications", "Save settings"}  # the menu is not repeated on every view
    public = next(v for v in digest["views"] if v["page_key"] == "get_started")
    assert public["observed_outcomes"][0]["result"] == "Invalid email or password" and public["signed_in"] is False


# ------------------------------------------------------------------------------------------ scripts
def test_an_invented_heading_text_is_not_confirmed_by_the_test_case_itself(world):
    discovery, specs, *_ = world
    invented = case(title="Settle page heading", expected_result="The 'Settle' heading is shown")  # the model's own wording
    assert "settle" not in build_corpus(invented, discovery)  # the wording of the test case is no evidence
    heading = key(specs, "settings", "heading", "Settings")
    out = check(world, ("goto", None, "/"), ("expect_text", heading, "Settle"))
    assert out.steps[-1].action == "expect_visible" and "never observed" in out.notes  # the heading exists; the claim about its text does not
    out = check(world, ("goto", None, "/"), ("expect_text", heading, "Settngs"))
    assert out.steps[-1].action == "expect_text" and out.steps[-1].value == "Settings"  # a near miss is corrected to the real text
    out = check(world, ("goto", None, "/"), ("expect_text", heading, "Setting"))
    assert out.steps[-1].value == "Setting"  # contained in "Settings": a real browser check passes, so it stays
    out = check(world, ("goto", None, "/"), ("expect_text", heading, "Settings"))
    assert out.steps[-1].value == "Settings" and "never observed" not in out.notes


def test_the_check_moves_to_the_element_that_really_carries_the_text(world):
    _, specs, *_ = world
    radio = key(specs, "settings", "radio", "Settings")
    heading = key(specs, "settings", "heading", "Settings")
    out = check(world, ("goto", None, "/"), ("click", radio, None), ("expect_text", key(specs, "settings", "button", "Save settings"), "Settings"))
    # 'Settings' is the heading's text, not the button's: the assertion is moved to the heading (a role the page really has)
    assert out.steps[-1].element == heading and out.steps[-1].action == "expect_text"


def test_the_script_follows_navigation_and_never_uses_an_element_of_another_view(world):
    _, specs, *_ = world
    settings_radio = key(specs, "home", "radio", "Settings")
    save_profile = key(specs, "profile", "button", "Save profile")
    profile_radio_on_home = key(specs, "home", "radio", "Profile")
    out = check(world, ("goto", None, "/"), ("click", settings_radio, None), ("click", profile_radio_on_home, None), ("click", save_profile, None))
    # after 'Settings' the walk is on the settings view: the Profile menu item used is the one of that view, and Save profile is only
    # reachable after the Profile click, so the click that follows it is allowed
    assert [s.element for s in out.steps[1:]] == [settings_radio, key(specs, "settings", "radio", "Profile"), save_profile]
    out = check(world, ("goto", None, "/"), ("click", settings_radio, None), ("click", save_profile, None))
    assert out.steps[-1].element == settings_radio and "Script stopped" in out.notes and "'profile' view" in out.notes  # not on screen: stop, don't wait 20 s


def test_an_action_must_fit_its_element(world):
    _, specs, *_ = world
    heading = key(specs, "settings", "heading", "Settings")
    radio = key(specs, "settings", "radio", "Settings")
    out = check(world, ("goto", None, "/"), ("click", heading, None))  # clicking the heading: the radio with the same name is meant
    assert out.steps[-1].element == radio and "moved to the radio" in out.notes
    save = key(specs, "settings", "button", "Save settings")
    out = check(world, ("goto", None, "/"), ("fill", save, "x"), ("expect_visible", save, None))  # typing into a button
    assert [s.action for s in out.steps] == ["goto"] and "does not fit" in out.notes


def test_unobserved_urls_and_titles_are_left_out(world):
    out = check(world, ("goto", None, "/"), ("expect_title_contains", None, "WithYou"), ("expect_url_contains", None, "/does-not-exist"))
    assert [s.action for s in out.steps] == ["goto", "expect_title_contains"] and "left out" in out.notes


# ------------------------------------------------------------------------------------------ test cases
def test_test_cases_get_their_view_the_sign_in_precondition_and_real_texts(world):
    discovery, specs, *_ = world
    scenario = Scenario(scenario_id="SC_X_001", title="s", page="Settings")  # a view NAME, not a key
    bad = TestCase(
        test_case_id="TC_X_001", scenario_id="SC_X_001", title="Settings page", related_page="settings page",
        steps=["Click 'Settings' in the sidebar", "Verify the 'Setting' heading is shown", "Verify the message 'All your changes were stored forever'"],
        expected_result="The 'Settings' heading and the 'Setting' heading are shown", test_data={"Name": "Karthik"},
    )  # fmt: skip
    [fixed], report = ground_cases([bad], [scenario], discovery, specs)
    assert fixed.related_page == "settings" and fixed.preconditions[0] == "Signed in with the test account"
    assert "Verify the 'Settings' heading is shown" in fixed.steps and "text-corrected" in fixed.tags  # 'Setting' -> 'Settings'
    assert "unverified-text" in fixed.tags and "All your changes were stored forever" in fixed.steps[2]  # flagged, not invented away
    assert report.corrected >= 1 and report.unverified == 1
    assert not fixed.automation_candidate


def test_generated_scenarios_need_an_unambiguous_discovered_view(world):
    discovery, *_ = world
    pages = {p.page_key for p in discovery.pages}
    raw = [Scenario(title=label, page=label) for label in ["WithYou", "unseen/settings", "Settings"]]
    assert [s.page for s in ScenarioService._clean(raw, pages, None, names=page_names(discovery))] == ["settings"]


def test_invented_click_target_is_left_for_manual_review(world):
    discovery, specs, *_ = world
    bad = case(related_page="profile", steps=["Click 'Publish to marketplace'"])
    [fixed], _ = ground_cases([bad], [], discovery, specs)
    assert not fixed.automation_candidate and "unverified-control" in fixed.tags
    assert fixed.steps == bad.steps


def test_discovery_rejects_unique_selector_for_a_different_node(browser_ready):
    if not browser_ready:
        pytest.skip("local Chromium unavailable")
    from playwright.sync_api import sync_playwright
    from ats.discovery.worker import extract_page, verify_elements

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content('<button id="real">Save</button><button>Delete</button>')
        target = next(e for e in extract_page(page)["elements"] if e["id"] == "real")
        target["name"] = "Delete"  # extractor's name heuristic differs from the browser's
        verify_elements(page, [target])
        browser.close()
    [spec] = build_locators(DiscoveryResult(start_url="about:blank", pages=[PageSnapshot(url="about:blank", page_key="home", elements=[target])]))
    assert spec.preferred.kind == "id"
    assert all(s.name != "Delete" for s in spec.alternatives)


# ------------------------------------------------------------------------------------------ repairs
TEST_FILE = """import pytest
from playwright.sync_api import expect


@pytest.mark.tc('TC_SET_001')
def test_tc_set_001_heading(app):
    with app.step('Open', action='open_view', element=''):
        app.open_view('settings')
    with app.step('Heading', action='expect_text', element='settings.settings_heading'):
        expect(app.pages.settings.settings_heading).to_contain_text('Settle')


@pytest.mark.tc('TC_SET_002')
def test_tc_set_002_heading(app):
    with app.step('Heading', action='expect_text', element='settings.settings_heading'):
        expect(app.pages.settings.settings_heading).to_contain_text('Settle')
"""
ERROR = "AssertionError: Locator expected to contain text 'Settle'\nActual value: Settings\nCall log:\n  - waiting for get_by_role('heading')"


def test_the_failure_message_gives_expected_and_actual():
    claim = parse_claim(ERROR)
    assert claim is not None and (claim.expected, claim.actual) == ("Settle", "Settings")


def test_an_invented_expectation_is_corrected_from_the_live_value_and_a_real_regression_is_not(world):
    _, specs, evidence, _ = world
    files = {"tests/web/test_settings.py": TEST_FILE}
    heading = specs[key(specs, "settings", "heading", "Settings")]
    repair, why = repair_expectation(files, "TC_SET_002", heading.element_key, "expect_text", ERROR, heading, evidence)
    assert repair is not None and "corrected to what the page shows: 'Settings'" in why
    fixed = apply_repair(files, repair)["tests/web/test_settings.py"]
    assert fixed.count("to_contain_text('Settings')") == 1 and fixed.count("to_contain_text('Settle')") == 1  # only TC_SET_002 changed
    assert fixed.count("expect(") == TEST_FILE.count("expect(")  # no assertion was removed

    unrelated = "AssertionError: Locator expected to contain text 'Welcome back'\nActual value: Settings\n"
    repair, why = repair_expectation({"tests/web/test_settings.py": TEST_FILE.replace("Settle", "Welcome back")}, "TC_SET_001", heading.element_key, "expect_text", unrelated, heading, evidence)
    assert repair is not None and "to_be_visible()" in repair.edits[0].replace  # nothing like it was ever seen: the claim is limited to the element

    observed = "AssertionError: Locator expected to contain text 'Settings'\nActual value: Profile\n"
    repair, why = repair_expectation({"tests/web/test_settings.py": TEST_FILE.replace("Settle", "Settings")}, "TC_SET_001", heading.element_key, "expect_text", observed, heading, evidence)
    assert repair is None and "application changed" in why  # it WAS observed: that is a regression, reported as a defect
