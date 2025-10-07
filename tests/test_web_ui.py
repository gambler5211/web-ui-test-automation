from __future__ import annotations

from automation_phase1.webui import create_app


def test_index_get():
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Automation Phase 1" in response.data
    assert b"Gherkin feature" in response.data


def test_compile_feature_shows_results():
    app = create_app()
    client = app.test_client()

    feature = (
        "Feature: Login\n"
        "  Scenario: Happy path\n"
        "    Given I open \"/login\"\n"
        "    Then I should see text \"Welcome\"\n"
    )

    response = client.post(
        "/",
        data={
            "feature_text": feature,
            "scenario_name": "Happy path",
        },
    )

    assert response.status_code == 200
    assert b"open_url" in response.data
    assert b"get_text" in response.data
