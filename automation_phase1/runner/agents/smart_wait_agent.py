# automation_phase1/runner/agents/smart_wait_agent.py
from __future__ import annotations
import asyncio
import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.async_api import Page, TimeoutError as PWTimeoutError
from ..selectors import resolve  # ARIA-first resolver
from ...schemas import Target
from ...llm_providers import LLMProviderFactory, BaseLLMProvider


# =========================
# Prompt (fixed: escaped braces)
# =========================
WAIT_DECISION_PROMPT = """
You are a smart test automation agent that decides optimal waiting strategies for browser automation.

Analyze the current step, next step, and page state to determine if and how the test should wait.

CONTEXT:
- Current action: {current_action}
- Current target: {current_target}
- Current pressed enter: {pressed_enter}
- Next action: {next_action}
- Next target: {next_target}
- Page URL: {page_url}
- Page has forms: {has_forms}
- Page has loading indicators: {has_loading}

DECISION RULES:
1. After "click" on submit/button → wait for network idle or success message
2. After "type" with press_enter=true → wait for next field to appear or page to change
3. After "click" on link → wait for navigation/network idle
4. Before "get_text" or "assert" → wait for the target text/element to appear
5. After "open_url" → wait for page load (network idle)
6. Between consecutive "type" actions with press_enter → wait for next input field
7. If loading indicators detected → wait for them to disappear
8. If no dynamic content expected → no wait needed

OUTPUT SCHEMA (JSON only):
{{
  "should_wait": true|false,
  "wait_strategy": "element_visible"|"text_appears"|"network_idle"|"element_gone"|"none",
  "timeout_ms": 1000-30000,
  "target_element": {{"role": "textbox", "name": "Password"}} | null,
  "target_text": "Success message" | null,
  "reason": "Brief explanation"
}}

EXAMPLES:

Input: click "Submit", next: assert "Success"
Output: {{"should_wait": true, "wait_strategy": "text_appears", "timeout_ms": 10000, "target_text": "Success", "reason": "Wait for success message after form submission"}}

Input: type with press_enter=true, next: type "Password"
Output: {{"should_wait": true, "wait_strategy": "element_visible", "timeout_ms": 5000, "target_element": {{"role": "textbox", "name": "Password"}}, "reason": "Wait for password field after pressing enter on username"}}

Input: click "Load Data", next: assert
Output: {{"should_wait": true, "wait_strategy": "network_idle", "timeout_ms": 15000, "reason": "Wait for AJAX data loading to complete"}}

Input: type "text", next: type "more text" (no press_enter)
Output: {{"should_wait": false, "wait_strategy": "none", "timeout_ms": 0, "reason": "No dynamic content between consecutive typing"}}

Input: open_url, next: type
Output: {{"should_wait": true, "wait_strategy": "network_idle", "timeout_ms": 8000, "reason": "Wait for page to fully load before interaction"}}

Return ONLY valid JSON, no markdown or extra text.
"""


# =========================
# Data classes
# =========================
@dataclass
class WaitDecision:
    """Decision from LLM/heuristics about waiting strategy."""
    should_wait: bool
    wait_strategy: str  # "element_visible" | "text_appears" | "network_idle" | "element_gone" | "none"
    timeout_ms: int
    target_element: Optional[Dict[str, Any]] = None
    target_text: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =========================
# Network quiet tracker
# =========================
class NetworkQuiet:
    """
    Tracks inflight requests and waits for a quiet window.
    Use for SPA/XHR churn (more reliable than load_state('networkidle') after clicks).
    """
    def __init__(self, page: Page):
        self.page = page
        self._inflight = 0
        self._bound = False

    def _on_req(self, _): self._inflight += 1
    def _on_done(self, _): self._inflight = max(0, self._inflight - 1)

    async def __aenter__(self):
        if not self._bound:
            self.page.on("request", self._on_req)
            self.page.on("requestfinished", self._on_done)
            self.page.on("requestfailed", self._on_done)
            self._bound = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # Keep bound across scenario to amortize listener cost.
        return False

    async def wait_quiet(self, *, quiet_ms=300, timeout_ms=2500) -> bool:
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            t0 = time.time()
            # need a continuous quiet window of length quiet_ms
            while (time.time() - t0) * 1000 < quiet_ms:
                if self._inflight > 0:
                    t0 = time.time()
                await asyncio.sleep(0.05)
            return True
        return False


