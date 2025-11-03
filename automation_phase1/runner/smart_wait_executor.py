from __future__ import annotations
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from playwright.async_api import Page
from .agents.smart_wait_agent import SmartWaitAgent, WaitDecision
from ..schemas import Target


class SmartWaitExecutor:
    """Executes smart wait decisions from the LLM agent."""
    
    def __init__(self, page: Page, proofs_dir: Path, use_llm: bool = True, cache_path: Path | None = None):
        """
        Initialize smart wait executor.
        
        Args:
            page: Playwright page instance
            proofs_dir: Directory for proof artifacts
            use_llm: Whether to use LLM for decisions (fallback to heuristics if False)
            cache_path: Path to cache file for consistency
        """
        self.page = page
        self.proofs_dir = proofs_dir
        self.use_llm = use_llm
        self.agent = None
        
        if use_llm:
            try:
                self.agent = SmartWaitAgent(cache_path=cache_path)
            except Exception as e:
                print(f"[Smart Wait] Failed to initialize agent: {e}, using fallback")
                self.agent = None

    async def execute_smart_wait(
        self,
        current_step: Dict[str, Any],
        next_step: Optional[Dict[str, Any]],
        page_state: Dict[str, Any]
    ) -> bool:
        """
        Execute smart waiting based on LLM decision or fallback heuristics.
        
        Args:
            current_step: The step that was just executed
            next_step: The upcoming step
            page_state: Current page state (URL, DOM snapshot, etc.)
            
        Returns:
            True if wait succeeded, False if failed
        """
        if not self.agent:
            # No LLM agent, use simple fallback
            return await self._execute_fallback_wait(current_step, next_step)
        
        try:
            # Get LLM decision
            decision = await self.agent.decide_wait_strategy(
                current_step=current_step,
                next_step=next_step,
                page_state=page_state
            )
            
            if not decision.should_wait:
                print(f"[Smart Wait] No wait needed: {decision.reason}")
                return True
            
            # Execute the wait strategy
            return await self._execute_wait_strategy(decision)
            
        except Exception as e:
            print(f"[Smart Wait] Error during smart wait: {e}")
            return await self._execute_fallback_wait(current_step, next_step)

    async def _execute_wait_strategy(self, decision: WaitDecision) -> bool:
        """Execute the specific wait strategy from LLM decision."""
        try:
            print(f"[Smart Wait] Executing: {decision.wait_strategy} ({decision.timeout_ms}ms) - {decision.reason}")
            
            if decision.wait_strategy == "element_visible":
                return await self._wait_for_element_visible(decision)
            
            elif decision.wait_strategy == "text_appears":
                return await self._wait_for_text_appears(decision)
            
            elif decision.wait_strategy == "network_idle":
                return await self._wait_for_network_idle(decision)
            
            elif decision.wait_strategy == "element_gone":
                return await self._wait_for_element_gone(decision)
            
            elif decision.wait_strategy == "none":
                return True
            
            else:
                print(f"[Smart Wait] Unknown strategy: {decision.wait_strategy}")
                return True
                
        except Exception as e:
            print(f"[Smart Wait] Failed to execute wait strategy: {e}")
            return False

    async def _wait_for_element_visible(self, decision: WaitDecision) -> bool:
        """Wait for a specific element to become visible."""
        if not decision.target_element:
            print("[Smart Wait] No target element specified")
            return False
        
        try:
            # Import resolve here to avoid circular dependency
            from .selectors import resolve
            
            target = Target.model_validate(decision.target_element)
            
            # Try to resolve with extended timeout
            locator = await resolve(
                self.page, 
                target,
                use_llm_resolver=False,
                step={"action": "wait_for_element", "target": decision.target_element},
                proofs_dir=self.proofs_dir
            )
            
            # Wait for element to be visible
            await locator.wait_for(state="visible", timeout=decision.timeout_ms)
            print(f"[Smart Wait] ✅ Element visible: {decision.target_element}")
            return True
            
        except Exception as e:
            print(f"[Smart Wait] ⚠️ Element not visible: {e}")
            return False

    async def _wait_for_text_appears(self, decision: WaitDecision) -> bool:
        """Wait for specific text to appear on the page."""
        if not decision.target_text:
            print("[Smart Wait] No target text specified")
            return False
        
        try:
            # Try selector-based approach first
            try:
                await self.page.wait_for_selector(
                    f"text={decision.target_text}",
                    timeout=decision.timeout_ms,
                    state="visible"
                )
                print(f"[Smart Wait] ✅ Text appeared: '{decision.target_text}'")
                return True
            except:
                # Fallback to JavaScript check
                await self.page.wait_for_function(
                    f"document.body.textContent.includes('{decision.target_text}')",
                    timeout=decision.timeout_ms
                )
                print(f"[Smart Wait] ✅ Text appeared (via JS): '{decision.target_text}'")
                return True
                
        except Exception as e:
            print(f"[Smart Wait] ⚠️ Text did not appear: {e}")
            return False

    async def _wait_for_network_idle(self, decision: WaitDecision) -> bool:
        """Wait for network to be idle (no requests for 500ms)."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=decision.timeout_ms)
            print(f"[Smart Wait] ✅ Network idle")
            return True
        except Exception as e:
            print(f"[Smart Wait] ⚠️ Network idle timeout: {e}")
            # Don't fail the test, network might still be active
            return True

    async def _wait_for_element_gone(self, decision: WaitDecision) -> bool:
        """Wait for an element (like loading spinner) to disappear."""
        if not decision.target_element:
            print("[Smart Wait] No target element specified for 'gone' wait")
            return False
        
        try:
            from .selectors import resolve
            
            target = Target.model_validate(decision.target_element)
            locator = await resolve(
                self.page,
                target,
                use_llm_resolver=False,
                step={"action": "wait_until_gone", "target": decision.target_element},
                proofs_dir=self.proofs_dir
            )
            
            # Wait for element to be detached or hidden
            await locator.wait_for(state="detached", timeout=decision.timeout_ms)
            print(f"[Smart Wait] ✅ Element gone: {decision.target_element}")
            return True
            
        except Exception as e:
            # Element might not exist at all, which is fine
            print(f"[Smart Wait] ✅ Element already gone or not found")
            return True

    async def _execute_fallback_wait(
        self,
        current_step: Dict[str, Any],
        next_step: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Fallback waiting strategy using simple heuristics.
        Used when LLM is not available.
        """
        current_action = current_step.get("action")
        pressed_enter = current_step.get("press_enter", False)
        next_action = next_step.get("action") if next_step else None
        
        try:
            # Heuristic 1: type with press_enter followed by type → wait for next field
            if current_action == "type" and pressed_enter and next_action == "type":
                next_target = next_step.get("target")
                if next_target:
                    print("[Smart Wait] Fallback: waiting for next field after press_enter")
                    from .selectors import resolve
                    target = Target.model_validate(next_target)
                    locator = await resolve(
                        self.page,
                        target,
                        use_llm_resolver=False,
                        step=next_step,
                        proofs_dir=self.proofs_dir
                    )
                    await locator.wait_for(state="visible", timeout=5000)
                    return True
            
            # Heuristic 2: click → brief network idle wait
            if current_action == "click":
                print("[Smart Wait] Fallback: waiting for network idle after click")
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass  # Don't fail, just continue
                return True
            
            # Heuristic 3: open_url → wait for page load
            if current_action == "open_url":
                print("[Smart Wait] Fallback: waiting for page load")
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=8000)
                except:
                    pass
                return True
            
            # No wait needed for other actions
            return True
            
        except Exception as e:
            print(f"[Smart Wait] Fallback wait failed: {e}")
            return True  # Don't block execution


