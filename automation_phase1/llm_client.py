from __future__ import annotations
import json
import os
from typing import Optional
from pydantic import ValidationError
from .schemas import Step, Target, Predicate

LLM_SYSTEM_PROMPT = (
    "You convert individual Gherkin steps into a strict JSON schema for a browser test runner. "
    "Allowed actions: open_url, click, type, select, wait, get_text, assert. "
    "Prefer role+name (ARIA) for targets. Avoid CSS unless explicitly provided. "
    "If the step is an assertion, use get_text + an assert predicate with op equals|contains|exists. "
    "Output ONLY JSON."
)

LLM_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": [
            "open_url", "click", "type", "select", "wait", "get_text", "assert"
        ]},
        "target": {
            "type": "object",
            "properties": {
                "role": {"type": ["string", "null"]},
                "name": {"type": ["string", "null"]},
                "label": {"type": ["string", "null"]},
                "placeholder": {"type": ["string", "null"]},
                "text": {"type": ["string", "null"]},
                "css": {"type": ["string", "null"]}
            },
            "additionalProperties": False
        },
        "url": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "press_enter": {"type": ["boolean", "null"]},
        "press_keys": {"type": ["array", "null"], "items": {"type": "string"}},
        "select_value": {"type": ["string", "null"]},
        "wait_ms": {"type": ["integer", "null"]},
        "save_as": {"type": ["string", "null"]},
        "predicate": {
            "type": ["object", "null"],
            "properties": {
                "op": {"type": "string", "enum": ["equals", "contains", "exists"]},
                "left": {"type": ["string", "null"]},
                "right": {"type": ["string", "null"]}
            },
            "additionalProperties": False
        }
    },
    "required": ["action"],
    "additionalProperties": False
}

class LLMNotConfigured(Exception):
    pass

class LLMCompiler:
    """LLM fallback. Supports OpenAI or Gemini based on env vars.
    Providers:
      - OpenAI: set OPENAI_API_KEY, model like gpt-4o-mini
      - Gemini: set GOOGLE_API_KEY, model like gemini-2.5-flash
    """
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0, max_tokens: int = 512):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider = None
        self.api_key = None
        if os.getenv("OPENAI_API_KEY"):
            self.provider = "openai"
            self.api_key = os.getenv("OPENAI_API_KEY")
        elif os.getenv("GOOGLE_API_KEY"):
            self.provider = "gemini"
            self.api_key = os.getenv("GOOGLE_API_KEY")
            # default to Gemini model if caller didn't override
            if model == "gpt-4o-mini":
                self.model = "gemini-2.5-flash"
        if not self.provider:
            raise LLMNotConfigured("Set OPENAI_API_KEY or GOOGLE_API_KEY to enable LLM fallback.")

    def compile_step(self, line: str) -> Step:
        if self.provider == "openai":
            from openai import OpenAI  # lazy import
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": line.strip()},
                ],
                response_format={"type": "json_object"},
            )
            txt = resp.choices[0].message.content
        else:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model, system_instruction=LLM_SYSTEM_PROMPT)
            resp = model.generate_content([line.strip()], generation_config={"temperature": self.temperature})
            # Gemini response is text; enforce JSON-only system prompt
            txt = resp.text
        data = json.loads(txt)
        try:
            step = Step.model_validate(data)
        except ValidationError as ve:
            raise ValueError(f"LLM returned invalid step: {ve}\nRaw: {txt}")
        return step


