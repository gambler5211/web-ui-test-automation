"""
Smart Scanner Agent - LLM-powered decision maker for page scanning strategy.

Decides when and how to scan the page:
- Light scans: Fast, basic interactive elements only
- Full scans: Complete a11y tree + DOM distill (expensive)
- Skip: No scan needed

Triggers:
1. After mutating steps (click, type, select)
2. On element resolution failures (auto-retry with fresh scan)
3. On URL changes or major state transitions
"""

import json
import sqlite3
import time
import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, Optional, List
from playwright.async_api import Page, TimeoutError as PWTimeoutError
from ...llm_providers import LLMProviderFactory, BaseLLMProvider


@dataclass
class ScanDecision:
    """Decision from the Smart Scanner Agent."""
    scan_type: str  # "light", "full", "skip"
    reason: str
    confidence: float  # 0.0 to 1.0
    cache_key: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SmartScannerAgent:
    """
    LLM-powered agent that decides when and how to scan the page.
    
    Features:
    - Intelligent scan strategy based on context
    - SQLite caching for consistency
    - Fallback heuristics when LLM fails
    - Rate limiting for expensive full scans
    - Performance monitoring
    """
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        cache_path: Optional[Path] = None,
        temperature: float = 0.7,
        max_full_scans_per_minute: int = 5
    ):
        """
        Initialize Smart Scanner Agent.
        
        Args:
            provider: LLM provider or None for auto-detect
            model: Model name or None for default (gemini-2.0-flash-exp)
            cache_path: Path to SQLite cache
            temperature: Sampling temperature
            max_full_scans_per_minute: Rate limit for expensive full scans
        """
        self.temperature = temperature
        self.max_full_scans_per_minute = max_full_scans_per_minute
        
        # Initialize LLM provider
        try:
            self.llm: Optional[BaseLLMProvider] = LLMProviderFactory.create(
                provider=provider,
                model=model or "gemini-2.0-flash-exp"
            )
            print(f"[Smart Scanner] Initialized with {self.llm}")
        except ValueError as e:
            raise ValueError(f"Smart Scanner requires an LLM provider: {e}")
        
        # SQLite cache for decisions
        self.cache_path = cache_path or Path(".smart_scanner_cache.db")
        self._init_cache()
        
        # Performance tracking
        self.full_scan_timestamps: List[float] = []
        self.last_scan_time: Optional[float] = None
        self.last_scan_type: Optional[str] = None
        self.last_scan_url: Optional[str] = None
        self.failure_history: List[Dict[str, Any]] = []
    
    def _init_cache(self):
        """Initialize SQLite cache for scan decisions."""
        conn = sqlite3.connect(str(self.cache_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_decisions (
                cache_key TEXT PRIMARY KEY,
                scan_type TEXT,
                reason TEXT,
                confidence REAL,
                created_at REAL
            )
        """)
        conn.commit()
        conn.close()
    
    def _get_cached_decision(self, cache_key: str) -> Optional[ScanDecision]:
        """Retrieve cached decision if available."""
        conn = sqlite3.connect(str(self.cache_path))
        row = conn.execute(
            "SELECT scan_type, reason, confidence FROM scan_decisions WHERE cache_key = ?",
            (cache_key,)
        ).fetchone()
        conn.close()
        
        if row:
            return ScanDecision(
                scan_type=row[0],
                reason=row[1],
                confidence=row[2],
                cache_key=cache_key
            )
        return None
    
    def _cache_decision(self, decision: ScanDecision):
        """Cache a scan decision."""
        conn = sqlite3.connect(str(self.cache_path))
        conn.execute(
            """INSERT OR REPLACE INTO scan_decisions 
               (cache_key, scan_type, reason, confidence, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (decision.cache_key, decision.scan_type, decision.reason, 
             decision.confidence, time.time())
        )
        conn.commit()
        conn.close()
    
    def _make_cache_key(self, context: Dict[str, Any]) -> str:
        """Generate cache key from context."""
        # Include relevant context fields for caching
        key_data = {
            "trigger": context.get("trigger"),
            "step_action": context.get("step", {}).get("action"),
            "url": context.get("url"),
            "failure_count": len(context.get("failure_history", [])),
            "last_scan_age": context.get("last_scan_age_seconds", 0) > 5
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]
    
    async def decide_scan_strategy(
        self,
        trigger: str,  # "after_step", "resolution_failure", "state_change"
        step_context: Optional[Dict[str, Any]] = None,
        failure_context: Optional[Dict[str, Any]] = None,
        page_url: Optional[str] = None
    ) -> ScanDecision:
        """
        Main decision method - determines if/how to scan the page.
        
        Args:
            trigger: Why we're considering a scan
            step_context: Current test step info
            failure_context: Info about element resolution failure (if any)
            page_url: Current page URL
        
        Returns:
            ScanDecision with scan_type, reason, confidence
        """
        # Build context for decision
        context = {
            "trigger": trigger,
            "step": step_context or {},
            "failure": failure_context or {},
            "url": page_url,
            "last_scan_age_seconds": self._get_last_scan_age(),
            "last_scan_type": self.last_scan_type,
            "last_scan_url": self.last_scan_url,
            "failure_history": self.failure_history[-3:],  # Last 3 failures
            "full_scans_last_minute": self._count_recent_full_scans()
        }
        
        # Check cache first
        cache_key = self._make_cache_key(context)
        cached = self._get_cached_decision(cache_key)
        if cached:
            return cached
        
        # Check rate limits
        if context["full_scans_last_minute"] >= self.max_full_scans_per_minute:
            return ScanDecision(
                scan_type="light",
                reason="Rate limit: too many full scans recently",
                confidence=1.0,
                cache_key=cache_key
            )
        
        # Call LLM for decision
        try:
            prompt = self._build_prompt(context)
            
            response_text = await self.llm.generate(
                prompt=prompt,
                temperature=self.temperature,
                max_tokens=500,
                json_mode=True
            )
            
            # Log token usage
            usage = self.llm.get_usage()
            if usage:
                print(f"[Smart Scanner] Tokens: {usage}")
            
            # Parse response
            decision_data = self._parse_llm_response(response_text)
            
            decision = ScanDecision(
                scan_type=decision_data.get("scan_type", "light"),
                reason=decision_data.get("reason", "LLM decision"),
                confidence=float(decision_data.get("confidence", 0.7)),
                cache_key=cache_key
            )
            
            self._cache_decision(decision)
            return decision
        except Exception as e:
            print(f"[Smart Scanner] LLM error: {e}, using fallback")
            return self._get_fallback_decision(context, cache_key)
    
    def _build_prompt(self, context: Dict[str, Any]) -> str:
        """Build LLM prompt for scan decision."""
        trigger = context["trigger"]
        step = context["step"]
        failure = context["failure"]
        
        prompt = f"""You are a Smart Scanner Agent that decides when and how to scan a webpage during automated testing.

**Current Context:**
- Trigger: {trigger}
- Current Step: {step.get('action', 'N/A')} on {step.get('target', {}).get('name', 'N/A')}
- Page URL: {context['url']}
- Last Scan: {context['last_scan_type']} ({context['last_scan_age_seconds']:.1f}s ago)
- Recent Failures: {len(context['failure_history'])}

"""
        
        if trigger == "resolution_failure":
            prompt += f"""
**Element Resolution Failed:**
- Target: {failure.get('target', {})}
- Reason: Could not find element on page
- This is an automatic retry attempt

**Question:** Should I scan the page to find this element?
"""
        elif trigger == "after_step":
            prompt += f"""
**Just Executed Step:**
- Action: {step.get('action')}
- This step may have changed the page state

**Question:** Should I scan to capture the new page state?
"""
        elif trigger == "state_change":
            prompt += f"""
**Page State Changed:**
- URL changed or major transition detected
- Previous URL: {context['last_scan_url']}

**Question:** Should I scan to capture the new state?
"""
        
        prompt += """

**Scan Options:**
1. **light**: Fast scan of interactive elements only (buttons, inputs, links) - ~100ms
2. **full**: Complete accessibility tree + DOM structure - ~500-1000ms (expensive!)
3. **skip**: No scan needed, use existing page state

**Decision Criteria:**
- Use "light" for: routine checks, after simple actions, when last scan is recent
- Use "full" for: resolution failures, complex forms, major state changes, when light scan is stale
- Use "skip" for: non-mutating actions, when last scan is very recent (<2s), read-only operations

**Respond with JSON:**
{
  "scan_type": "light" | "full" | "skip",
  "reason": "Brief explanation of why this scan type is appropriate",
  "confidence": 0.0 to 1.0
}
"""
        return prompt
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM response, handling markdown fences and extraction."""
        text = response_text.strip()
        
        # Remove markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Extract JSON object using regex
        import re
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"Could not parse JSON from LLM response: {response_text[:200]}")
    
    def _get_fallback_decision(self, context: Dict[str, Any], cache_key: str) -> ScanDecision:
        """Heuristic-based fallback when LLM fails."""
        trigger = context["trigger"]
        last_scan_age = context["last_scan_age_seconds"]
        
        # Resolution failure → always scan
        if trigger == "resolution_failure":
            # If we just did a light scan, escalate to full
            if context["last_scan_type"] == "light" and last_scan_age < 5:
                return ScanDecision(
                    scan_type="full",
                    reason="Fallback: escalate to full scan after light scan failed",
                    confidence=0.9,
                    cache_key=cache_key
                )
            return ScanDecision(
                scan_type="light",
                reason="Fallback: scan after resolution failure",
                confidence=0.8,
                cache_key=cache_key
            )
        
        # After mutating step
        if trigger == "after_step":
            action = context["step"].get("action")
            if action in ("click", "type", "select"):
                if last_scan_age > 10:
                    return ScanDecision(
                        scan_type="light",
                        reason="Fallback: scan after mutating step (stale)",
                        confidence=0.7,
                        cache_key=cache_key
                    )
        
        # State change
        if trigger == "state_change":
            if context["url"] != context["last_scan_url"]:
                return ScanDecision(
                    scan_type="light",
                    reason="Fallback: scan after URL change",
                    confidence=0.8,
                    cache_key=cache_key
                )
        
        # Default: skip
        return ScanDecision(
            scan_type="skip",
            reason="Fallback: no scan needed",
            confidence=0.6,
            cache_key=cache_key
        )
    
    def _get_last_scan_age(self) -> float:
        """Get seconds since last scan."""
        if self.last_scan_time is None:
            return float('inf')
        return time.time() - self.last_scan_time
    
    def _count_recent_full_scans(self) -> int:
        """Count full scans in the last minute."""
        cutoff = time.time() - 60
        self.full_scan_timestamps = [t for t in self.full_scan_timestamps if t > cutoff]
        return len(self.full_scan_timestamps)
    
    def record_scan(self, scan_type: str, page_url: str):
        """Record that a scan was performed."""
        self.last_scan_time = time.time()
        self.last_scan_type = scan_type
        self.last_scan_url = page_url
        
        if scan_type == "full":
            self.full_scan_timestamps.append(time.time())
    
    def record_failure(self, failure_info: Dict[str, Any]):
        """Record an element resolution failure."""
        self.failure_history.append({
            **failure_info,
            "timestamp": time.time()
        })
        # Keep only last 10 failures
        self.failure_history = self.failure_history[-10:]


async def collect_light_dom_snapshot(page: Page, max_elems: int = 150) -> Dict[str, Any]:
    """
    Light scan: Fast collection of interactive elements only.
    
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
    except Exception as e:
        print(f"Light scan error: {e}")
        state["dom_snapshot"] = []
    return state


async def collect_full_page_scan(page: Page, proofs_dir: Path) -> Dict[str, Any]:
    """
    Full scan: Complete accessibility tree + DOM distill (expensive!).
    
    Returns: {"url": ..., "a11y_tree": [...], "dom_distill": [...]}
    Saves artifacts to proofs_dir for debugging.
    """
    state: Dict[str, Any] = {"url": page.url}
    
    try:
        # Capture accessibility tree
        a11y_tree = await page.accessibility.snapshot(interesting_only=True)
        state["a11y_tree"] = a11y_tree
        
        # Save to proofs
        a11y_path = proofs_dir / f"a11y_tree_{int(time.time())}.json"
        a11y_path.write_text(json.dumps(a11y_tree, indent=2))
        
    except Exception as e:
        print(f"A11y tree capture error: {e}")
        state["a11y_tree"] = []
    
    try:
        # Distill DOM - use the same logic as in tools.py
        dom_distill = await page.evaluate("""
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
        state["dom_distill"] = dom_distill
        
        # Save to proofs
        dom_path = proofs_dir / f"dom_distill_{int(time.time())}.json"
        dom_path.write_text(json.dumps(dom_distill, indent=2))
        
    except Exception as e:
        print(f"DOM distill error: {e}")
        state["dom_distill"] = []
    
    return state


async def perform_scan(
    page: Page,
    decision: ScanDecision,
    proofs_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Execute the scan based on the decision.
    
    Returns: Page state data (light or full scan results)
    """
    if decision.scan_type == "skip":
        return {"url": page.url, "skipped": True}
    
    if decision.scan_type == "light":
        return await collect_light_dom_snapshot(page)
    
    if decision.scan_type == "full":
        if not proofs_dir:
            # Fallback to light if no proofs dir
            return await collect_light_dom_snapshot(page)
        return await collect_full_page_scan(page, proofs_dir)
    
    # Unknown type, default to light
    return await collect_light_dom_snapshot(page)
