Feature: Smart Scanner Demo
  Demonstrates the Smart Scanner Agent that intelligently decides when to scan the page

Scenario: Dynamic content loading with auto-scan
  Given I open "https://www.google.com"
  When I click "Search"
  And I type "playwright automation" into the "Search" field
  And I click "Google Search"
  # Smart Scanner will automatically scan after the click to capture new results
  Then I should see text "playwright automation"
  # If an element is not found, Smart Scanner will trigger a scan and retry
  And I click the link "playwright automation"
