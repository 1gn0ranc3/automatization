import pytest
from playwright.sync_api import expect

from automation.api.client import ApiClient
from automation.pages.links import LinksPage

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "name,endpoint,status",
    [
        ("Created", "/created", 201),
        ("No Content", "/no-content", 204),
        ("Not Found", "/invalid-url", 404),
    ],
)
def test_click_sends_http_and_renders_status(page, http_server, name, endpoint, status):
    with ApiClient(http_server.url) as api:
        direct = api.request("GET", endpoint)
    assert direct.status_code == status
    links = LinksPage(page, http_server.url)
    links.open()
    received = links.follow_api_link(name, endpoint)
    assert received.status == direct.status_code
    expect(links.response_fields).to_have_text([str(status), direct.reason])
    assert http_server.calls.count(endpoint) == 2
