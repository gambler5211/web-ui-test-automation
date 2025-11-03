from __future__ import annotations
import json
from typing import Optional
from pydantic import ValidationError
from .schemas import Step, Target, Predicate
from .llm_providers import LLMProviderFactory, BaseLLMProvider

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
    """Raised when no LLM provider is configured."""
    pass


class LLMCompiler:
    """
    LLM-powered Gherkin step compiler.
    
    Converts natural language Gherkin steps into structured JSON steps.
    Supports Gemini, OpenAI, and Anthropic.
    """
    
    def __init__(
        self, 
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7, 
        max_tokens: int = 512
    ):
        """
        Initialize LLM Compiler.
        
        Args:
            provider: LLM provider or None for auto-detect
            model: Model name or None for default (gemini-2.5-flash)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
        """
        try:
            self.llm: BaseLLMProvider = LLMProviderFactory.create(
                provider=provider,
                model=model or "gemini-2.5-flash"
            )
            print(f"[LLM Compiler] Initialized with {self.llm}")
        except ValueError as e:
            raise LLMNotConfigured(f"No LLM provider configured: {e}")
        
        self.temperature = temperature
        self.max_tokens = max_tokens

    def compile_step(self, line: str) -> Step:
        """
        Compile a Gherkin step into a structured Step object.
        
        Args:
            line: Gherkin step text
        
        Returns:
            Compiled Step object
        
        Raises:
            ValueError: If LLM returns invalid step
        
        Note: This is a synchronous wrapper around the async LLM call.
              The compiler runs in a sync context, so we use asyncio.run().
        """
        import asyncio
        
        async def _async_compile():
            response_text = await self.llm.generate(
                prompt=line.strip(),
                system_instruction=LLM_SYSTEM_PROMPT,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                json_mode=True
            )
            
            # Log token usage
            usage = self.llm.get_usage()
            if usage:
                print(f"[LLM Compiler] Tokens: {usage}")
            
            return response_text
        
        # Run async code in sync context
        txt = asyncio.run(_async_compile())
        
        # Strip markdown if present
        txt = txt.strip()
        if txt.startswith("```"):
            lines = txt.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            txt = "\n".join(lines)
        
        # Parse JSON
        data = json.loads(txt)
        
        # Validate against Step schema
        try:
            step = Step.model_validate(data)
        except ValidationError as ve:
            raise ValueError(f"LLM returned invalid step: {ve}\nRaw: {txt}")
        
        return step


