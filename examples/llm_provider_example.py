"""
Example: Using the Unified LLM Provider System

This demonstrates how to use the new unified LLM provider architecture.
All agents now support Gemini, OpenAI, and Anthropic seamlessly!
"""

import asyncio
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from automation_phase1.llm_providers import LLMProviderFactory


async def demo_basic_usage():
    """Basic usage - auto-detect provider from environment."""
    print("=" * 60)
    print("DEMO 1: Auto-detect Provider")
    print("=" * 60)
    
    try:
        # Auto-detect from environment variables
        provider = LLMProviderFactory.create()
        print(f"✓ Created provider: {provider}\n")
        
        # Generate completion
        response = await provider.generate(
            prompt="What is 2 + 2? Respond with just the number.",
            temperature=0.0,
            max_tokens=10
        )
        
        print(f"Prompt: What is 2 + 2?")
        print(f"Response: {response}")
        
        # Show token usage
        usage = provider.get_usage()
        if usage:
            print(f"Tokens used: {usage}\n")
    
    except ValueError as e:
        print(f"✗ No provider configured: {e}\n")


async def demo_explicit_provider():
    """Explicitly choose a provider."""
    print("=" * 60)
    print("DEMO 2: Explicit Provider Selection")
    print("=" * 60)
    
    # Check available providers
    available = LLMProviderFactory.list_available_providers()
    print("Available providers:")
    for name, is_available in available.items():
        status = "✓" if is_available else "✗"
        print(f"  {status} {name}")
    print()
    
    # Try each available provider
    for provider_name, is_available in available.items():
        if is_available:
            try:
                print(f"\nTrying {provider_name}...")
                provider = LLMProviderFactory.create(provider=provider_name)
                
                response = await provider.generate(
                    prompt="Say 'Hello from {provider}'!".replace("{provider}", provider_name),
                    temperature=0.7,
                    max_tokens=20
                )
                
                print(f"  Response: {response}")
                
                usage = provider.get_usage()
                if usage:
                    print(f"  Tokens: {usage}")
            
            except Exception as e:
                print(f"  Error: {e}")


async def demo_json_mode():
    """Use JSON mode for structured output."""
    print("\n" + "=" * 60)
    print("DEMO 3: JSON Mode (Structured Output)")
    print("=" * 60)
    
    try:
        provider = LLMProviderFactory.create()
        
        response = await provider.generate(
            prompt="List 3 programming languages in JSON array format.",
            system_instruction="You are a helpful assistant. Respond ONLY with valid JSON.",
            temperature=0.7,
            max_tokens=100,
            json_mode=True
        )
        
        print(f"Response: {response}")
        
        # Parse the JSON
        import json
        data = json.loads(response)
        print(f"Parsed: {data}")
        print(f"Type: {type(data)}\n")
    
    except Exception as e:
        print(f"Error: {e}\n")


async def demo_custom_models():
    """Use custom models."""
    print("=" * 60)
    print("DEMO 4: Custom Model Selection")
    print("=" * 60)
    
    models = {
        "gemini": "gemini-2.0-flash-exp",
        "openai": "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022"
    }
    
    available = LLMProviderFactory.list_available_providers()
    
    for provider_name, model_name in models.items():
        if available.get(provider_name):
            try:
                print(f"\n{provider_name} with {model_name}:")
                provider = LLMProviderFactory.create(
                    provider=provider_name,
                    model=model_name
                )
                
                response = await provider.generate(
                    prompt="What color is the sky?",
                    temperature=0.0,
                    max_tokens=20
                )
                
                print(f"  Response: {response}")
            
            except Exception as e:
                print(f"  Error: {e}")


async def main():
    """Run all demos."""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "LLM Provider System Demo" + " " * 24 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    await demo_basic_usage()
    await demo_explicit_provider()
    await demo_json_mode()
    await demo_custom_models()
    
    print("\n" + "=" * 60)
    print("All demos completed!")
    print("=" * 60)


if __name__ == "__main__":
    # Make sure you have at least one API key set:
    # export GOOGLE_API_KEY=...
    # export OPENAI_API_KEY=...
    # export ANTHROPIC_API_KEY=...
    
    asyncio.run(main())


