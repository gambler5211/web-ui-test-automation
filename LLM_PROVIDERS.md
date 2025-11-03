# Unified LLM Provider Architecture

## Overview

The playwright automation framework now uses a **unified LLM provider architecture** that standardizes how all AI agents interact with Large Language Models. This makes it easy to:

- **Switch providers** without code changes
- **Add new providers** (Groq, OpenRouter, etc.) with minimal effort
- **Track token usage** consistently across all agents
- **Handle errors** uniformly
- **Mix providers** (e.g., use Gemini for scanning, Claude for natural language)

## Supported Providers

| Provider | Models | API Key Required | Best For |
|----------|--------|------------------|----------|
| **Gemini** | `gemini-2.5-flash`<br>`gemini-2.0-flash-exp`<br>`gemini-1.5-pro` | `GOOGLE_API_KEY` | Fast responses, JSON mode, cost-effective |
| **OpenAI** | `gpt-4o`<br>`gpt-4o-mini`<br>`gpt-3.5-turbo` | `OPENAI_API_KEY` | High quality, structured output |
| **Anthropic** | `claude-3-5-sonnet-20241022`<br>`claude-3-opus`<br>`claude-3-haiku` | `ANTHROPIC_API_KEY` | Long context, reasoning, safety |

## Quick Start

### 1. Set API Key

```bash
# Choose one or more:
export GOOGLE_API_KEY=your_gemini_key
export OPENAI_API_KEY=your_openai_key
export ANTHROPIC_API_KEY=your_claude_key
```

### 2. Auto-Detect Provider

```python
from automation_phase1.llm_providers import LLMProviderFactory

# Automatically uses first available provider (priority: Gemini → OpenAI → Anthropic)
provider = LLMProviderFactory.create()
```

### 3. Explicit Provider

```python
# Use specific provider and model
provider = LLMProviderFactory.create(
    provider="openai",
    model="gpt-4o"
)
```

### 4. Generate Response

```python
response = await provider.generate(
    prompt="What is the capital of France?",
    system_instruction="You are a helpful assistant.",
    temperature=0.7,
    max_tokens=50,
    json_mode=True  # Force JSON output
)
```

### 5. Check Token Usage

```python
usage = provider.get_usage()
print(f"Tokens: {usage}")
# Output: Tokens: prompt=15, completion=8, total=23
```

## Agent-Specific Usage

### LLM Resolver Agent

```python
from automation_phase1.runner.agents.llm_resolver import LLMResolverAgent

# Auto-detect
resolver = LLMResolverAgent()

# Explicit
resolver = LLMResolverAgent(provider="gemini", model="gemini-2.5-flash")

# Use
proposed_target = await resolver.propose_target(step, a11y_tree, dom_distill)
```

### Smart Wait Agent

```python
from automation_phase1.runner.agents.smart_wait_agent import SmartWaitAgent

# Auto-detect
wait_agent = SmartWaitAgent(cache_path=Path("wait_cache.db"))

# Explicit
wait_agent = SmartWaitAgent(
    provider="openai",
    model="gpt-4o-mini",
    cache_path=Path("wait_cache.db")
)

# Use
decision = await wait_agent.decide_wait_strategy(current_step, next_step, page_state)
```

### Smart Scanner Agent

```python
from automation_phase1.runner.agents.smart_scanner_agent import SmartScannerAgent

# Auto-detect
scanner = SmartScannerAgent(cache_path=Path("scanner_cache.db"))

# Explicit
scanner = SmartScannerAgent(
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",
    cache_path=Path("scanner_cache.db")
)

# Use
decision = await scanner.decide_scan_strategy(trigger="after_step", step_context=step)
```

### Natural Language Agent

```python
from automation_phase1.runner.agents.natural_language_agent import NaturalLanguageAgent

# Auto-detect
nl_agent = NaturalLanguageAgent()

# Explicit
nl_agent = NaturalLanguageAgent(
    provider="gemini",
    model="gemini-2.0-flash-exp"
)

# Use
actions = await nl_agent.plan_actions("Login as admin", page_context)
```

