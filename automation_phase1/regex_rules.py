from __future__ import annotations
import re
from typing import Optional
from .schemas import Step, Target, Predicate

# Order matters; first match wins
_RULES: list[tuple[re.Pattern[str], callable]] = []

def rule(pattern: str):
    pat = re.compile(pattern, flags=re.IGNORECASE)
    def decorator(fn):
        _RULES.append((pat, fn))
        return fn
    return decorator

@rule(r"^I open \"(.+)\"$")
def _open_url(m: re.Match[str]) -> Step:
    return Step(action="open_url", url=m.group(1))

@rule(r"^I click \"(.+)\"$")
def _click_button(m: re.Match[str]) -> Step:
    name = m.group(1)
    return Step(action="click", target=Target(role="button", name=name))

@rule(r"^I click the link \"(.+)\"$")
def _click_link(m: re.Match[str]) -> Step:
    name = m.group(1)
    return Step(action="click", target=Target(role="link", name=name))

@rule(r"^I type \"(.+)\" into the \"(.+)\" field$")
def _type_into_field(m: re.Match[str]) -> Step:
    value, field_name = m.group(1), m.group(2)
    return Step(action="type", target=Target(role="textbox", name=field_name), text=value)

@rule(r"^I type \"(.+)\" into the \"(.+)\" field and press enter$")
def _type_into_field_and_enter(m: re.Match[str]) -> Step:
    value, field_name = m.group(1), m.group(2)
    return Step(action="type", target=Target(role="textbox", name=field_name), text=value, press_enter=True)

@rule(r"^I type \"(.+)\" into \"(.+)\" and press enter$")
def _type_and_enter(m: re.Match[str]) -> Step:
    value, field_name = m.group(1), m.group(2)
    return Step(action="type", target=Target(role="textbox", name=field_name), text=value, press_enter=True)

@rule(r"^I select \"(.+)\" from \"(.+)\"$")
def _select_value(m: re.Match[str]) -> Step:
    value, name = m.group(1), m.group(2)
    return Step(action="select", target=Target(role="combobox", name=name), select_value=value)

@rule(r"^I wait (\d+) ms$")
def _wait_ms(m: re.Match[str]) -> Step:
    return Step(action="wait", wait_ms=int(m.group(1)))

@rule(r"^I should see text \"(.+)\"$")
def _see_text(m: re.Match[str]):
    txt = m.group(1)
    # return pair: get_text + assert contains
    return [
        Step(action="get_text", target=Target(text=txt), save_as="__seen"),
        Step(action="assert", predicate=Predicate(op="contains", left="${__seen}", right=txt)),
    ]

@rule(r"^the page title contains \"(.+)\"$")
def _title_contains(m: re.Match[str]) -> Step:
    # as an explicit assert predicate (runner must implement title read)
    return Step(action="assert", predicate=Predicate(op="contains", left="${title}", right=m.group(1)))

@rule(r"^I get_a11y_tree$")
def _get_a11y_tree(m: re.Match[str]) -> Step:
    return Step(action="get_a11y_tree")

@rule(r"^I get_dom_distill$")
def _get_dom_distill(m: re.Match[str]) -> Step:
    return Step(action="get_dom_distill")

@rule(r"^I check if \"(.+)\" exists$")
def _check_exists(m: re.Match[str]) -> Step:
    name = m.group(1)
    return Step(action="exists", target=Target(name=name))

@rule(r"^I count \"(.+)\" elements$")
def _count_elements(m: re.Match[str]) -> Step:
    name = m.group(1)
    return Step(action="count", target=Target(name=name))


def compile_by_regex(line: str):
    line = line.strip()
    for pat, fn in _RULES:
        m = pat.match(line)
        if m:
            return fn(m)
    return None


