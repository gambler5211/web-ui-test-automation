"""
Unified LLM Provider Architecture

This module provides a consistent interface for all LLM providers (Gemini, OpenAI, Anthropic).
All agents use this to interact with LLMs, making it easy to:
- Switch providers without code changes
- Add new providers (Groq, OpenRouter, etc.)
- Track token usage consistently
- Handle errors uniformly
"""

from __future__ import annotations
import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMUsage:
    """Token usage statistics from an LLM call."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    
    def __str__(self) -> str:
        return f"prompt={self.prompt_tokens}, completion={self.completion_tokens}, total={self.total_tokens}"


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.
    
    All providers must implement:
    - generate(): Main method to get completions
    - get_usage(): Return token usage from last call
    """
    
    def __init__(self, model: str, **kwargs):
        self.model = model
        self._last_usage: Optional[LLMUsage] = None
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_mode: bool = False
    ) -> str:
        """
        Generate completion from the LLM.
        
        Args:
            prompt: The user prompt/input
            system_instruction: System prompt (behavior instructions)
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            json_mode: If True, force JSON output
        
        Returns:
            Generated text (JSON string if json_mode=True)
        """
        pass
    
    def get_usage(self) -> Optional[LLMUsage]:
        """Return token usage from the last generate() call."""
        return self._last_usage
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model})"


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider (gemini-2.5-flash, gemini-2.0-flash-exp, etc.)."""
    
    def __init__(self, model: str = "gemini-2.5-flash", **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable not set. "
                "Get your key at https://aistudio.google.com/apikey"
            )
    
    async def generate(
        self,
        prompt: str,
        *,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_mode: bool = False
    ) -> str:
        """Call Gemini API asynchronously."""
        
        def _sync_call() -> str:
            """Synchronous Gemini call (SDK doesn't support async yet)."""
            import google.generativeai as genai
            
            genai.configure(api_key=self.api_key)
            
            # Create model with optional system instruction
            model = genai.GenerativeModel(
                self.model,
                system_instruction=system_instruction
            )
            
            # Build generation config
            gen_config: Dict[str, Any] = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            
            # Enable JSON mode if requested
            if json_mode:
                gen_config["response_mime_type"] = "application/json"
            
            # Generate
            resp = model.generate_content(prompt, generation_config=gen_config)
            
            # Extract usage
            try:
                um = getattr(resp, "usage_metadata", None)
                if um:
                    self._last_usage = LLMUsage(
                        prompt_tokens=getattr(um, "prompt_token_count", 0),
                        completion_tokens=getattr(um, "candidates_token_count", 0),
                        total_tokens=getattr(um, "total_token_count", 0)
                    )
            except Exception:
                self._last_usage = None
            
            return resp.text or ""
        
        # Run in thread pool to avoid blocking event loop
        return await asyncio.to_thread(_sync_call)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider (gpt-4o, gpt-4o-mini, gpt-3.5-turbo, etc.)."""
    
    def __init__(self, model: str = "gpt-4o-mini", **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set. "
                "Get your key at https://platform.openai.com/api-keys"
            )
    
    async def generate(
        self,
        prompt: str,
        *,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_mode: bool = False
    ) -> str:
        """Call OpenAI API asynchronously."""
        
        def _sync_call() -> str:
            """Synchronous OpenAI call."""
            import openai
            
            client = openai.OpenAI(api_key=self.api_key)
            
            # Build messages
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            
            # Build kwargs
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            # Enable JSON mode if requested
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            
            # Generate
            resp = client.chat.completions.create(**kwargs)
            
            # Extract usage
            if resp.usage:
                self._last_usage = LLMUsage(
                    prompt_tokens=resp.usage.prompt_tokens,
                    completion_tokens=resp.usage.completion_tokens,
                    total_tokens=resp.usage.total_tokens
                )
            
            return resp.choices[0].message.content or ""
        
        return await asyncio.to_thread(_sync_call)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider (claude-3-5-sonnet, claude-3-opus, etc.)."""
    
    def __init__(self, model: str = "claude-3-5-sonnet-20241022", **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Get your key at https://console.anthropic.com/settings/keys"
            )
    
    async def generate(
        self,
        prompt: str,
        *,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_mode: bool = False
    ) -> str:
        """Call Anthropic API asynchronously."""
        
        def _sync_call() -> str:
            """Synchronous Anthropic call."""
            import anthropic
            
            client = anthropic.Anthropic(api_key=self.api_key)
            
            # Build kwargs
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            # Add system instruction if provided
            if system_instruction:
                kwargs["system"] = system_instruction
            
            # Note: Claude doesn't have a native JSON mode like OpenAI/Gemini
            # We append JSON instruction to the prompt if needed
            if json_mode and system_instruction:
                kwargs["system"] = system_instruction + "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanations."
            elif json_mode:
                kwargs["system"] = "Respond ONLY with valid JSON. No markdown, no explanations."
            
            # Generate
            resp = client.messages.create(**kwargs)
            
            # Extract usage
            if hasattr(resp, 'usage'):
                self._last_usage = LLMUsage(
                    prompt_tokens=resp.usage.input_tokens,
                    completion_tokens=resp.usage.output_tokens,
                    total_tokens=resp.usage.input_tokens + resp.usage.output_tokens
                )
            
            # Extract text from content blocks
            text_content = ""
            for block in resp.content:
                if hasattr(block, 'text'):
                    text_content += block.text
            
            return text_content
        
        return await asyncio.to_thread(_sync_call)


class LLMProviderFactory:
    """
    Factory for creating LLM providers with auto-detection.
    
    Usage:
        # Auto-detect from environment
        provider = LLMProviderFactory.create()
        
        # Explicit provider
        provider = LLMProviderFactory.create(provider="openai", model="gpt-4o")
        
        # Generate
        response = await provider.generate("What is 2+2?", json_mode=True)
    """
    
    # Default models for each provider
    DEFAULT_MODELS = {
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-20241022",
    }
    
    @staticmethod
    def create(
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> BaseLLMProvider:
        """
        Create an LLM provider instance.
        
        Args:
            provider: Provider name ("gemini", "openai", "anthropic") or None for auto-detect
            model: Model name or None for default
            **kwargs: Additional provider-specific arguments
        
        Returns:
            Configured LLM provider instance
        
        Raises:
            ValueError: If no provider configured or invalid provider name
        
        Provider Priority (when auto-detecting):
            1. Gemini (GOOGLE_API_KEY)
            2. OpenAI (OPENAI_API_KEY)
            3. Anthropic (ANTHROPIC_API_KEY)
        """
        # Auto-detect provider from environment
        if provider is None:
            if os.getenv("GOOGLE_API_KEY"):
                provider = "gemini"
            elif os.getenv("OPENAI_API_KEY"):
                provider = "openai"
            elif os.getenv("ANTHROPIC_API_KEY"):
                provider = "anthropic"
            else:
                raise ValueError(
                    "No LLM provider configured. Set one of:\n"
                    "  - GOOGLE_API_KEY (for Gemini)\n"
                    "  - OPENAI_API_KEY (for OpenAI)\n"
                    "  - ANTHROPIC_API_KEY (for Claude)"
                )
        
        # Normalize provider name
        provider = provider.lower()
        
        # Use default model if not specified
        if model is None:
            model = LLMProviderFactory.DEFAULT_MODELS.get(provider)
            if model is None:
                raise ValueError(f"Unknown provider: {provider}")
        
        # Create provider instance
        if provider == "gemini":
            return GeminiProvider(model=model, **kwargs)
        elif provider == "openai":
            return OpenAIProvider(model=model, **kwargs)
        elif provider == "anthropic":
            return AnthropicProvider(model=model, **kwargs)
        else:
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Supported: gemini, openai, anthropic"
            )
    
    @staticmethod
    def list_available_providers() -> Dict[str, bool]:
        """
        Check which providers are available (have API keys set).
        
        Returns:
            Dict mapping provider name to availability
        """
        return {
            "gemini": bool(os.getenv("GOOGLE_API_KEY")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        }


