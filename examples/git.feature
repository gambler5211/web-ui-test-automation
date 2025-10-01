@base_url=https://www.github.com
Feature: git login
  Scenario: login for git
    Given I open "/login"
    And I get_dom_distill
    And I get_a11y_tree
    When I type "gambler5211" into the "username" field
    When I type "Vg@12345678" into the "Password" field and press enter
    And I should see text "Incorrect username or password"