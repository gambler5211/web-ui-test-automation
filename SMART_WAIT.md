# Smart Wait Agent - LLM-Powered Intelligent Waiting

## Overview

The Smart Wait Agent uses LLM (GPT or Gemini) to automatically determine when and how long to wait during test execution. This eliminates the need for manual `wait` steps in your Gherkin files while handling dynamic content intelligently.

## Features

✅ **Automatic Wait Detection** - LLM analyzes test flow and decides when to wait  
✅ **Context-Aware** - Considers current action, next action, and page state  
✅ **Multiple Wait Strategies** - Element visibility, text appearance, network idle, element removal  
✅ **Caching for Consistency** - Decisions are cached to ensure deterministic behavior  
✅ **Fallback Heuristics** - Works without LLM using smart defaults  
✅ **Zero Gherkin Changes** - Existing tests work without modification  

## How It Works

### 1. Decision Process

After each step, the agent:
1. Captures page state (URL, title, DOM snapshot)
2. Analyzes current step and next step
3. Calls LLM with context
4. LLM decides: wait strategy, timeout, target
5. Executes the wait (or skips if unnecessary)

### 2. Wait Strategies

The LLM can choose from:

- **`element_visible`** - Wait for a specific element to appear
- **`text_appears`** - Wait for text to appear on page
- **`network_idle`** - Wait for network requests to complete
- **`element_gone`** - Wait for loading spinner/overlay to disappear
- **`none`** - No wait needed

### 3. Example Decisions

**Scenario 1: Username → Password Field**
```gherkin
When I type "user@example.com" into the "Email" field and press enter
And I type "password123" into the "Password" field
```

**LLM Decision:**
```json
{
  "should_wait": true,
  "wait_strategy": "element_visible",
  "timeout_ms": 5000,
  "target_element": {"role": "textbox", "name": "Password"},
  "reason": "Wait for password field after pressing enter on username"
}
```

**Scenario 2: Form Submission**
```gherkin
When I click "Submit"
Then I should see "Success"
```

**LLM Decision:**
```json
{
  "should_wait": true,
  "wait_strategy": "text_appears",
  "timeout_ms": 10000,
  "target_text": "Success",
  "reason": "Wait for success message after form submission"
}
```

**Scenario 3: No Wait Needed**
```gherkin
When I type "email@test.com" into the "Email" field
And I type "password" into the "Password" field
```

**LLM Decision:**
```json
{
  "should_wait": false,
  "wait_strategy": "none",
  "timeout_ms": 0,
  "reason": "No dynamic content between consecutive typing"
}
```

## Setup

### 1. Install Dependencies

Already included in `requirements.txt`:
```bash
pip install openai>=1.40.0
# OR
pip install google-generativeai>=0.7.0
```

### 2. Configure API Key

**For OpenAI:**
```bash
export OPENAI_API_KEY="sk-..."
```

**For Gemini:**
```bash
export GOOGLE_API_KEY="your_gemini_api_key"
```

### 3. Run with Smart Wait (Default: Enabled)

```bash
# Smart wait enabled by default
python -m automation_phase1.runner \
  --in scenario.json \
  --out proofs \
  --headed

# Explicitly enable
python -m automation_phase1.runner \
  --in scenario.json \
  --out proofs \
  --smart-wait

# Disable smart wait
python -m automation_phase1.runner \
  --in scenario.json \
  --out proofs \
  --no-smart-wait
```

## Usage Examples

### Example 1: Dynamic Login Flow

```gherkin
@base_url=https://example.com
Feature: Login with Smart Waiting
  Scenario: Multi-step login
    Given I open "/login"
    When I type "user@example.com" into the "Email" field and press enter
    # Smart wait automatically waits for password field to appear
    And I type "password123" into the "Password" field
    And I click "Login"
    # Smart wait automatically waits for success message
    Then I should see "Welcome"
```

**What happens:**
1. After typing email + press enter → waits for password field (5s)
2. After clicking login → waits for network idle + success message (10s)

### Example 2: AJAX Data Loading

```gherkin
Feature: Load Dynamic Data
  Scenario: Search with results
    Given I open "/search"
    When I type "laptop" into the "Search" field
    And I click "Search"
    # Smart wait detects AJAX and waits for network idle
    Then I should see "50 results found"
```

**What happens:**
- After clicking Search → waits for network idle (15s)
- Ensures results are loaded before assertion

### Example 3: Multi-page Form

```gherkin
Feature: Multi-step Checkout
  Scenario: Complete checkout
    Given I open "/cart"
    When I click "Proceed to Checkout"
    # Smart wait detects navigation
    Then I should see "Shipping Information"
    When I type "John Doe" into the "Name" field
    And I click "Continue to Payment"
    # Smart wait waits for payment page
    Then I should see "Payment Method"
```

