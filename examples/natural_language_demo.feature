Feature: Natural Language Testing Demo

  Scenario: Login with natural language
    Given I open "file:///Users/metadome.ai/Desktop/vishal%20backup/Documents/personal/playwright_auto/examples/local_smoke.html"
    When I login with email "test@example.com" and password "password123"
    Then I should see a welcome message

