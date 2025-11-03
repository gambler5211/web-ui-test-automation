# Phase 1+2 — Gherkin → JSON → Playwright Runtime

## What it does
- Parses a `.feature` file.
- Compiles each step via regex rules first; if no match and `--use-llm-compiler` is set, falls back to an LLM (strict schema).
- Runs the compiled Scenario with an async Playwright runtime, taking per-step screenshots and writing JUnit XML and results.json.
- **NEW: Natural Language Mode** - Write tests in plain English! The AI agent interprets high-level instructions (e.g., "Login as admin", "Search for iPhone") and executes them intelligently.
- **NEW: Smart Wait Agent** - LLM automatically determines when and how long to wait for dynamic content (no manual waits needed!).
- **NEW: Smart Scanner Agent** - LLM intelligently decides when and how to scan the page, auto-scanning on element resolution failures.

## Install
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

Optional (LLM fallback):
```
export OPENAI_API_KEY=sk-...
# or Gemini
export GOOGLE_API_KEY=your_gemini_api_key
## Optional: choose model (defaults to gemini-2.5-flash when GOOGLE_API_KEY is set)
# python -m automation_phase1.cli --llm-model gemini-2.5-flash ...
```

## Authoring
- Write a `.feature` file. You can set a base URL via a tag:
```
@base_url=https://example.com
Feature: Login
  Scenario: Happy path
    Given I open "/login"
    When I type "user@example.com" into the "Email" field
    And I type "secret" into "Password" and press enter
    Then I should see text "Welcome"
```

## Natural Language Mode (NEW!) 🚀

Write tests in plain English without worrying about exact syntax! The AI agent interprets your intent and executes actions intelligently.

👉 **[Quick Start Guide](QUICK_START_NATURAL_LANGUAGE.md)** | **[Full Documentation](NATURAL_LANGUAGE.md)**

### Example
```gherkin
Feature: E-Commerce Testing
  Scenario: Shop for products
    Given I open the store homepage
    When I search for "iPhone"
    And I add the iPhone to my cart
    And I proceed to checkout
    Then I should see an order confirmation
```

### Modes

**Auto (default)**: Uses natural language for unmatched steps, regex for recognized patterns
```bash
python -m automation_phase1.cli \
  --in examples/ecommerce_nl_demo.feature \
  --out scenario.json \
  --natural-language-mode auto
```

**Always**: Treats ALL steps as natural language (maximum flexibility)
```bash
python -m automation_phase1.cli \
  --in examples/ecommerce_nl_demo.feature \
  --out scenario.json \
  --natural-language-mode always
```

**Never**: Requires exact pattern matches (traditional mode)
```bash
python -m automation_phase1.cli \
  --in examples/sample.feature \
  --out scenario.json \
  --natural-language-mode never
```

### How it works
1. At compile time: Unmatched steps are marked as `natural_language` actions
2. At runtime: The Natural Language Agent:
   - Inspects the page (accessibility tree, DOM structure)
   - Interprets your instruction
   - Plans concrete actions (click, type, etc.)
   - Executes them step-by-step

### Benefits
- Write tests like you describe them to a colleague
- No need to specify exact field names or selectors
- High-level operations in single steps (e.g., "Login as admin")
- AI figures out implementation details automatically
- More maintainable, less brittle tests

## Compile (Phase 1)
Regex-first (traditional):
```
python -m automation_phase1.cli \
  --in examples/sample.feature \
  --out scenario.json
```

With LLM fallback:
```
python -m automation_phase1.cli \
  --in examples/sample.feature \
  --out scenario.json \
  --use-llm-compiler
```

Outputs:
- `scenario.json` — executable Scenario
- `scenario.provenance.json` — source of each compiled step (regex/llm)

## Run (Phase 2)
```
python -m automation_phase1.runner \
  --in scenario.json \
  --out proofs \
  --headed           # optional; show browser
  --smart-wait       # optional; enable LLM-powered smart waiting (default: enabled)
  --autoscan=smart   # optional; smart page scanning (default: smart)
```

**Smart Wait (NEW!)**: The runner uses an LLM to automatically determine when to wait for dynamic content (e.g., password field appearing after pressing enter on username). See [SMART_WAIT.md](SMART_WAIT.md) for details.

**Smart Scanner (NEW!)**: The runner uses an LLM to intelligently decide when and how to scan the page. It automatically scans after mutating steps and on element resolution failures, eliminating the need for manual page inventories. See [SMART_SCANNER.md](SMART_SCANNER.md) for details.

Runtime behavior:
- One Chromium browser; one context per scenario; one page per run
- Per-step screenshot: `step_XXX_<action>.png`
- Sensors available: `get_a11y_tree`, `get_dom_distill`, `exists`, `count`
- On error: `step_XXX_error.png`, error recorded, run stops

Artifacts:
- `proofs/run_*/results.json` — step timings, errors, and scan decisions
- `proofs/run_*/junit.xml` — one testcase per step
- `proofs/run_*/a11y_tree_*.json` and `dom_distill_*.json` — when full scans performed
- `proofs/wait_cache.sqlite3` — cached smart wait decisions
- `proofs/scanner_cache.sqlite3` — cached smart scanner decisions

## Resolver priority (selectors)
`role+name` → `role-only` → `label` → `placeholder` → `text` → `css`

## Base URL precedence
`--base-url` flag > `@base_url=...` scenario tag > `@base_url=...` feature tag

## Output shape (snippet)
```
{
  "meta": {"name": "Happy path", "base_url": "https://example.com"},
  "steps": [
    {"action": "open_url", "url": "/login"},
    {"action": "type", "target": {"role": "textbox", "name": "Email"}, "text": "user@example.com"},
    {"action": "type", "target": {"role": "textbox", "name": "Password"}, "text": "secret", "press_enter": true},
    {"action": "get_text", "target": {"text": "Welcome"}, "save_as": "__seen"}
  ]
}
```

## Troubleshooting
- Install browsers: `python -m playwright install --with-deps chromium`
- Async tests: ensure `pytest-asyncio` is installed
- Can’t find an element? Add sensor steps to your feature:
  - `And I get_dom_distill`
  - `And I get_a11y_tree`
  Inspect generated JSON in `proofs/run_*/` to refine selectors or extend regex rules.

## Design notes
- Deterministic first; LLM is a last resort behind a flag
- SQLite cache for compiles (when `--cache` provided) and smart wait decisions (for consistency)
- Smart wait uses LLM to decide optimal waiting strategies, with caching for deterministic behavior
- No visual/a11y/security audits in runtime (Phase 2 sensors only)

