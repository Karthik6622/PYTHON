"""Translate framework-neutral selectors into Selenium ``By`` strategies (``css`` or ``xpath``).

Playwright-only strategies (role, label, text) are approximated with XPath. The approximation is deliberate and documented:
accessible-name computation is simplified to aria-label / label / visible text / value / title / placeholder.
"""

from __future__ import annotations

from ats.models import Selector

_ROLE_XPATH: dict[str, str] = {
    "button": "//button | //input[@type='button' or @type='submit' or @type='reset' or @type='image'] | //*[@role='button']",
    "link": "//a[@href] | //*[@role='link']",
    "textbox": "//input[not(@type) or @type='text' or @type='email' or @type='password' or @type='tel' or @type='url'] | //textarea | //*[@role='textbox']",
    "searchbox": "//input[@type='search'] | //*[@role='searchbox']",
    "checkbox": "//input[@type='checkbox'] | //*[@role='checkbox']",
    "radio": "//input[@type='radio'] | //*[@role='radio']",
    "combobox": "//select | //*[@role='combobox']",
    "spinbutton": "//input[@type='number'] | //*[@role='spinbutton']",
    "slider": "//input[@type='range'] | //*[@role='slider']",
    "heading": "//h1 | //h2 | //h3 | //h4 | //h5 | //h6 | //*[@role='heading']",
    "img": "//img | //*[@role='img']",
    "switch": "//*[@role='switch']",
}


def xpath_literal(text: str) -> str:
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    parts = text.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def css_attr(name: str, value: str) -> str:
    return f'[{name}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"]'


def _name_condition(name: str, exact: bool) -> str:
    lit = xpath_literal(name)
    compare = (lambda expr: f"normalize-space({expr})={lit}") if exact else (lambda expr: f"contains(normalize-space({expr}), {lit})")
    attrs = " or ".join(
        [
            f"@aria-label={lit}" if exact else f"contains(@aria-label, {lit})",
            f"@value={lit}" if exact else f"contains(@value, {lit})",
            f"@title={lit}" if exact else f"contains(@title, {lit})",
            f"@alt={lit}" if exact else f"contains(@alt, {lit})",
            f"@placeholder={lit}" if exact else f"contains(@placeholder, {lit})",
        ]
    )
    label = f"@id=//label[{compare('.')}]/@for or ancestor::label[{compare('.')}]"
    return f"{attrs} or {compare('.')} or {label}"


def to_selenium(selector: Selector | dict) -> dict[str, str]:
    sel = selector if isinstance(selector, Selector) else Selector.model_validate(selector)
    kind, value = sel.kind, sel.value
    if kind == "testid":
        return {"by": "css", "value": css_attr("data-testid", value)}
    if kind == "id":
        return {"by": "css", "value": css_attr("id", value)}
    if kind == "name":
        return {"by": "css", "value": css_attr("name", value)}
    if kind == "placeholder":
        return {"by": "css", "value": css_attr("placeholder", value)}
    if kind == "css":
        return {"by": "css", "value": value}
    if kind == "xpath":
        return {"by": "xpath", "value": value}
    if kind == "label":
        lit = xpath_literal(value)
        cond = "normalize-space(.)=" + lit if sel.exact else f"contains(normalize-space(.), {lit})"
        return {"by": "xpath", "value": f"//*[@id=//label[{cond}]/@for] | //label[{cond}]//input | //label[{cond}]//select | //label[{cond}]//textarea"}
    if kind == "text":
        lit = xpath_literal(value)
        cond = f"normalize-space(.)={lit}" if sel.exact else f"contains(normalize-space(.), {lit})"
        return {"by": "xpath", "value": f"//*[not(self::script) and not(self::style)][{cond}][not(*[{cond}])]"}
    # role (+ optional accessible name)
    base = _ROLE_XPATH.get(value, f"//*[@role={xpath_literal(value)}]")
    if sel.name:
        return {"by": "xpath", "value": f"({base})[{_name_condition(sel.name, sel.exact)}]"}
    return {"by": "xpath", "value": base}
