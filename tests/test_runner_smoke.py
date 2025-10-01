from __future__ import annotations
import json
import pytest
from pathlib import Path
from automation_phase1.runner.orchestrator import run_scenario


@pytest.mark.asyncio
async def test_runner_smoke(tmp_path: Path):
    """Smoke test for the runner with a local HTML file."""
    
    # Create a local HTML file
    html_file = tmp_path / "local.html"
    html_file.write_text("""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <title>Smoke</title>
</head>
<body>
    <h1>Welcome</h1>
    <form>
        <label>Email <input aria-label="Email" type="email"/></label>
        <label>Password <input aria-label="Password" type="password"/></label>
        <button type="submit">Login</button>
    </form>
</body>
</html>""")
    
    # Create scenario JSON
    scenario_data = {
        "meta": {
            "name": "Smoke Test",
            "base_url": f"file://{html_file.absolute()}"
        },
        "steps": [
            {
                "action": "open_url",
                "url": ""
            },
            {
                "action": "get_text",
                "target": {"text": "Welcome"}
            },
            {
                "action": "exists",
                "target": {"role": "textbox", "name": "Email"}
            },
            {
                "action": "count",
                "target": {"role": "button"}
            },
            {
                "action": "get_a11y_tree"
            },
            {
                "action": "get_dom_distill"
            }
        ]
    }
    
    scenario_file = tmp_path / "scenario.json"
    scenario_file.write_text(json.dumps(scenario_data, indent=2))
    
    # Run the scenario
    proofs_dir = await run_scenario(
        scenario_path=scenario_file,
        output_dir=tmp_path,
        headed=False
    )
    
    # Verify outputs
    assert proofs_dir.exists()
    assert (proofs_dir / "junit.xml").exists()
    assert (proofs_dir / "results.json").exists()
    assert (proofs_dir / "a11y_tree.json").exists()
    assert (proofs_dir / "dom_distill.json").exists()
    
    # Check for screenshots (at least 2 step screenshots should exist)
    screenshots = list(proofs_dir.glob("step_*.png"))
    assert len(screenshots) >= 2
    
    # Verify JUnit XML contains test cases
    junit_content = (proofs_dir / "junit.xml").read_text()
    assert 'testcase name="001 open_url"' in junit_content
    assert 'testcase name="002 get_text"' in junit_content
    
    # Verify results JSON
    results = json.loads((proofs_dir / "results.json").read_text())
    assert len(results) >= 4  # Should have at least 4 successful steps