## Consistency & Caching

### Decision Caching

All LLM decisions are cached in `.smart_wait_cache.db` by key:
- Current action + target
- Next action + target
- Press enter flag

This ensures:
- **Deterministic behavior** - Same test always gets same wait decisions
- **Performance** - No repeated LLM calls for same scenarios
- **Cost savings** - Reduces API calls

### Cache Location

```
proofs/
  .smart_wait_cache.db    # SQLite cache
  run_xxxxx/              # Individual test runs
```

### Clear Cache

```bash
rm proofs/.smart_wait_cache.db
```

## Fallback Behavior

If LLM is unavailable or fails, smart wait uses heuristics:

1. **Type + press_enter → type**: Wait 5s for next field
2. **Click button**: Wait for network idle (8s)
3. **Open URL**: Wait for page load (10s)
4. **Other actions**: No wait

## Configuration

### Custom Model

Set via environment or code:

```python
# In your test framework
smart_wait_agent = SmartWaitAgent(model="gpt-4o")  # OpenAI
# OR
smart_wait_agent = SmartWaitAgent(model="gemini-2.0-flash")  # Gemini
```

### Timeout Ranges

LLM can choose timeouts between:
- **Minimum**: 1000ms (1 second)
- **Maximum**: 30000ms (30 seconds)

Most decisions use 5-15 seconds.

## Troubleshooting

### Issue: LLM not being called

**Check:**
1. API key is set: `echo $OPENAI_API_KEY` or `echo $GOOGLE_API_KEY`
2. Smart wait is enabled: `--smart-wait` (default)
3. Check logs for "[Smart Wait]" messages

### Issue: Decisions not consistent

**Solution:**
- Cache should handle this automatically
- Clear cache and re-run if needed
- Check that test steps are identical

### Issue: Timeouts too short/long

**Solution:**
- LLM learns from context
- Add more descriptive step names
- Provide DOM context (framework does this automatically)

### Issue: Too many API calls

**Solution:**
- Cache is working - should only call once per unique scenario
- Check cache file exists: `ls -la proofs/.smart_wait_cache.db`

## Cost Considerations

### Typical Usage

- **First run**: ~1 LLM call per step transition (cached)
- **Subsequent runs**: 0 LLM calls (uses cache)
- **Token usage**: ~500-1000 tokens per decision

### Example Cost (OpenAI GPT-4o-mini)

For 100-step test suite:
- First run: ~100 decisions × $0.0001 = **$0.01**
- Cached runs: **$0.00**

Very cost-effective!

## Advanced: LLM Prompt

The agent uses this prompt template:

```
You are a smart test automation agent that decides optimal waiting strategies.

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
2. After "type" with press_enter=true → wait for next field to appear
3. After "click" on link → wait for navigation/network idle
4. Before "get_text" or "assert" → wait for the target text/element
5. After "open_url" → wait for page load
6. Between consecutive "type" with press_enter → wait for next input
7. If loading indicators → wait for them to disappear
8. If no dynamic content → no wait

OUTPUT: JSON with should_wait, wait_strategy, timeout_ms, target, reason
```

## Best Practices

1. **Use descriptive names** - LLM understands context better
2. **Keep natural flow** - Write tests as you would manually test
3. **Trust the agent** - Let it decide, don't micro-manage waits
4. **Monitor first runs** - Check logs to see decisions
5. **Cache for CI** - Commit cache file for consistent CI runs

## Comparison: Before vs After

### Before (Manual Waits)

```gherkin
When I type "user@test.com" into "Email" and press enter
And I wait 3000 ms                    # Manual wait
And I type "password" into "Password"
And I click "Login"
And I wait 5000 ms                    # Manual wait
Then I should see "Welcome"
```

### After (Smart Wait)

```gherkin
When I type "user@test.com" into "Email" and press enter
And I type "password" into "Password"   # Auto-waits for field
And I click "Login"                     # Auto-waits for response
Then I should see "Welcome"             # Auto-waits for text
```

Cleaner, more maintainable, adapts to actual page timing!

## Summary

The Smart Wait Agent makes your tests:
- ✅ **Simpler** - No manual wait steps
- ✅ **Smarter** - Adapts to actual page behavior
- ✅ **More reliable** - Handles dynamic content automatically
- ✅ **Consistent** - Cached decisions ensure determinism
- ✅ **Cost-effective** - Minimal API usage with caching

Just write natural Gherkin and let the LLM handle the timing! 🚀


