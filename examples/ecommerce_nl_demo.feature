Feature: E-Commerce Natural Language Testing

  Scenario: Shop for products using natural language
    Given I open "file:///Users/metadome.ai/Desktop/vishal%20backup/Documents/personal/playwright_auto/examples/ecommerce_demo.html"
    When I search for "iPhone"
    And I add the iPhone to my cart
    And I proceed to checkout
    Then I should see an order confirmation

