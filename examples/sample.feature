Feature: Login
  Scenario: Happy path
    Given I open "/login"
    When I type "user@example.com" into the "Email" field
    And I type "secret" into "Password" and press enter
    Then I should see text "Welcome"


