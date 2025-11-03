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
from .tools import Ctx, open_url, click, type_text, select, wait, get_text, get_a11y_tree, get_dom_distill, exists, count, assert_, execute_natural_language
from .reporting import JUnitWriter
from .agents.smart_wait_agent import SmartWaitAgent, perform_wait, collect_light_dom_snapshot
from .agents.smart_scanner_agent import SmartScannerAgent, perform_scan


# Tool mapping
TOOL_MAP = {
    "natural_language": execute_natural_language,
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
    use_llm_resolver: bool = False,
    use_smart_wait: bool = True,
    autoscan: str = "smart"  # "off", "light", "smart", "full"
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
    
    # Initialize smart wait decider
    decider: SmartWaitAgent | None = SmartWaitAgent(cache_path=output_dir / "wait_cache.sqlite3") if use_smart_wait else None
    
    # Initialize smart scanner agent
    scanner: SmartScannerAgent | None = None
    if autoscan != "off":
        scanner = SmartScannerAgent(cache_path=output_dir / "scanner_cache.sqlite3")
    
    async with browser_session(
        headless=not headed,
        proofs_dir=proofs_dir,
        video=video,
        trace=trace,
        har=har
    ) as page:
        ctx = Ctx(page=page, proofs_dir=proofs_dir, use_llm_resolver=use_llm_resolver)
        
        # Store scanner in context for resolver access
        if scanner:
            ctx.scanner = scanner
            ctx.autoscan_mode = autoscan
        
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
                
                elif step.action == "natural_language":
                    result = await tool_func(ctx, step.text or "", step_idx)
                    # Store result for debugging/reporting
                    if step.save_as:
                        variables[step.save_as] = result
                
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
                
                # Execute smart scan after mutating step (if enabled)
                if scanner and step.action in ("open_url", "click", "type", "select"):
                    try:
                        next_step = scenario.steps[step_idx] if step_idx < len(scenario.steps) else None
                        
                        # Decide scan strategy
                        scan_decision = await scanner.decide_scan_strategy(
                            trigger="after_step",
                            step_context=step.model_dump(exclude_none=True),
                            page_url=page.url
                        )
                        
                        # Perform scan
                        if scan_decision.scan_type != "skip":
                            scan_data = await perform_scan(page, scan_decision, proofs_dir)
                            scanner.record_scan(scan_decision.scan_type, page.url)
                            
                            # Store scan data in context for resolver
                            ctx.last_scan_data = scan_data
                            ctx.last_scan_type = scan_decision.scan_type
                            
                            results.append({
                                "name": f"{step_idx:03d} {step.action}#scan",
                                "duration_ms": 0,
                                "url": page.url,
                                "scan_type": scan_decision.scan_type,
                                "scan_reason": scan_decision.reason
                            })
                    except Exception as scan_err:
                        print(f"[Smart Scanner] Error during scan: {scan_err}")
                
                # Execute smart wait after mutating step (if enabled and not last step)
                if decider and step.action in ("open_url", "click", "type", "select") and step_idx < len(scenario.steps):
                    try:
                        next_step = scenario.steps[step_idx]
                        decision = await decider.decide_wait_strategy(
                            current_step=step.model_dump(exclude_none=True),
                            next_step=next_step.model_dump(exclude_none=True),
                            page_state=await collect_light_dom_snapshot(page)
                        )
                        ok = await perform_wait(page, decision)
                        results.append({
                            "name": f"{step_idx:03d} {step.action}#wait",
                            "duration_ms": 0,
                            "url": page.url,
                            "stabilized": ok
                        })
                    except Exception as wait_err:
                        print(f"[Smart Wait] Error during smart wait: {wait_err}")
                
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
