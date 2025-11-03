from __future__ import annotations
import json
from typing import Any, Dict, Optional

from ...llm_providers import LLMProviderFactory, BaseLLMProvider


PROMPT = (
    "You are a selector resolver for web automation. Given a user's intent (action/target/text) "
    "and page inventories (a11y_tree, dom_distill), propose a Target JSON.\n\n"
    "Principles:\n"
    "- Prefer accessible, stable selectors: role+name when unique; otherwise label or placeholder; CSS last.\n"
    "- Infer the most appropriate role from a11y_tree for the given accessible name (e.g., textbox vs combobox vs searchbox).\n"
    "- If multiple candidates share the same name, pick the one most relevant to the action (type → text entry control; click → button/link).\n"
    "- Avoid brittle text matches for inputs; avoid deep CSS unless necessary.\n\n"
    "Inventory use:\n"
    "- Use a11y_tree to find nodes by accessible name; read their role to choose role.\n"
    "- Use dom_distill to disambiguate when names are duplicated (e.g., input[type=search]).\n\n"
    "Output:\n"
    "Return ONLY one JSON object with ONE of these strategies: {role+name} | {label} | {placeholder} | {text} | {css}.\n"
)


class LLMResolverAgent:
    def __init__(
        self, 
        provider: Optional[str] = None, 
        model: Optional[str] = None,
        temperature: float = 0.7, 
        max_tokens: int = 256
    ):
        """
        Initialize LLM Resolver Agent.
        
        Args:
            provider: LLM provider ("gemini", "openai", "anthropic") or None for auto-detect
            model: Model name or None for provider default
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        try:
            self.llm: Optional[BaseLLMProvider] = LLMProviderFactory.create(
                provider=provider,
                model=model
            )
            print(f"[LLM Resolver] Initialized with {self.llm}")
        except ValueError as e:
            print(f"[LLM Resolver] No LLM provider available: {e}")
            self.llm = None
        
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def propose_target(self, step: Dict[str, Any], a11y_tree: Optional[Dict[str, Any]] = None, dom_distill: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Propose a target selector using LLM analysis of page inventories.
        
        Args:
            step: Step context (action, target, text)
            a11y_tree: Accessibility tree snapshot
            dom_distill: DOM inventory
        
        Returns:
            Proposed target dict with role/name/label/placeholder/text/css
        """
        print(f"[LLM Resolver] Has a11y_tree: {a11y_tree is not None}, Has dom_distill: {dom_distill is not None}")
        
        if not self.llm:
            print("[LLM Resolver] No LLM provider configured, returning empty dict")
            return {}

        # Trim inventories for prompt size
        def trim(obj: Any, limit: int = 5000) -> str:
            try:
                s = json.dumps(obj)[:limit]
                return s
            except Exception:
                return "{}"

        user_payload = {
            "step": step,
            "a11y_tree": a11y_tree if a11y_tree else None,
            "dom_distill": dom_distill if dom_distill else None,
        }
        user_text = trim(user_payload, 10000)

        try:
            print(f"[LLM Resolver] Calling {self.llm}...")
            
            # Use unified provider
            txt = await self.llm.generate(
                prompt=user_text,
                system_instruction=PROMPT,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                json_mode=True
            )
            
            # Log token usage
            usage = self.llm.get_usage()
            if usage:
                print(f"[LLM Resolver] Tokens: {usage}")
            
            print(f"[LLM Resolver] Response: {txt}")
            
            # Strip markdown code fences if present (some models still add them)
            txt = txt.strip()
            if txt.startswith("```"):
                lines = txt.split("\n")
                lines = lines[1:]  # Remove first line (```json or ```)
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                txt = "\n".join(lines)
            
            data = json.loads(txt)
            print(f"[LLM Resolver] Parsed JSON: {data}")
        except Exception as e:
            print(f"[LLM Resolver] Error: {e}")
            return {}

        # Validate minimal schema
        allowed_keys = {"role", "name", "label", "placeholder", "text", "css"}
        if not isinstance(data, dict):
            return {}
        clean = {k: v for k, v in data.items() if k in allowed_keys and (v is None or isinstance(v, str))}
        
        # Normalize CSS selectors: replace single quotes with double quotes
        if "css" in clean and clean["css"]:
            clean["css"] = clean["css"].replace("'", '"')
        
        # If only 'name' is provided: prefer a11y-informed role inference before generic defaults
        if "name" in clean and clean["name"] and not clean.get("role") and not clean.get("css"):
            step_action = step.get("action") if step else None
            name_lc = str(clean["name"]).strip()

            # Try to infer role from a11y_tree
            def iter_a11y(nodes):
                if not nodes:
                    return
                if isinstance(nodes, dict):
                    nodes = [nodes]
                for n in nodes:
                    try:
                        n_name = (n.get("name") or n.get("accessibleName") or "").strip()
                        n_role = n.get("role")
                        if n_role and n_name and n_name.lower() == name_lc.lower():
                            yield n_role
                        for c in (n.get("children") or []):
                            yield from iter_a11y(c)
                    except Exception:
                        continue

            inferred_role = None
            for r in iter_a11y(a11y_tree):
                # Prefer searchbox/combobox/textbox order for type actions
                if step_action in ["type", "get_text"] and r in ("searchbox", "combobox", "textbox"):
                    inferred_role = r
                    break
                # For click, prefer button/link
                if step_action == "click" and r in ("button", "link"):
                    inferred_role = r
                    break

            if inferred_role:
                clean["role"] = inferred_role
                print(f"[LLM Resolver] A11y-inferred role='{inferred_role}' for name='{clean['name']}'")
            else:
                # Fallback defaults if a11y not helpful
                if step_action in ["type", "get_text"]:
                    clean["role"] = "textbox"
                    print(f"[LLM Resolver] Defaulted role='textbox' for name='{clean['name']}'")
                elif step_action == "click":
                    clean["role"] = "button"
                    print(f"[LLM Resolver] Defaulted role='button' for name='{clean['name']}'")
        
        return clean