# =========================
# Executor: perform the decided wait
# =========================
async def perform_wait(page: Page, decision: WaitDecision) -> bool:
    """
    Map a WaitDecision into concrete Playwright waits.
    Returns True if stabilization succeeded (or skipped), False on timeout.
    """
    if not decision.should_wait:
        return True

    strategy = decision.wait_strategy or "none"
    tmo = max(1000, min(30000, int(decision.timeout_ms or 5000)))
    try:
        if strategy == "element_visible":
            if not decision.target_element:
                return True
            tgt = Target.model_validate(decision.target_element)
            loc = await resolve(page, tgt)
            await loc.first.wait_for(state="visible", timeout=tmo)
            return True

        if strategy == "element_gone":
            if not decision.target_element:
                return True
            tgt = Target.model_validate(decision.target_element)
            loc = await resolve(page, tgt)
            await loc.first.wait_for(state="hidden", timeout=tmo)
            return True

        if strategy == "text_appears":
            if decision.target_text:
                await page.get_by_text(decision.target_text).first.wait_for(state="visible", timeout=tmo)
                return True
            # Fallback: body contains text
            await page.wait_for_function(
                "(txt) => document.body && document.body.innerText.includes(txt)",
                decision.target_text, timeout=tmo
            )
            return True

        if strategy == "network_idle":
            async with NetworkQuiet(page) as nq:
                ok = await nq.wait_quiet(quiet_ms=300, timeout_ms=tmo)
                return ok

        # unknown / none
        return True

    except PWTimeoutError:
        return False


