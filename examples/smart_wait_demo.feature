@base_url=file:///Users/metadome.ai/Desktop/vishal backup/Documents/personal/playwright_auto/examples/local_smoke.html
Feature: Smart Wait Demo
  Scenario: Login with smart waiting
    Given I open ""
    When I type "test@example.com" into the "Email" field and press enter
    And I type "password123" into the "Password" field
    And I click "Login"
    Then I should see text "Welcome"


