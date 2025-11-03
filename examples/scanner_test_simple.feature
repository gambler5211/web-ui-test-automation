Feature: Smart Scanner Simple Test
  Test the Smart Scanner Agent with a local HTML page

Scenario: Test delayed content with Smart Scanner
  Given I open "file:///Users/metadome.ai/Desktop/vishal backup/Documents/personal/playwright_auto/examples/smart_scanner_test.html"
  When I click "Show Delayed Content"
  Then I should see text "This content appeared after 2 seconds!"
