from __future__ import annotations
import json
from pathlib import Path
from playwright.async_api import Page, Locator
from .agents.llm_resolver import LLMResolverAgent
from ..schemas import Target


async def resolve(page: Page, target: Target, *, use_llm_resolver: bool = False, step: dict | None = None, inventories: dict | None = None, proofs_dir: Path | None = None, llm_proposed: bool = False) -> Locator:
    """Resolve a Target to a Playwright Locator, trying ARIA first, CSS last."""
    if not target:
        raise ValueError("Target cannot be None")
    
    async def try_locator(loc: Locator, timeout: int = 250) -> Locator | None:
        try:
            # quick existence/visibility smoke check; low timeout to keep fast fallback
            # Use longer timeout for LLM-proposed selectors
            await loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception:
            return None
    
    # Priority 1: ARIA role + name
    if target.role and target.name:
        loc = await try_locator(page.get_by_role(target.role, name=target.name))
        if loc:
            return loc
    
    # Priority 1b: ARIA role only (for counting, existence checks)
    if target.role and not target.name:
        loc = await try_locator(page.get_by_role(target.role))
        if loc:
            return loc
    
    # Priority 2: Label
    if target.label:
        loc = await try_locator(page.get_by_label(target.label))
        if loc:
            return loc
    
    # Priority 3: Placeholder
    if target.placeholder:
        loc = await try_locator(page.get_by_placeholder(target.placeholder))
        if loc:
            return loc
    
    # Priority 4: Text content
    if target.text:
        loc = await try_locator(page.get_by_text(target.text))
        if loc:
            return loc
    
    # Priority 5: CSS fallback (discouraged but allowed)
    if target.css:
        # Use longer timeout for LLM-proposed CSS selectors
        timeout = 5000 if llm_proposed else 250
        loc = await try_locator(page.locator(target.css), timeout=timeout)
        if loc:
            return loc
    
    # If we get here, the target has no usable selectors
    if use_llm_resolver:
        # Load inventories from disk if not provided
        if not inventories and proofs_dir:
            inventories = {}
            a11y_path = proofs_dir / "a11y_tree.json"
            dom_path = proofs_dir / "dom_distill.json"
            if a11y_path.exists():
                try:
                    inventories["a11y"] = json.loads(a11y_path.read_text())
                except Exception:
                    pass
            if dom_path.exists():
                try:
                    inventories["dom"] = json.loads(dom_path.read_text())
                except Exception:
                    pass
        
        agent = LLMResolverAgent()
        proposed = await agent.propose_target(step or {}, (inventories or {}).get("a11y"), (inventories or {}).get("dom"))
        print(f"[Resolver] LLM proposed: {proposed}")
        if proposed:
            # Try again with proposed target
            try:
                print(f"[Resolver] Retrying with proposed target...")
                result = await resolve(page, Target.model_validate(proposed), use_llm_resolver=False, proofs_dir=proofs_dir, llm_proposed=True)
                print(f"[Resolver] Success with LLM proposed target!")
                return result
            except Exception as e:
                print(f"[Resolver] Retry failed: {e}")
                pass
    raise ValueError(f"Target has no resolvable selectors: {target}")


async def maybe_exists(locator: Locator, timeout: int = 250) -> bool:
    """Check if a locator exists and is visible, with short timeout."""
    try:
        await locator.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        return False
