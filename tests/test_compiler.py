from pathlib import Path
from textwrap import dedent
from automation_phase1.compiler import Compiler

def test_sample_feature(tmp_path: Path):
    c = Compiler(use_llm=False)
    res = c.compile_feature(Path("examples/sample.feature"), base_url="https://example.com")
    assert res.scenario.meta.name == "Happy path"
    assert res.scenario.steps[0].action == "open_url"
    assert res.scenario.steps[1].target.name == "Email"


def test_override_applied(tmp_path: Path):
    # Create a minimal feature that needs the override
    feature = tmp_path / "ovr.feature"
    feature.write_text(dedent(
        '''
        Feature: Override
          Scenario: Click sign in
            When I click "Sign in"
        '''
    ).strip())

    # Create a matching overrides YAML
    overrides = tmp_path / "overrides.yaml"
    overrides.write_text(dedent(
        '''
        'I click "Sign in"':
          action: click
          target:
            role: button
            name: Sign in
        '''
    ).strip())

    c = Compiler(use_llm=False)
    res = c.compile_feature(feature_path=feature, overrides_path=overrides)

    step = res.scenario.steps[0]
    assert step.action == "click"
    assert step.target.role == "button"
    assert step.target.name == "Sign in"


def test_unmatched_without_llm_raises(tmp_path: Path):
    # Step that neither regex nor overrides can handle
    feature = tmp_path / "bad.feature"
    feature.write_text(dedent(
        '''
        Feature: Bad
          Scenario: Unmatched
            When I dance on the page
        '''
    ).strip())

    c = Compiler(use_llm=False)
    try:
        c.compile_feature(feature_path=feature)
        assert False, "Expected ValueError for unmatched step when LLM is disabled"
    except ValueError as e:
        assert "Unrecognized step" in str(e)


def test_base_url_from_feature_tag(tmp_path: Path):
    feature = tmp_path / "tagged.feature"
    feature.write_text(dedent(
        '''
        @base_url=https://example.org
        Feature: Tagged
          Scenario: Uses feature tag
            Given I open "/path"
        '''
    ).strip())

    c = Compiler(use_llm=False)
    res = c.compile_feature(feature_path=feature)
    assert res.scenario.meta.base_url == "https://example.org"
    assert res.scenario.steps[0].url == "/path"


def test_base_url_from_scenario_tag(tmp_path: Path):
    feature = tmp_path / "tagged_scenario.feature"
    feature.write_text(dedent(
        '''
        Feature: Tagged scenario
          @base_url=https://scen.example
          Scenario: Uses scenario tag
            Given I open "/s"
        '''
    ).strip())

    c = Compiler(use_llm=False)
    res = c.compile_feature(feature_path=feature)
    assert res.scenario.meta.base_url == "https://scen.example"
    assert res.scenario.steps[0].url == "/s"


