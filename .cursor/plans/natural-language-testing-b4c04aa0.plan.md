<!-- b4c04aa0-ed5d-4035-942d-383a8713cc8e 284a76b1-c810-4f0e-8cb0-4bfb4cd952fa -->
# Transform to Natural Language AI Testing Platform

## Goal

Enable users to write Gherkin in natural language with high-level intents that the LLM interprets and executes at runtime, similar to TestZeus.

## Current Architecture Issues

- Requires specific Gherkin patterns matching regex rules
- Forces explicit selectors and field names
- Cannot express complex multi-step operations in one step
- Compile-time translation limits flexibility

## Proposed Solution

### 1. Create Natural Language Agent

**New file**: `automation_phase1/runner/agents/natural_language_agent.py`

This agent will:

- Accept natural language instructions (e.g., "Login as admin", "Search for iPhone")
- Inspect the page using existing scanning tools (a11y_tree, dom_distill)
- Plan and execute multi-step actions using existing tools (click, type, etc.)
- Return execution results and handle errors gracefully
- Use chain-of-thought reasoning to break down complex intents

Key capabilities:

- Page understanding via accessibility tree and DOM analysis
- Intent decomposition (e.g., "Login" → find username field → type → find password field → type → find login button → click)
- Dynamic selector resolution without explicit naming
- Multi-step operation handling from single instruction

### 2. Update Compiler for Natural Language Pass-Through

**File**: `automation_phase1/compiler.py`

Changes:

- Add new action type: `"natural_language"` to schema
- Detect when a step doesn't match regex patterns
- Instead of requiring LLM to translate to structured JSON, pass through as-is
- Create `Step(action="natural_language", text="Login as admin user")`
- Store original natural language text for runtime interpretation

This eliminates rigid pattern matching at compile time.

### 3. Update Schemas

**File**: `automation_phase1/schemas.py`

Add to Action literal:

```python
Action = Literal[
    "natural_language",  # NEW
    "open_url", "click", "type", ...
]
```

### 4. Enhance Orchestrator for Runtime Interpretation

**File**: `automation_phase1/runner/orchestrator.py`

Changes:

- Add tool mapping for `"natural_language"` action
- When encountering natural language step:

  1. Initialize NaturalLanguageAgent
  2. Provide current page context
  3. Let agent interpret and execute
  4. Record all sub-actions in results

- Maintain full backward compatibility with structured steps

### 5. Update Tool Context

**File**: `automation_phase1/runner/tools.py`

Add new tool function:

```python
async def execute_natural_language(ctx: Ctx, instruction: str, step_num: int) -> Dict[str, Any]:
    """Execute a natural language instruction using AI agent."""
    # Delegate to NaturalLanguageAgent
```

### 6. CLI Enhancement

**File**: `automation_phase1/cli.py`

Add flag:

- `--natural-language-mode` (default: auto-detect)
  - "auto": Use NL agent for unmatched steps
  - "always": Treat all steps as natural language
  - "never": Fail on unmatched steps (current behavior)

### 7. Update Examples

Create new example: `examples/natural_language_demo.feature`

```gherkin
@base_url=https://example.com
Feature: Natural Language Testing

  Scenario: Login and search
    Given I open the homepage
    When I login as admin user
    And I search for "iPhone 15"
    Then I should see search results
```

## Key Design Decisions

1. **Runtime interpretation** - LLM interprets steps during execution with full page context
2. **Backward compatible** - Existing structured steps continue to work
3. **Hybrid approach** - Can mix natural language and structured steps in same scenario
4. **Leverage existing infrastructure** - Uses smart scanner, smart wait, and tool functions
5. **Caching support** - Cache natural language interpretations for speed/consistency

## Benefits

- Users write intuitive, natural test descriptions
- No need to specify exact field names or selectors
- High-level operations in single steps
- AI figures out implementation details
- More maintainable test suites (less brittle)
- Closer to how humans describe test scenarios

## Implementation Order

1. Create natural language agent with core reasoning loop
2. Update schemas to support natural_language action
3. Modify compiler to pass through unmatched steps
4. Wire agent into orchestrator
5. Add CLI options
6. Create examples and documentation

### To-dos

- [ ] Create NaturalLanguageAgent in automation_phase1/runner/agents/natural_language_agent.py with page inspection, intent planning, and action execution capabilities
- [ ] Add 'natural_language' to Action literal in schemas.py
- [ ] Update compiler.py to pass through unmatched steps as natural_language actions instead of failing
- [ ] Add execute_natural_language tool function in tools.py
- [ ] Update orchestrator.py to handle natural_language action type and invoke the agent
- [ ] Add --natural-language-mode flag to cli.py
- [ ] Create natural_language_demo.feature example showing natural language capabilities
- [ ] Update README.md with natural language mode documentation