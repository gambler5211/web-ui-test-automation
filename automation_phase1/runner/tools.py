from __future__ import annotations
import json
from dataclasses import dataclass
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional
from playwright.async_api import Page
from ..schemas import Target, Step
from .selectors import resolve, maybe_exists


@dataclass
class Ctx:
    """Context for tool execution."""
    page: Page
    proofs_dir: Path
    use_llm_resolver: bool = False
    scanner: Optional[Any] = None  # SmartScannerAgent instance
    autoscan_mode: str = "off"  # "off", "light", "smart", "full"
    last_scan_data: Optional[Dict[str, Any]] = None
    last_scan_type: Optional[str] = None


async def open_url(ctx: Ctx, url: str, step_num: int) -> None:
    """Navigate to a URL."""
    await ctx.page.goto(url)
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_open_url.png"
    await ctx.page.screenshot(path=screenshot_path)


async def click(ctx: Ctx, target: Target, step_num: int) -> None:
    """Click on a target element."""
    locator = await resolve(ctx.page, target, use_llm_resolver=ctx.use_llm_resolver, step={"action": "click", "target": target.model_dump() if target else {}}, proofs_dir=ctx.proofs_dir)
    await locator.click()
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_click.png"
    await ctx.page.screenshot(path=screenshot_path)


async def type_text(ctx: Ctx, target: Target, text: str, step_num: int, 
                   press_enter: Optional[bool] = None, 
                   press_keys: Optional[list[str]] = None) -> None:
    """Type text into a target element."""
    locator = await resolve(ctx.page, target, use_llm_resolver=ctx.use_llm_resolver, step={"action": "type", "target": target.model_dump() if target else {}, "text": text}, proofs_dir=ctx.proofs_dir)
    await locator.fill(text)
    
    if press_enter:
        await locator.press("Enter")
    
    if press_keys:
        for key in press_keys:
            await locator.press(key)
    
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_type.png"
    await ctx.page.screenshot(path=screenshot_path)


async def select(ctx: Ctx, target: Target, select_value: str, step_num: int) -> None:
    """Select an option from a dropdown."""
    locator = await resolve(ctx.page, target, use_llm_resolver=ctx.use_llm_resolver, step={"action": "select", "target": target.model_dump() if target else {}, "value": select_value}, proofs_dir=ctx.proofs_dir)
    await locator.select_option(select_value)
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_select.png"
    await ctx.page.screenshot(path=screenshot_path)


async def wait(ctx: Ctx, wait_ms: int, step_num: int) -> None:
    """Wait for a specified number of milliseconds."""
    await ctx.page.wait_for_timeout(wait_ms)
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_wait.png"
    await ctx.page.screenshot(path=screenshot_path)


async def get_text(ctx: Ctx, target: Target, step_num: int, 
                  save_as: Optional[str] = None) -> Optional[str]:
    """Get text from a target element."""
    locator = await resolve(ctx.page, target, use_llm_resolver=ctx.use_llm_resolver, step={"action": "get_text", "target": target.model_dump() if target else {}}, proofs_dir=ctx.proofs_dir)
    text_content = await locator.text_content()
    
    if save_as and text_content is not None:
        # Save to a variable file for potential future use
        var_file = ctx.proofs_dir / f"{save_as}.txt"
        var_file.write_text(text_content)
    
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_get_text.png"
    await ctx.page.screenshot(path=screenshot_path)
    return text_content


# Sensor actions
async def get_a11y_tree(ctx: Ctx, step_num: int, save_as: Optional[str] = None) -> Dict[str, Any]:
    """Get accessibility tree snapshot."""
    a11y_tree = await ctx.page.accessibility.snapshot(interesting_only=True)
    
    output_file = ctx.proofs_dir / "a11y_tree.json"
    output_file.write_text(json.dumps(a11y_tree, indent=2))
    
    if save_as:
        var_file = ctx.proofs_dir / f"{save_as}.json"
        var_file.write_text(json.dumps(a11y_tree, indent=2))
    
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_get_a11y_tree.png"
    await ctx.page.screenshot(path=screenshot_path)
    return a11y_tree or {}


async def get_dom_distill(ctx: Ctx, step_num: int, save_as: Optional[str] = None) -> Dict[str, Any]:
    """Get a fast DOM inventory."""
    dom_data = await ctx.page.evaluate("""
        () => {
            const elements = document.querySelectorAll('*');
            const tagCounts = {};
            const formElements = [];
            const links = [];
            
            for (const el of elements) {
                const tag = el.tagName.toLowerCase();
                tagCounts[tag] = (tagCounts[tag] || 0) + 1;
                
                if (['input', 'select', 'textarea', 'button'].includes(tag)) {
                    formElements.push({
                        tag: tag,
                        type: el.type || null,
                        id: el.id || null,
                        name: el.name || null,
                        'aria-label': el.getAttribute('aria-label') || null
                    });
                }
                
                if (tag === 'a' && el.href) {
                    links.push({
                        href: el.href,
                        text: el.textContent.trim().slice(0, 50)
                    });
                }
            }
            
            return {
                tagCounts,
                formElements,
                links: links.slice(0, 20), // Limit to first 20 links
                title: document.title,
                url: window.location.href
            };
        }
    """)
    
    output_file = ctx.proofs_dir / "dom_distill.json"
    output_file.write_text(json.dumps(dom_data, indent=2))
    
    if save_as:
        var_file = ctx.proofs_dir / f"{save_as}.json"
        var_file.write_text(json.dumps(dom_data, indent=2))
    
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_get_dom_distill.png"
    await ctx.page.screenshot(path=screenshot_path)
    return dom_data


