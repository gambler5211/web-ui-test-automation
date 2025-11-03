# Natural Language Testing Mode

## Overview

Natural Language Mode transforms your testing platform into an AI-powered test automation system. Instead of writing tests with rigid syntax patterns, you write them in plain English, just like describing test scenarios to a colleague.

## Key Features

### 1. Intuitive Test Authoring
Write tests in natural language without memorizing syntax patterns:

```gherkin
Feature: E-Commerce Shopping
  Scenario: Purchase a product
    Given I open the store homepage
    When I search for "iPhone 15"
    And I add the first product to my cart
    And I proceed to checkout
    Then I should see an order confirmation
```

### 2. High-Level Intent
Express complex operations in single steps:

```gherkin
# Instead of:
When I type "admin@example.com" into the "Email" field
And I type "password123" into the "Password" field
And I click the "Login" button

# You can write:
When I login with email "admin@example.com" and password "password123"

# Or even simpler:
When I login as an admin user
```

### 3. AI-Powered Execution
The Natural Language Agent:
- Analyzes the current page structure
- Understands your intent
- Plans concrete actions
- Executes them automatically
- Handles dynamic content intelligently

## How It Works

### Architecture

```
Gherkin Step (Natural Language)
    ↓
Compiler (marks as "natural_language" action)
    ↓
Runtime Orchestrator
    ↓
Natural Language Agent
    ↓ (analyzes page)
Page Context (a11y tree, DOM)
    ↓ (interprets intent)
LLM (Gemini/OpenAI)
    ↓ (returns action plan)
Execution Engine (click, type, etc.)
```

### Step-by-Step Process

1. **Compile Time**: Unmatched steps are tagged as `natural_language` actions
2. **Runtime**: When a natural language step is encountered:
   - Agent inspects page (accessibility tree, DOM structure)
   - Sends instruction + page context to LLM
   - LLM returns a plan of concrete actions
   - Agent executes each action sequentially

## Operating Modes

### Auto (Default)
Best of both worlds: uses regex for recognized patterns, natural language for everything else.

```bash
python -m automation_phase1.cli \
  --in examples/my_test.feature \
  --out scenario.json \
  --natural-language-mode auto
```

**Use when**: You want maximum flexibility while maintaining speed for standard operations.

### Always
Every step is interpreted as natural language, even simple ones.

```bash
python -m automation_phase1.cli \
  --in examples/my_test.feature \
  --out scenario.json \
  --natural-language-mode always
```

**Use when**: You want complete freedom in how you write tests, or testing the NL agent.

### Never
Traditional mode: all steps must match regex patterns or explicit LLM compilation.

```bash
python -m automation_phase1.cli \
  --in examples/my_test.feature \
  --out scenario.json \
  --natural-language-mode never
```

**Use when**: You want deterministic behavior and strict pattern matching.

## Examples

### Example 1: Login Flow

```gherkin
@base_url=https://myapp.com
Feature: User Authentication

  Scenario: Successful login
    Given I open the homepage
    When I login with username "john@example.com" and password "secret123"
    Then I should see my dashboard
```

The agent will:
1. Find the username/email input field
2. Type the email
3. Find the password field
4. Type the password
5. Find and click the login/submit button
6. Verify dashboard is visible

### Example 2: E-Commerce Shopping

```gherkin
Feature: Product Purchase

  Scenario: Buy a smartphone
    Given I open the store
    When I search for "iPhone 15 Pro"
    And I select the first search result
    And I add it to my shopping cart
    And I go to checkout
    And I complete the purchase
    Then I should see an order confirmation
```

### Example 3: Form Filling

```gherkin
Feature: Contact Form

  Scenario: Submit inquiry
    Given I open the contact page
    When I fill out the contact form with my details
    And I submit the form
    Then I should see a success message
```

The agent will intelligently find and fill form fields based on common patterns.

## Best Practices

### 1. Be Clear and Specific
❌ Bad: "Do something with the button"
✅ Good: "Click the Submit button"

❌ Bad: "Fill the form"
✅ Good: "Fill the contact form with name 'John Doe' and email 'john@example.com'"

