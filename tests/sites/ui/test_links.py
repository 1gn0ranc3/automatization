import pytest
from playwright.sync_api import expect

from automation.pages.links import LinksPage

pytestmark = [
    pytest.mark.ui,
    pytest.mark.demoqa,
    pytest.mark.external,
    pytest.mark.regression,
    pytest.mark.e2e,
]


@pytest.mark.parametrize(
    "name,endpoint,status,reason",
    [
        pytest.param("Created", "/created", 201, "Created", marks=pytest.mark.smoke),
        pytest.param("No Content", "/no-content", 204, "No Content"),
        pytest.param("Not Found", "/invalid-url", 404, "Not Found"),
    ],
    ids=["created", "no-content", "not-found"],
)
def test_link_displays_actual_api_status(
    ui_page, settings, demoqa_api, name, endpoint, status, reason
):
    direct = demoqa_api.request("GET", endpoint)
    assert direct.status_code == status
    links = LinksPage(ui_page, settings.demoqa_url)
    links.open()
    browser_response = links.follow_api_link(name, endpoint)
    assert browser_response.status == direct.status_code
    expect(links.response_fields).to_have_text([str(status), reason])
