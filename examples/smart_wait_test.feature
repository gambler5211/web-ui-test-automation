@base_url=file:///Users/metadome.ai/Desktop/vishal backup/Documents/personal/playwright_auto/examples/dynamic_form.html
Feature: Smart Wait Demo - Dynamic Form
  
  Scenario: Login with dynamic password field
    Given I open ""
    When I type "user@example.com" into the "Email" field
    And I click "Next"
    # Smart Wait Agent will automatically wait for password field to appear (1 second delay)
    # Without smart wait, this would fail because password field isn't visible yet
    And I type "password123" into the "Password" field
    And I click "Login"
    # Smart Wait Agent will automatically wait for success message (1.5 second delay)
    Then I should see text "Login successful"