# =========================
# LLM-powered SmartWaitAgent (Gemini supported; falls back to heuristics)
# =========================
class SmartWaitAgent:
    """
    Decides whether/how to wait after a step.
    - If LLM provider available, uses it with caching for intelligent decisions
    - If not, uses conservative heuristics (deterministic).
    """

    def __init__(
        self, 
        provider: Optional[str] = None,
        model: Optional[str] = None, 
        cache_path: Optional[Path] = None
    ):
        """
        Initialize Smart Wait Agent.
        
        Args:
            provider: LLM provider or None for auto-detect
            model: Model name or None for default (gemini-2.5-flash)
            cache_path: Path to SQLite cache file
        """
        try:
            self.llm: Optional[BaseLLMProvider] = LLMProviderFactory.create(
                provider=provider,
                model=model or "gemini-2.5-flash"
            )
            print(f"[Smart Wait] Initialized with {self.llm}")
        except ValueError:
            print("[Smart Wait] No LLM provider available, will use heuristics")
            self.llm = None

        self.conn = None
        self.cache_path = cache_path
        if cache_path:
            self._init_cache(cache_path)

    # ---------- cache ----------
    def _init_cache(self, cache_path: Path):
        self.conn = sqlite3.connect(str(cache_path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS wait_decisions (
                key TEXT PRIMARY KEY,
                decision_json TEXT NOT NULL,
                ts DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def _cache_key(self, context: Dict[str, Any]) -> str:
        parts = [
            context.get("current_action", ""),
            context.get("current_target", ""),
            str(context.get("pressed_enter", False)),
            context.get("next_action", ""),
            context.get("next_target", ""),
            str(context.get("has_loading", False)),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def _get_cached_decision(self, key: str) -> Optional[WaitDecision]:
        if not self.conn:
            return None
        row = self.conn.execute("SELECT decision_json FROM wait_decisions WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row[0])
            return WaitDecision(**data)
        except Exception:
            return None

    def _cache_decision(self, key: str, decision: WaitDecision):
        if not self.conn:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO wait_decisions(key, decision_json) VALUES(?, ?)",
            (key, json.dumps(decision.to_dict()))
        )
        self.conn.commit()

    # ---------- public API ----------
    async def decide_wait_strategy(
        self,
        current_step: Dict[str, Any],
        next_step: Optional[Dict[str, Any]],
        page_state: Dict[str, Any]
    ) -> WaitDecision:
        """
        Decide optimal wait strategy for the current situation.
        
        Uses LLM if available, falls back to heuristics.
        """
        if not self.llm:
            return self._fallback(current_step, next_step)

        context = self._build_context(current_step, next_step, page_state)
        key = self._cache_key(context)
        cached = self._get_cached_decision(key)
        if cached:
            return cached

        try:
            prompt = WAIT_DECISION_PROMPT.format(**context)
        except KeyError:
            # Extremely defensive: if braces slipped, do naive replacement
            prompt = self._naive_prompt(context)

        try:
            response_text = await self.llm.generate(
                prompt=prompt,
                system_instruction="Return ONLY JSON. No markdown/code fences. Start with { and end with }.",
                temperature=0.2,
                max_tokens=400,
                json_mode=True
            )
            
            # Log token usage
            usage = self.llm.get_usage()
            if usage:
                print(f"[Smart Wait] Tokens: {usage}")
            
            decision = self._parse_llm_response(response_text)
            self._cache_decision(key, decision)
            return decision
        except Exception as e:
            print(f"[Smart Wait] LLM error: {e}, using fallback")
            # On any LLM error, use fallback
            return self._fallback(current_step, next_step)

    # ---------- helpers ----------
    def _build_context(
        self,
        current_step: Dict[str, Any],
        next_step: Optional[Dict[str, Any]],
        page_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        current_action = current_step.get("action", "unknown")
        current_target = self._stringify_target(current_step.get("target"))
        pressed_enter = bool(current_step.get("press_enter", False))

        next_action = next_step.get("action") if next_step else "none"
        next_target = self._stringify_target(next_step.get("target")) if next_step else "none"

        # dom_snapshot expects a list from dom_distill shape; optional
        dom_snapshot = page_state.get("dom_snapshot")
        has_forms = self._guess_has_forms(dom_snapshot)
        has_loading = self._detect_loading(dom_snapshot)

        return {
            "current_action": current_action,
            "current_target": current_target,
            "pressed_enter": pressed_enter,
            "next_action": next_action or "none",
            "next_target": next_target or "none",
            "page_url": page_state.get("url", "unknown"),
            "has_forms": has_forms,
            "has_loading": has_loading,
        }

    def _stringify_target(self, target: Optional[Dict[str, Any]]) -> str:
        if not target:
            return "none"
        parts = []
        for k in ("role", "name", "text", "label", "placeholder", "css"):
            v = target.get(k)
            if v:
                parts.append(f"{k}={v}")
        return ", ".join(parts) if parts else "unspecified"

    def _guess_has_forms(self, dom_snapshot: Any) -> bool:
        if not isinstance(dom_snapshot, list):
            return False
        for el in dom_snapshot:
            role = (el.get("role") or "").lower()
            tag = (el.get("tag") or "").lower()
            if role in ("textbox", "combobox") or tag in ("input", "textarea", "select"):
                return True
        return False

    def _detect_loading(self, dom_snapshot: Any) -> bool:
        if not isinstance(dom_snapshot, list):
            return False
        for el in dom_snapshot:
            text = (el.get("text") or "").lower()
            cls  = (el.get("cls") or "").lower()
            role = (el.get("role") or "").lower()
            if any(tok in text for tok in ("loading", "please wait", "spinner")):
                return True
            if any(tok in cls for tok in ("loading", "spinner", "progress", "skeleton")):
                return True
            if role in ("progressbar", "status"):
                return True
        return False

    def _naive_prompt(self, context: Dict[str, Any]) -> str:
        p = WAIT_DECISION_PROMPT
        for k, v in context.items():
            p = p.replace("{" + k + "}", str(v))
        return p

    def _parse_llm_response(self, text: str) -> WaitDecision:
        s = text.strip()
        # Strip code fences if any
        if s.startswith("```"):
            lines = s.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        # Extract first JSON object
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            s = m.group(0)
        data = json.loads(s)

        # normalize
        should_wait = bool(data.get("should_wait", False))
        wait_strategy = str(data.get("wait_strategy", "none"))
        timeout_ms = int(data.get("timeout_ms", 5000))
        timeout_ms = max(1000, min(30000, timeout_ms))
        target_element = data.get("target_element")
        target_text = data.get("target_text")
        reason = str(data.get("reason", "LLM decision"))

        return WaitDecision(
            should_wait=should_wait,
            wait_strategy=wait_strategy,
            timeout_ms=timeout_ms,
            target_element=target_element,
            target_text=target_text,
            reason=reason,
        )

    # ---------- heuristics fallback ----------
    def _fallback(self, current_step: Dict[str, Any], next_step: Optional[Dict[str, Any]]) -> WaitDecision:
        action = current_step.get("action")
        press_enter = bool(current_step.get("press_enter", False))
        next_action = next_step.get("action") if next_step else None

        # type + press_enter → wait for next field to appear
        if action == "type" and press_enter and next_action == "type":
            return WaitDecision(
                should_wait=True,
                wait_strategy="element_visible",
                timeout_ms=5000,
                target_element=next_step.get("target") if next_step else None,
                reason="Fallback: wait for next field after pressing enter"
            )
        # click → network idle
        if action == "click":
            return WaitDecision(
                should_wait=True,
                wait_strategy="network_idle",
                timeout_ms=8000,
                reason="Fallback: wait for network idle after click"
            )
        # open_url → page load
        if action == "open_url":
            return WaitDecision(
                should_wait=True,
                wait_strategy="network_idle",
                timeout_ms=10000,
                reason="Fallback: wait for page load"
            )
        # otherwise: no wait
        return WaitDecision(
            should_wait=False,
            wait_strategy="none",
            timeout_ms=0,
            reason="Fallback: no wait needed"
        )


# =========================
# Convenience: sample page_state producer (optional)
# =========================
async def collect_light_dom_snapshot(page: Page, max_elems: int = 150) -> Dict[str, Any]:
    """
    Tiny DOM distill for the decider context. Cheap and safe to call.
    Returns: {"url": ..., "dom_snapshot": [ {role, cls, text, tag}, ... ] }
    """
    state: Dict[str, Any] = {"url": page.url}
    try:
        data = await page.evaluate(f"""
            () => Array.from(document.querySelectorAll('a,button,input,textarea,select,[role]'))
                .filter(el => el.offsetParent !== null)
                .slice(0, {int(max_elems)})
                .map(el => ({{
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || (el.tagName==='A'?'link':null),
                    cls: el.className || '',
                    text: (el.innerText||'').trim().slice(0,80)
                }}))
        """)
        state["dom_snapshot"] = data
    except Exception:
        pass
    return state