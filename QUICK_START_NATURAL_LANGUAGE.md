# Quick Start: Natural Language Mode

Get started with AI-powered natural language testing in 5 minutes!

## Prerequisites

1. Install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

2. Set up API key (choose one):
```bash
# Google Gemini (recommended)
export GOOGLE_API_KEY=your_api_key

# Or OpenAI
export OPENAI_API_KEY=your_api_key
```

## Step 1: Write a Test

Create a file `my_test.feature`:

```gherkin
Feature: Login Test

  Scenario: User logs in successfully
    Given I open "https://example.com"
    When I login with email "user@example.com" and password "secret123"
    Then I should see my dashboard
```

## Step 2: Compile

```bash
python -m automation_phase1.cli \
  --in my_test.feature \
  --out my_test.json \
  --natural-language-mode auto
```

Output:
```
Wrote my_test.json and my_test.provenance.json
```

## Step 3: Run

```bash
python -m automation_phase1.runner \
  --in my_test.json \
  --out proofs \
  --headed
```

Watch the AI agent:
1. Navigate to the page
2. Find and fill the email field
3. Find and fill the password field
4. Find and click the login button
5. Verify the dashboard appears

## Step 4: Check Results

Results are in `proofs/run_*/`:
- `results.json` - Execution details
- `junit.xml` - Test results
- `step_*.png` - Screenshots of each step

## Examples Included

### 1. Simple Login
```bash
python -m automation_phase1.cli \
  --in examples/natural_language_demo.feature \
  --out demo.json \
  --natural-language-mode auto

python -m automation_phase1.runner --in demo.json --out proofs --headed
```

### 2. E-Commerce Flow
```bash
python -m automation_phase1.cli \
  --in examples/ecommerce_nl_demo.feature \
  --out ecommerce.json \
  --natural-language-mode auto

python -m automation_phase1.runner --in ecommerce.json --out proofs --headed
```

## Operating Modes

### Auto (Recommended)
Uses regex for known patterns, natural language for everything else:
```bash
--natural-language-mode auto
```

### Always
Treats all steps as natural language:
```bash
--natural-language-mode always
```

### Never
Traditional mode (requires exact patterns):
```bash
--natural-language-mode never
```

## Tips

1. **Be Specific**: "Click the Submit button" is better than "Click button"
2. **Use Natural Phrasing**: Write like you're talking to a person
3. **Include Details**: "Fill email with user@example.com" vs "Fill form"
4. **Test Incrementally**: Add steps one at a time when developing

## Common Patterns

### Login
```gherkin
When I login with username "admin" and password "secret"
# Or
When I login as an admin user
```

### Search
```gherkin
When I search for "iPhone 15"
# Or
When I type "iPhone 15" in the search box and press enter
```

### Forms
```gherkin
When I fill out the contact form with name "John" and email "john@example.com"
# Or
When I submit my contact information
```

### Navigation
```gherkin
When I go to the settings page
# Or
When I click on the user profile menu
```

### Verification
```gherkin
Then I should see a success message
# Or
Then the page should display "Welcome back"
```

## Troubleshooting

### No API key error
Set `GOOGLE_API_KEY` or `OPENAI_API_KEY` environment variable.

### Element not found
- Wait for page to load (Smart Wait should handle this)
- Be more specific about which element
- Verify the element exists on the page

### Unexpected behavior
- Check `proofs/run_*/results.json` for details
- Review screenshots to see what the agent did
- Make your instructions more specific

## Next Steps

- Read [NATURAL_LANGUAGE.md](NATURAL_LANGUAGE.md) for complete documentation
- Explore [SMART_WAIT.md](SMART_WAIT.md) for automatic waiting
- Check [SMART_SCANNER.md](SMART_SCANNER.md) for intelligent page scanning

## Need Help?

1. Check the documentation files
2. Review example tests in `examples/`
3. Examine `proofs/` output for debugging
4. Try making instructions more specific

Happy testing! 🚀



