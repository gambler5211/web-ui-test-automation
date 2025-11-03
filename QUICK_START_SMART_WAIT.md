# Smart Wait - Quick Start Guide

## 5-Minute Setup

### Step 1: Set API Key
```bash
# OpenAI (recommended)
export OPENAI_API_KEY="sk-..."

# OR Gemini
export GOOGLE_API_KEY="your_api_key"
```

### Step 2: Write Normal Gherkin (No Changes Needed!)
```gherkin
@base_url=https://example.com
Feature: Login
  Scenario: User login
    Given I open "/login"
    When I type "user@test.com" into "Email" and press enter
    And I type "password" into "Password"
    And I click "Login"
    Then I should see "Welcome"
```

### Step 3: Compile & Run
```bash
# Compile
python -m automation_phase1.cli \
  --in examples/login.feature \
  --out scenario.json

# Run with smart wait (default: enabled)
python -m automation_phase1.runner \
  --in scenario.json \
  --out proofs \
  --headed
```

That's it! The LLM automatically handles all waiting.

## What Happens

### Without Smart Wait
```
❌ Type "user@test.com" → Press Enter
❌ Type "password" → FAILS (password field not visible yet)
```

### With Smart Wait
```
✅ Type "user@test.com" → Press Enter
✅ [Smart Wait] Wait for password field (5s)
✅ Type "password" → SUCCESS
```

## Example Output

```
[Smart Wait] LLM decision: Wait for password field after pressing enter
[Smart Wait] Executing: element_visible (5000ms)
[Smart Wait] ✅ Element visible: role='textbox' name='Password'
[Smart Wait] LLM decision: Wait for network idle after click
[Smart Wait] Executing: network_idle (8000ms)
[Smart Wait] ✅ Network idle
[Smart Wait] Using cached decision: Wait for success message
[Smart Wait] Executing: text_appears (10000ms)
[Smart Wait] ✅ Text appeared: 'Welcome'
```

## Common Scenarios

### 1. Dynamic Field Appearance
```gherkin
When I type "email" into "Email" and press enter
And I type "password" into "Password"  # Auto-waits for field
```
**Smart Wait:** Waits 5s for password field to appear

### 2. Form Submission
```gherkin
When I click "Submit"
Then I should see "Success"  # Auto-waits for success
```
**Smart Wait:** Waits 10s for success message

### 3. AJAX Loading
```gherkin
When I click "Load Data"
Then I should see "Data loaded"  # Auto-waits for data
```
**Smart Wait:** Waits 15s for network idle

### 4. Page Navigation
```gherkin
When I click "Dashboard"
Then I should see "Welcome to Dashboard"  # Auto-waits for navigation
```
**Smart Wait:** Waits 8s for page load

## Disable Smart Wait

```bash
python -m automation_phase1.runner \
  --in scenario.json \
  --out proofs \
  --no-smart-wait
```

## Cost

- **First run**: ~$0.01 per 100 steps
- **All subsequent runs**: $0.00 (cached)

Very affordable!

## Troubleshooting

### "No API key set"
```bash
export OPENAI_API_KEY="sk-..."
# OR
export GOOGLE_API_KEY="your_key"
```

### "LLM error"
Don't worry! It falls back to smart heuristics automatically.

### "Too slow"
First run calls LLM. Second run uses cache (instant).

## That's It!

Smart Wait is:
- ✅ **Enabled by default**
- ✅ **Zero code changes**
- ✅ **Automatic caching**
- ✅ **Fallback safe**

Just write normal Gherkin and let the LLM handle the rest! 🎉

For more details, see [SMART_WAIT.md](SMART_WAIT.md)


