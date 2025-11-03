# Smart Scanner Agent 🔍

The **Smart Scanner Agent** is an LLM-powered component that intelligently decides when and how to scan webpages during test execution. It eliminates the need for manual page inventories while keeping tests fast and efficient.

## Overview

Traditional test frameworks require you to manually capture page state (a11y tree, DOM structure) before running tests. The Smart Scanner automates this by:

1. **Deciding when to scan** based on test context and page state
2. **Choosing scan depth** (light vs. full) to balance speed and detail
3. **Auto-scanning on failures** to recover from element resolution errors
4. **Caching decisions** for consistency across test runs

## How It Works

### Scan Types

The Smart Scanner can perform three types of scans:

1. **Light Scan** (~100ms)
   - Fast collection of interactive elements only
   - Captures buttons, inputs, links, and their basic properties
   - Used for routine checks after simple actions

2. **Full Scan** (~500-1000ms)
   - Complete accessibility tree + DOM structure
   - Detailed element information for LLM resolver
   - Used for complex scenarios and element resolution failures

3. **Skip**
   - No scan performed
   - Uses existing page state
   - Used when recent scan is still valid

### Decision Triggers

The Smart Scanner makes decisions at three key points:

#### 1. After Mutating Steps
After actions that change page state (`click`, `type`, `select`, `open_url`):
```python
# Smart Scanner decides: "Should I scan to capture the new state?"
# Considers: last scan age, action type, next step requirements
```

#### 2. On Element Resolution Failures
When an element cannot be found on the page:
```python
# Smart Scanner decides: "Should I scan to find this element?"
# Performs scan → Retries element resolution with fresh state
# If light scan fails → Escalates to full scan
```

#### 3. On State Changes
When major page transitions occur (URL changes, modals, etc.):
```python
# Smart Scanner decides: "Should I scan the new page state?"
# Considers: URL change, previous scan URL, state transition type
```

## Usage

### Basic Usage

Enable Smart Scanner (default mode):
```bash
python -m automation_phase1.runner --in scenario.json --autoscan=smart
```

### Scan Modes

```bash
# Smart mode (default): LLM decides when and how to scan
--autoscan=smart

# Light mode: Always use light scans only
--autoscan=light

# Full mode: Always use full scans (slow but thorough)
--autoscan=full

# Off: Disable auto-scanning (manual inventories required)
--autoscan=off
```

### Combined with Other Features

```bash
# Smart Scanner + LLM Resolver + Smart Wait
python -m automation_phase1.runner \
  --in scenario.json \
  --autoscan=smart \
  --use-llm-resolver \
  --smart-wait
```

## How Smart Scanner Helps

### Scenario 1: Dynamic Content Loading

**Without Smart Scanner:**
```gherkin
Given I open "https://example.com"
When I click on "Load More" button
And I wait 5000 milliseconds  # Manual wait - brittle!
Then I should see "New Content"
```

**With Smart Scanner:**
```gherkin
Given I open "https://example.com"
When I click on "Load More" button
# Smart Scanner automatically:
# 1. Detects the click action
# 2. Scans page after click to capture new content
# 3. No manual wait needed!
Then I should see "New Content"
```

### Scenario 2: Element Not Found

**Without Smart Scanner:**
```
❌ Error: Target has no resolvable selectors
Test fails immediately
```

**With Smart Scanner:**
```
🔍 [Resolver] Element not found, triggering Smart Scanner...
🔍 [Resolver] Scanner decision: light - scan after resolution failure
🔍 [Resolver] Scan complete, retrying element resolution...
✅ [Resolver] Success after scan!
```

### Scenario 3: Multi-Step Form

**Without Smart Scanner:**
```gherkin
Given I open "https://example.com/form"
When I click on "Next" button
And I wait 2000 milliseconds  # Wait for next step
And I type "test@example.com" into email field
And I wait 2000 milliseconds  # Wait for validation
And I click on "Submit" button
And I wait 3000 milliseconds  # Wait for confirmation
```

**With Smart Scanner:**
```gherkin
Given I open "https://example.com/form"
When I click on "Next" button
# Auto-scan after click
And I type "test@example.com" into email field
# Auto-scan after type
And I click on "Submit" button
# Auto-scan after click
# Smart Scanner handles all timing automatically!
```

## LLM Decision Process

The Smart Scanner uses Gemini to make intelligent decisions:

### Example Prompt
```
You are a Smart Scanner Agent that decides when and how to scan a webpage.

Current Context:
- Trigger: resolution_failure
- Current Step: click on "Submit" button
- Page URL: https://example.com/form
- Last Scan: light (3.2s ago)
- Recent Failures: 0

Element Resolution Failed:
- Target: {"role": "button", "name": "Confirm"}
- Reason: Could not find element on page

Question: Should I scan the page to find this element?

Scan Options:
1. light: Fast scan (~100ms)
2. full: Complete scan (~500-1000ms)
3. skip: Use existing state

Respond with JSON:
{
  "scan_type": "light" | "full" | "skip",
  "reason": "Brief explanation",
  "confidence": 0.0 to 1.0
}
```

### Example LLM Response
```json
{
  "scan_type": "light",
  "reason": "Element might have appeared after form submission, light scan should find it",
  "confidence": 0.85
}
```

## Performance & Caching

### SQLite Cache
All scan decisions are cached in SQLite for consistency:
```python
# Cache key based on:
- Trigger type (after_step, resolution_failure, state_change)
- Step action (click, type, etc.)
- Page URL
- Failure count
- Last scan age (>5s or <5s)

# Same context → Same decision (deterministic)
```

### Rate Limiting
Full scans are rate-limited to prevent performance issues:
```python
max_full_scans_per_minute: 5  # Configurable

# If limit exceeded → Falls back to light scan
```

