from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional


PROMPT = (
    "You are a selector resolver for web automation. Given a user's intent (action/target/text) "
    "and page inventories (a11y_tree, dom_distill), propose a Target JSON.\n\n"
    "CRITICAL: For textbox inputs with empty or missing 'name' in a11y_tree:\n"
    "- Count how many textbox elements exist\n"
    "- If multiple textboxes, use CSS to target the specific form/position\n"
    "- Example: Login page email field → {\"css\": \"form input[type='text']:nth-of-type(1)\"}\n"
    "- Example: Search box input → can use role if it has unique name\n\n"
    "Rules:\n"
    "1. NEVER use 'text' selector for input elements\n"
    "2. Check a11y_tree for role='textbox' with name=\"\" (empty) - use CSS\n"
    "3. For login/email inputs with no attributes: {\"css\": \"input[type='text']\"}\n\n"
    "Return ONLY a single JSON object with ONE of: role, name, label, placeholder, text, or css."
)


class LLMResolverAgent:
    def __init__(self, model: str | None = None, temperature: float = 0.0, max_tokens: int = 256):
        # Provider auto-detect (reuse envs from llm_client): OpenAI or Gemini
        self.provider = None
        self.api_key = None
        if os.getenv("OPENAI_API_KEY"):
            self.provider = "openai"
            self.api_key = os.getenv("OPENAI_API_KEY")
        elif os.getenv("GOOGLE_API_KEY"):
            self.provider = "gemini"
            self.api_key = os.getenv("GOOGLE_API_KEY")
        self.model = model or ("gpt-4o-mini" if self.provider == "openai" else "gemini-2.5-flash")
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def propose_target(self, step: Dict[str, Any], a11y_tree: Optional[Dict[str, Any]] = None, dom_distill: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        print(f"[LLM Resolver] Called with provider={self.provider}, model={self.model}")
        print(f"[LLM Resolver] Has a11y_tree: {a11y_tree is not None}, Has dom_distill: {dom_distill is not None}")
        if not self.provider:
            print("[LLM Resolver] No provider configured, returning empty dict")
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
            if self.provider == "openai":
                from openai import OpenAI
                print(f"[LLM Resolver] Calling OpenAI {self.model}...")
                client = OpenAI(api_key=self.api_key)
                resp = client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    messages=[
                        {"role": "system", "content": PROMPT},
                        {"role": "user", "content": user_text},
                    ],
                    response_format={"type": "json_object"},
                )
                txt = resp.choices[0].message.content
                # Token usage (OpenAI)
                try:
                    usage = resp.usage
                    if usage:
                        print(f"[LLM Resolver] Tokens (OpenAI): prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}")
                except Exception:
                    pass
            else:
                import google.generativeai as genai
                print(f"[LLM Resolver] Calling Gemini {self.model}...")
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel(self.model, system_instruction=PROMPT)
                resp = model.generate_content([user_text], generation_config={"temperature": self.temperature})
                txt = resp.text
                # Token usage (Gemini)
                try:
                    um = getattr(resp, "usage_metadata", None)
                    if um:
                        print(f"[LLM Resolver] Tokens (Gemini): prompt={um.prompt_token_count}, candidates={um.candidates_token_count}, total={um.total_token_count}")
                except Exception:
                    pass
            print(f"[LLM Resolver] Response: {txt}")
            # Strip markdown code fences if present
            txt = txt.strip()
            if txt.startswith("```"):
                lines = txt.split("\n")
                # Remove first line (```json or ```)
                lines = lines[1:]
                # Remove last line if it's ```
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
        return clean