async def exists(ctx: Ctx, target: Target, step_num: int, 
                save_as: Optional[str] = None) -> bool:
    """Check if a target element exists and is visible."""
    locator = await resolve(ctx.page, target, use_llm_resolver=ctx.use_llm_resolver, step={"action": "exists", "target": target.model_dump() if target else {}}, proofs_dir=ctx.proofs_dir)
    element_exists = await maybe_exists(locator)
    
    if save_as:
        var_file = ctx.proofs_dir / f"{save_as}.txt"
        var_file.write_text(str(element_exists))
    
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_exists.png"
    await ctx.page.screenshot(path=screenshot_path)
    return element_exists


async def count(ctx: Ctx, target: Target, step_num: int, 
               save_as: Optional[str] = None) -> int:
    """Count the number of elements matching the target."""
    locator = await resolve(ctx.page, target, use_llm_resolver=ctx.use_llm_resolver, step={"action": "count", "target": target.model_dump() if target else {}}, proofs_dir=ctx.proofs_dir)
    element_count = await locator.count()
    
    if save_as:
        var_file = ctx.proofs_dir / f"{save_as}.txt"
        var_file.write_text(str(element_count))
    
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_count.png"
    await ctx.page.screenshot(path=screenshot_path)
    return element_count


def _next_shot(proofs_dir: Path, action: str, step_num: Optional[int] = None) -> Path:
    if step_num is not None:
        return proofs_dir / f"step_{step_num:03d}_{action}.png"
    # Fallback (shouldn't be used normally)
    i = 1
    while True:
        p = proofs_dir / f"step_{i:03d}_{action}.png"
        if not p.exists():
            return p
        i += 1


async def assert_(ctx: Ctx, predicate: dict, variables: dict, step_num: int, **_):
    """
    Supports ops: equals, contains, exists.
    - Interpolate ${var} on predicate.left/right using variables.
    - Special vars: ${title} (await ctx.page.title()), ${url} (ctx.page.url)
    """

    async def resolve_val(x: Optional[str]):
        if x is None:
            return None
        if isinstance(x, str) and x.startswith("${") and x.endswith("}"):
            key = x[2:-1]
            if key == "title":
                return await ctx.page.title()
            if key == "url":
                return ctx.page.url
            return variables.get(key, x)
        return x

    op = predicate.get("op")
    left = await resolve_val(predicate.get("left"))
    right = await resolve_val(predicate.get("right"))

    if op == "equals":
        if str(left) != str(right):
            raise AssertionError(f"equals: {left!r} != {right!r}")
    elif op == "contains":
        if str(right) not in str(left):
            raise AssertionError(f"contains: {right!r} not in {left!r}")
    elif op == "exists":
        if not bool(left):
            raise AssertionError(f"exists: {left!r} is falsy")
    else:
        raise ValueError(f"Unsupported assert op: {op}")

    shot = _next_shot(ctx.proofs_dir, "assert", step_num)
    await ctx.page.screenshot(path=shot)
    return {"screenshot": str(shot)}


async def execute_natural_language(ctx: Ctx, instruction: str, step_num: int) -> Dict[str, Any]:
    """Execute a natural language instruction using AI agent."""
    from .agents.natural_language_agent import NaturalLanguageAgent
    
    print(f"[Natural Language] Executing: {instruction}")
    
    # Initialize the agent
    agent = NaturalLanguageAgent()
    
    # Get page context
    page_context = await agent.get_page_context(ctx.page)
    
    # Plan actions
    planned_actions = await agent.plan_actions(instruction, page_context)
    
    # Execute each planned action
    executed_actions = []
    for i, action_data in enumerate(planned_actions):
        action_type = action_data.get("action")
        print(f"[Natural Language] Sub-action {i+1}/{len(planned_actions)}: {action_type}")
        
        try:
            if action_type == "click":
                target_data = action_data.get("target", {})
                target = Target(**target_data) if target_data else None
                if target:
                    await click(ctx, target, step_num)
                    executed_actions.append(action_data)
            
            elif action_type == "type":
                target_data = action_data.get("target", {})
                target = Target(**target_data) if target_data else None
                text = action_data.get("text", "")
                press_enter = action_data.get("press_enter", False)
                press_keys = action_data.get("press_keys")
                if target:
                    await type_text(ctx, target, text, step_num, press_enter=press_enter, press_keys=press_keys)
                    executed_actions.append(action_data)
            
            elif action_type == "select":
                target_data = action_data.get("target", {})
                target = Target(**target_data) if target_data else None
                select_value = action_data.get("select_value", "")
                if target:
                    await select(ctx, target, select_value, step_num)
                    executed_actions.append(action_data)
            
            elif action_type == "wait":
                wait_ms = action_data.get("wait_ms", 0)
                await wait(ctx, wait_ms, step_num)
                executed_actions.append(action_data)
            
            else:
                print(f"[Natural Language] Warning: Unknown action type '{action_type}'")
        
        except Exception as e:
            print(f"[Natural Language] Error executing sub-action: {e}")
            raise  # Re-raise to trigger error handling in orchestrator
    
    # Take final screenshot
    screenshot_path = ctx.proofs_dir / f"step_{step_num:03d}_natural_language.png"
    await ctx.page.screenshot(path=screenshot_path)
    
    return {
        "instruction": instruction,
        "planned_actions": planned_actions,
        "executed_actions": executed_actions,
        "screenshot": str(screenshot_path)
    }