### LLM Compiler

```python
from automation_phase1.llm_client import LLMCompiler

# Auto-detect
compiler = LLMCompiler()

# Explicit
compiler = LLMCompiler(provider="openai", model="gpt-4o")

# Use
step = compiler.compile_step("When I click the Login button")
```

## CLI Integration

The unified provider architecture is automatically used when you run tests:

```bash
# Uses auto-detected provider
python -m automation_phase1.runner \
  --in scenario.json \
  --out proofs \
  --use-llm-resolver

# All agents will use Gemini if GOOGLE_API_KEY is set
# or OpenAI if OPENAI_API_KEY is set
# or Anthropic if ANTHROPIC_API_KEY is set
```

## Provider Selection Priority

When auto-detecting (no explicit `provider` argument):

1. **Gemini** - if `GOOGLE_API_KEY` is set
2. **OpenAI** - if `OPENAI_API_KEY` is set  
3. **Anthropic** - if `ANTHROPIC_API_KEY` is set
4. **Error** - if none are set

## Mixing Providers

You can use different providers for different agents:

```python
# Use Gemini for fast scanning decisions
scanner = SmartScannerAgent(provider="gemini", model="gemini-2.5-flash")

# Use Claude for complex natural language understanding
nl_agent = NaturalLanguageAgent(provider="anthropic", model="claude-3-5-sonnet-20241022")

# Use OpenAI for resolving selectors
resolver = LLMResolverAgent(provider="openai", model="gpt-4o-mini")
```

## Features

### Automatic JSON Mode

All providers support forcing JSON output:

```python
response = await provider.generate(
    prompt="List 3 colors",
    json_mode=True  # Response will be valid JSON
)
```

**How it works:**
- **Gemini**: Uses `response_mime_type: "application/json"`
- **OpenAI**: Uses `response_format: {"type": "json_object"}`
- **Anthropic**: Appends JSON instruction to system prompt

### Token Usage Tracking

All providers expose consistent token usage:

```python
provider.generate(...)
usage = provider.get_usage()

print(usage.prompt_tokens)      # Tokens in prompt
print(usage.completion_tokens)  # Tokens in response
print(usage.total_tokens)       # Total
```

### Async/Await Support

All providers use `asyncio.to_thread()` for non-blocking execution:

```python
# Won't block the event loop
response1 = await provider1.generate("Question 1")
response2 = await provider2.generate("Question 2")

# Can run in parallel
results = await asyncio.gather(
    provider1.generate("Question 1"),
    provider2.generate("Question 2")
)
```

## Architecture

```
automation_phase1/
├── llm_providers.py              # NEW - Unified provider system
│   ├── BaseLLMProvider           # Abstract base class
│   ├── GeminiProvider            # Gemini implementation
│   ├── OpenAIProvider            # OpenAI implementation
│   ├── AnthropicProvider         # Anthropic implementation
│   ├── LLMProviderFactory        # Factory for creating providers
│   └── LLMUsage                  # Token usage dataclass
│
├── llm_client.py                 # UPDATED - Uses unified providers
├── runner/agents/
│   ├── llm_resolver.py           # UPDATED - Uses unified providers
│   ├── smart_wait_agent.py       # UPDATED - Uses unified providers
│   ├── smart_scanner_agent.py    # UPDATED - Uses unified providers
│   └── natural_language_agent.py # UPDATED - Uses unified providers
```

## Adding a New Provider

To add support for a new provider (e.g., Groq):

1. **Create provider class in `llm_providers.py`:**

```python
class GroqProvider(BaseLLMProvider):
    def __init__(self, model: str = "llama-3.3-70b-versatile", **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not set")
    
    async def generate(self, prompt: str, **kwargs) -> str:
        # Implementation
        pass
```

2. **Update factory in `llm_providers.py`:**

