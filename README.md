# Phase 1+2 — Gherkin → JSON → Playwright Runtime

## What it does
- Parses a `.feature` file.
- Compiles each step via regex rules first; if no match and `--use-llm-compiler` is set, falls back to an LLM (strict schema).
- Runs the compiled Scenario with an async Playwright runtime, taking per-step screenshots and writing JUnit XML and results.json.

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

## Compile (Phase 1)
Regex-first:
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
```

Runtime behavior:
- One Chromium browser; one context per scenario; one page per run
- Per-step screenshot: `step_XXX_<action>.png`
- Sensors available: `get_a11y_tree`, `get_dom_distill`, `exists`, `count`
- On error: `step_XXX_error.png`, error recorded, run stops

Artifacts:
- `proofs/run_*/results.json` — step timings and errors
- `proofs/run_*/junit.xml` — one testcase per step
- `proofs/run_*/a11y_tree.json` and `dom_distill.json` — when sensors used

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
- SQLite cache for compiles (when `--cache` provided)
- No visual/a11y/security audits in runtime (Phase 2 sensors only)

