from __future__ import annotations
import json
import pytest
from pathlib import Path
from textwrap import dedent

from automation_phase1.compiler import Compiler
from automation_phase1.runner.orchestrator import run_scenario


def test_then_see_text_emits_assert(tmp_path: Path):
    feature = tmp_path / "t.feature"
    feature.write_text(dedent(
        '''
        Feature: T
          Scenario: S
            Then I should see text "Welcome"
        '''
    ).strip())

    c = Compiler(use_llm=False)
    res = c.compile_feature(feature)
    steps = res.scenario.steps
    assert len(steps) == 2
    assert steps[0].action == "get_text"
    assert steps[0].save_as == "__seen"
    assert steps[1].action == "assert"
    assert steps[1].predicate.op == "contains"
    assert steps[1].predicate.left == "${__seen}"
    assert steps[1].predicate.right == "Welcome"


def test_title_contains_compiles_to_assert(tmp_path: Path):
    feature = tmp_path / "t2.feature"
    feature.write_text(dedent(
        '''
        Feature: T
          Scenario: S
            Then the page title contains "Smoke"
        '''
    ).strip())

    c = Compiler(use_llm=False)
    res = c.compile_feature(feature)
    steps = res.scenario.steps
    assert len(steps) == 1
    assert steps[0].action == "assert"
    assert steps[0].predicate.op == "contains"
    assert steps[0].predicate.left == "${title}"
    assert steps[0].predicate.right == "Smoke"


@pytest.mark.asyncio
async def test_runner_assert_equals_and_contains(tmp_path: Path):
    # Create a local page
    html = tmp_path / "local.html"
    html.write_text("""<!doctype html><html><head><title>Smoke</title></head><body><h1>Welcome</h1></body></html>""")

    scenario = {
        "meta": {"name": "Assert Runtime", "base_url": f"file://{html.absolute()}"},
        "steps": [
            {"action": "open_url", "url": ""},
            {"action": "get_text", "target": {"text": "Welcome"}, "save_as": "banner"},
            {"action": "assert", "predicate": {"op": "equals", "left": "${banner}", "right": "Welcome"}},
            {"action": "assert", "predicate": {"op": "contains", "left": "${title}", "right": "Smoke"}}
        ]
    }
    scen_file = tmp_path / "s.json"
    scen_file.write_text(json.dumps(scenario))

    proofs = await run_scenario(scen_file, tmp_path, headed=False)
    assert (proofs / "junit.xml").exists()
    # No failures expected
    junit = (proofs / "junit.xml").read_text()
    assert "failures=\"0\"" in junit


@pytest.mark.asyncio
async def test_runner_assert_failures_reported(tmp_path: Path):
    # Create a local page
    html = tmp_path / "local.html"
    html.write_text("""<!doctype html><html><head><title>Smoke</title></head><body><h1>Welcome</h1></body></html>""")

    scenario = {
        "meta": {"name": "Assert Fail", "base_url": f"file://{html.absolute()}"},
        "steps": [
            {"action": "open_url", "url": ""},
            {"action": "get_text", "target": {"text": "Welcome"}, "save_as": "banner"},
            {"action": "assert", "predicate": {"op": "equals", "left": "${banner}", "right": "Wrong"}}
        ]
    }
    scen_file = tmp_path / "s.json"
    scen_file.write_text(json.dumps(scenario))

    proofs = await run_scenario(scen_file, tmp_path, headed=False)
    junit = (proofs / "junit.xml").read_text()
    assert "failures=\"1\"" in junit
    # Failure should include a Screenshot and URL line
    assert "Screenshot:" in junit
    assert "URL:" in junit