### Performance Metrics
```
Light Scan: ~100ms
Full Scan:  ~500-1000ms
LLM Decision: ~200-500ms (cached: <1ms)

Total overhead per step: ~100-500ms (smart mode)
```

## Integration with Other Agents

### Smart Scanner + LLM Resolver
```python
# Flow:
1. Element not found
2. Smart Scanner scans page (light)
3. Retry with fresh state
4. If still fails → Smart Scanner escalates to full scan
5. LLM Resolver uses full scan data to propose target
6. Retry with LLM-proposed target
7. Success! ✅
```

### Smart Scanner + Smart Wait
```python
# Flow:
1. Click button
2. Smart Wait determines optimal wait strategy
3. Perform wait (network idle, element visible, etc.)
4. Smart Scanner scans page after wait
5. Fresh page state available for next step
```

## Configuration

### In Code
```python
from automation_phase1.runner.agents.smart_scanner_agent import SmartScannerAgent

scanner = SmartScannerAgent(
    cache_path=Path("scanner_cache.sqlite3"),
    model="gemini-2.0-flash-exp",
    temperature=0.7,
    max_full_scans_per_minute=5
)

# Decide scan strategy
decision = await scanner.decide_scan_strategy(
    trigger="after_step",
    step_context={"action": "click", "target": {...}},
    page_url="https://example.com"
)

# Perform scan
scan_data = await perform_scan(page, decision, proofs_dir)
```

### Environment Variables
```bash
export GOOGLE_API_KEY="your-gemini-api-key"
```

## Fallback Behavior

When LLM is unavailable or fails, Smart Scanner uses heuristics:

```python
# Resolution failure → Always scan (light first)
# After mutating step + stale scan (>10s) → Light scan
# URL change → Light scan
# Default → Skip
```

## Debugging

### Enable Verbose Logging
```python
# Scanner prints decision reasoning:
[Resolver] Element not found, triggering Smart Scanner...
[Resolver] Scanner decision: light - scan after resolution failure
[Resolver] Scan complete, retrying element resolution...
[Resolver] Success after scan!
```

### Check Results
```json
// proofs/run_abc123/results.json
{
  "name": "002 click#scan",
  "duration_ms": 0,
  "url": "https://example.com",
  "scan_type": "light",
  "scan_reason": "Scan after mutating step to capture new state"
}
```

### Review Scan Artifacts
```bash
proofs/run_abc123/
├── a11y_tree_1234567890.json    # Full scan artifacts
├── dom_distill_1234567890.json  # Full scan artifacts
└── results.json                  # Scan decisions
```

## Best Practices

1. **Use Smart Mode by Default**
   - Let the LLM decide when to scan
   - Optimal balance of speed and reliability

2. **Enable LLM Resolver with Smart Scanner**
   - They work together to handle dynamic content
   - Auto-scan → Retry → LLM fallback → Success

3. **Monitor Full Scan Usage**
   - Check results.json for scan_type counts
   - Too many full scans? Adjust rate limit or use light mode

4. **Cache Warming**
   - First run builds cache
   - Subsequent runs are faster (cached decisions)

5. **Combine with Smart Wait**
   - Smart Wait handles timing
   - Smart Scanner handles page state
   - Together they eliminate manual waits

## Troubleshooting

### Issue: Too Many Full Scans
**Solution:** Lower the rate limit or use `--autoscan=light`

### Issue: Element Still Not Found After Scan
**Solution:** Enable LLM resolver with `--use-llm-resolver`

### Issue: Scans Too Slow
**Solution:** Use `--autoscan=light` or `--autoscan=off` (manual inventories)

### Issue: LLM Errors
**Solution:** Check `GOOGLE_API_KEY`, fallback heuristics will be used

## Examples

See `examples/smart_scanner_test.html` for a test page demonstrating:
- Delayed element appearance
- Dynamic form loading
- Multi-step interactions

Run the demo:
```bash
# Compile the feature file first
python -m automation_phase1.llm_client \
  --in examples/smart_scanner_demo.feature \
  --out examples/smart_scanner_demo.json

# Run with Smart Scanner
python -m automation_phase1.runner \
  --in examples/smart_scanner_demo.json \
  --autoscan=smart \
  --use-llm-resolver \
  --headed
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Test Orchestrator                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ├─ After mutating step
                              ├─ On element resolution failure
                              └─ On state change
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Smart Scanner Agent                        │
│  ┌────────────────────────────────────────────────────┐    │
│  │  1. Check cache for decision                       │    │
│  │  2. Call LLM with context                          │    │
│  │  3. Parse decision (light/full/skip)               │    │
│  │  4. Cache decision                                 │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Perform Scan                            │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Light: collect_light_dom_snapshot()               │    │
│  │  Full:  collect_full_page_scan()                   │    │
│  │         - capture_a11y_tree()                      │    │
│  │         - distill_dom()                            │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Store in Context                          │
│  ctx.last_scan_data = scan_data                             │
│  ctx.last_scan_type = "light" | "full"                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Used by Resolver & Next Steps                   │
│  - Element resolution retry                                  │
│  - LLM Resolver fallback                                     │
│  - Next scan decision                                        │
└─────────────────────────────────────────────────────────────┘
```

## Summary

The Smart Scanner Agent brings intelligence to page scanning:

✅ **Automatic** - No manual inventories needed
✅ **Intelligent** - LLM decides when and how to scan
✅ **Fast** - Light scans by default, full scans only when needed
✅ **Resilient** - Auto-scan on failures with escalation
✅ **Consistent** - Cached decisions for deterministic behavior
✅ **Integrated** - Works with Smart Wait and LLM Resolver

**Result:** Tests that are simpler to write, faster to run, and more reliable in handling dynamic content.