### 2. Use Domain-Appropriate Language
Write tests using terminology from your application domain:

```gherkin
# For banking app:
When I transfer $500 from checking to savings

# For social media:
When I post a new status update "Hello World"

# For e-commerce:
When I add 3 units of product "iPhone" to cart
```

### 3. Break Down Complex Scenarios
While natural language allows high-level steps, break very complex operations into logical parts:

```gherkin
# Better readability:
When I navigate to account settings
And I update my email address to "new@example.com"
And I save the changes

# Instead of:
When I change my email to "new@example.com" in settings
```

### 4. Leverage Existing Patterns
The agent understands common patterns:
- Login/signup flows
- Search operations
- Form submissions
- Navigation
- Shopping carts
- CRUD operations

### 5. Mix with Structured Steps
You can combine natural language with traditional structured steps:

```gherkin
Scenario: Mixed approach
  Given I open "/login"
  When I login as admin                     # Natural language
  And I click "Dashboard"                   # Traditional
  Then I navigate to the reports section    # Natural language
```

## Configuration

### API Keys
Natural Language Mode requires an LLM provider. Set one of:

```bash
# For Google Gemini (recommended)
export GOOGLE_API_KEY=your_gemini_api_key

# For OpenAI
export OPENAI_API_KEY=your_openai_api_key
```

### Model Selection
The default model is `gemini-2.0-flash-exp`. You can customize in the code or via environment variables.

### Performance Considerations

1. **Caching**: Compiled steps are cached to avoid redundant LLM calls
2. **Token Usage**: Each natural language step requires an LLM call at runtime
3. **Speed**: Structured steps are faster; use NL for complex operations
4. **Cost**: LLM calls incur API costs; monitor usage in production

## Troubleshooting

### Issue: "No LLM provider configured"
**Solution**: Set `GOOGLE_API_KEY` or `OPENAI_API_KEY` environment variable.

### Issue: Agent misunderstands intent
**Solution**: Be more specific in your instruction. Include details like:
- Which element to interact with
- What values to enter
- Expected outcomes

### Issue: Cannot find element
**Solution**: 
- Ensure the page has loaded before the step executes
- Smart Wait agent should handle this, but you can add explicit waits if needed
- Verify the element actually exists on the page

### Issue: Expensive LLM usage
**Solution**:
- Use `auto` mode to leverage regex for simple patterns
- Cache compiled scenarios
- Consider using Gemini Flash models for better cost/performance

## Comparison with Traditional Mode

| Aspect | Traditional | Natural Language |
|--------|------------|------------------|
| Syntax | Rigid patterns | Free-form English |
| Learning curve | Must learn patterns | Write naturally |
| Flexibility | Limited to defined patterns | Unlimited |
| Speed | Fast (regex matching) | Slower (LLM calls) |
| Maintenance | Update regex rules | No maintenance |
| Cost | No API costs | LLM API costs |
| Best for | Simple, repetitive tests | Complex, varied tests |

## Advanced Usage

### Custom Instructions
You can be very specific about how to perform actions:

```gherkin
When I carefully select the premium plan from the pricing table
```

### Conditional Logic
Express conditions naturally:

```gherkin
When I add the product to cart if it's in stock
```

### Verification Steps
Natural assertions:

```gherkin
Then I should see a confirmation message
Then the cart count should be 3
Then the total price should be correct
```

## Future Enhancements

Planned improvements:
- Multi-page flows (navigation between pages)
- Data-driven testing (table parameters)
- Visual verification
- Mobile gesture support
- API interaction
- Database verification

## Contributing

To extend natural language capabilities:

1. Update the system prompt in `natural_language_agent.py`
2. Add new action types to the execution engine
3. Improve page context extraction
4. Enhance error handling and recovery

## See Also

- [README.md](README.md) - Main documentation
- [SMART_WAIT.md](SMART_WAIT.md) - Smart Wait Agent
- [SMART_SCANNER.md](SMART_SCANNER.md) - Smart Scanner Agent
- [QUICK_START_SMART_WAIT.md](QUICK_START_SMART_WAIT.md) - Quick start guide



