from __future__ import annotations
import asyncio
import json
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin

from ..schemas import Scenario
from .browser_manager import browser_session
from .tools import Ctx, open_url, click, type_text, select, wait, get_text, get_a11y_tree, get_dom_distill, exists, count, assert_
from .reporting import JUnitWriter


# Tool mapping
TOOL_MAP = {
    "open_url": open_url,
    "click": click,
    "type": type_text,
    "select": select,
    "wait": wait,
    "get_text": get_text,
    "get_a11y_tree": get_a11y_tree,
    "get_dom_distill": get_dom_distill,
    "exists": exists,
    "count": count,
    "assert": assert_,
}


async def run_scenario(
    scenario_path: Path,
    output_dir: Path,
    *,
    headed: bool = False,
    video: bool = False,
    trace: bool = False,
    har: bool = False,
    use_llm_resolver: bool = False
) -> Path:
    """Run a scenario and return the proofs directory path."""
    
    # Load scenario
    scenario_data = json.loads(scenario_path.read_text())
    scenario = Scenario.model_validate(scenario_data)
    
    # Create unique run directory
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    proofs_dir = output_dir / run_id
    proofs_dir.mkdir(parents=True, exist_ok=True)
    
    results: List[Dict[str, Any]] = []
    variables: Dict[str, Any] = {}
    
    async with browser_session(
        headless=not headed,
        proofs_dir=proofs_dir,
        video=video,
        trace=trace,
        har=har
    ) as page:
        ctx = Ctx(page=page, proofs_dir=proofs_dir, use_llm_resolver=use_llm_resolver)
        # Note: use_llm_resolver flag reserved; wiring happens in selectors if enabled in future
        
        for step_idx, step in enumerate(scenario.steps, 1):
            step_name = f"{step_idx:03d} {step.action}"
            start_time = time.time()
            
            try:
                # Get the tool function
                tool_func = TOOL_MAP.get(step.action)
                if not tool_func:
                    raise ValueError(f"Unknown action: {step.action}")
                
                # Prepare arguments based on action type
                if step.action == "open_url":
                    url = step.url
                    # interpolate variables in url
                    if isinstance(url, str) and url.startswith("${") and url.endswith("}"):
                        key = url[2:-1]
                        url = variables.get(key, url)
                    # Handle empty URL - use base_url directly
                    if not url and scenario.meta.base_url:
                        url = scenario.meta.base_url
                    # Expand relative URLs using base_url if available
                    elif url and scenario.meta.base_url:
                        if not url.startswith(("http://", "https://", "file://")):
                            url = urljoin(scenario.meta.base_url, url)
                    await tool_func(ctx, url, step_idx)
                    
                elif step.action == "click":
                    await tool_func(ctx, step.target, step_idx)
                    
                elif step.action == "type":
                    await tool_func(
                        ctx, 
                        step.target, 
                        (variables.get(step.text[2:-1]) if isinstance(step.text, str) and step.text.startswith("${") and step.text.endswith("}") else (step.text or "")), 
                        step_idx,
                        press_enter=step.press_enter,
                        press_keys=step.press_keys
                    )
                    
                elif step.action == "select":
                    sel_val = step.select_value
                    if isinstance(sel_val, str) and sel_val.startswith("${") and sel_val.endswith("}"):
                        sel_val = variables.get(sel_val[2:-1], sel_val)
                    await tool_func(ctx, step.target, sel_val, step_idx)
                    
                elif step.action == "wait":
                    await tool_func(ctx, step.wait_ms or 0, step_idx)
                    
                elif step.action == "get_text":
                    await tool_func(ctx, step.target, step_idx, save_as=step.save_as)
                    
                elif step.action in ["get_a11y_tree", "get_dom_distill"]:
                    await tool_func(ctx, step_idx, save_as=step.save_as)
                    
                elif step.action in ["exists", "count"]:
                    value = await tool_func(ctx, step.target, step_idx, save_as=step.save_as)
                    if step.save_as:
                        variables[step.save_as] = value

                elif step.action == "assert":
                    await tool_func(ctx, predicate=step.predicate.model_dump() if step.predicate else {}, variables=variables, step_num=step_idx)
                
                # Post-step variable capture for get_text
                if step.action == "get_text" and step.save_as:
                    # read saved text file back or skip (we can set None safely)
                    try:
                        txt = (ctx.proofs_dir / f"{step.save_as}.txt").read_text()
                        variables[step.save_as] = txt
                    except Exception:
                        pass

                # Record successful step
                results.append({
                    "name": step_name,
                    "duration_ms": int((time.time() - start_time) * 1000),
                    "url": page.url
                })
                
            except Exception as e:
                # Save error screenshot
                error_screenshot = proofs_dir / f"step_{step_idx:03d}_error.png"
                try:
                    await page.screenshot(path=error_screenshot)
                except Exception:
                    pass  # Ignore screenshot errors during error handling
                
                # Record failed step
                results.append({
                    "name": step_name,
                    "duration_ms": int((time.time() - start_time) * 1000),
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "url": page.url,
                    "screenshot": str(error_screenshot)
                })
                
                # Break on first error
                break
    
    # Write results
    results_file = proofs_dir / "results.json"
    results_file.write_text(json.dumps(results, indent=2))
    
    # Write JUnit XML
    junit_file = proofs_dir / "junit.xml"
    JUnitWriter.write(junit_file, scenario.meta.name, results)
    
    return proofs_dir