```python
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-20241022",
    "groq": "llama-3.3-70b-versatile",  # ADD THIS
}

@staticmethod
def create(provider: Optional[str] = None, model: Optional[str] = None) -> BaseLLMProvider:
    if provider == "groq":  # ADD THIS
        return GroqProvider(model=model or "llama-3.3-70b-versatile")
    # ... existing code
```

3. **Done!** All agents automatically support it:

```python
resolver = LLMResolverAgent(provider="groq")
```

## Migration Guide

### Before (Old System)

```python
# Each agent had its own LLM integration
class LLMResolverAgent:
    def __init__(self):
        if os.getenv("GOOGLE_API_KEY"):
            self.provider = "gemini"
            # Gemini-specific code
        # No OpenAI or Anthropic support

class NaturalLanguageAgent:
    def __init__(self):
        if os.getenv("GOOGLE_API_KEY"):
            self.provider = "gemini"
        elif os.getenv("OPENAI_API_KEY"):
            self.provider = "openai"
        # Duplicate provider handling code
```

### After (New System)

```python
# All agents use unified provider
from automation_phase1.llm_providers import LLMProviderFactory

class LLMResolverAgent:
    def __init__(self, provider=None, model=None):
        self.llm = LLMProviderFactory.create(provider, model)
        # Works with Gemini, OpenAI, or Anthropic!

class NaturalLanguageAgent:
    def __init__(self, provider=None, model=None):
        self.llm = LLMProviderFactory.create(provider, model)
        # Same simple API!
```

## Benefits

✅ **Standardized** - All agents use the same interface  
✅ **Flexible** - Easy to switch providers or models  
✅ **Extensible** - Add new providers in one place  
✅ **Consistent** - Token tracking, error handling, JSON mode  
✅ **Testable** - Easy to mock providers for testing  
✅ **Maintainable** - Fix bugs once, benefits all agents

## Example Output

```bash
[LLM Resolver] Initialized with GeminiProvider(model=gemini-2.5-flash)
[LLM Resolver] Calling GeminiProvider(model=gemini-2.5-flash)...
[LLM Resolver] Tokens: prompt=150, completion=25, total=175
[LLM Resolver] Parsed JSON: {'role': 'button', 'name': 'Login'}

[Smart Wait] Initialized with OpenAIProvider(model=gpt-4o-mini)
[Smart Wait] Tokens: prompt=300, completion=45, total=345

[NL Agent] Initialized with AnthropicProvider(model=claude-3-5-sonnet-20241022)
[NL Agent] Tokens: prompt=450, completion=120, total=570
```

## Cost Comparison

Approximate costs per 1M tokens (as of Oct 2024):

| Provider | Model | Input | Output | Best For |
|----------|-------|-------|--------|----------|
| Gemini | gemini-2.5-flash | $0.075 | $0.30 | High volume |
| OpenAI | gpt-4o-mini | $0.15 | $0.60 | General use |
| OpenAI | gpt-4o | $2.50 | $10.00 | Complex tasks |
| Anthropic | claude-3-haiku | $0.25 | $1.25 | Speed + quality |
| Anthropic | claude-3-5-sonnet | $3.00 | $15.00 | Best quality |

**Recommendation:** Start with Gemini for cost-effectiveness, use Claude for complex natural language understanding.

## Troubleshooting

### "No LLM provider configured"

Set at least one API key:
```bash
export GOOGLE_API_KEY=your_key
```

### "Provider requires API key"

Make sure the key is exported in your current shell.

### JSON parsing errors

Some providers occasionally add markdown. The system automatically strips ` ```json` fences.

### Rate limits

Each provider has different rate limits. Use caching to reduce API calls.

## See Also

- [Natural Language Testing](NATURAL_LANGUAGE.md)
- [Smart Wait Agent](SMART_WAIT.md)
- [Smart Scanner Agent](SMART_SCANNER.md)
- [Example Script](examples/llm_provider_example.py)


