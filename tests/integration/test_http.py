import pytest
import requests

from automation.api.client import ApiClient
from automation.api.contracts import json_response
from automation.api.reqres import ReqresClient

pytestmark = pytest.mark.integration


def test_real_post_preserves_json_query_and_auth(http_server):
    with ReqresClient(http_server.url, api_key="local-test-key") as client:
        result = json_response(
            client.request("POST", "/echo", params={"search": "Иван & Анна"}, json={"id": 7})
        )
    assert result == {
        "method": "POST",
        "query": {"search": ["Иван & Анна"]},
        "body": {"id": 7},
        "api_key": "local-test-key",
    }
    assert http_server.calls == ["/echo"]


def test_real_redirect_is_not_followed(http_server):
    with ApiClient(http_server.url) as client:
        result = client.request("GET", "/redirect")
    assert result.status_code == 302
    assert result.history == []
    assert http_server.calls == ["/redirect"]


def test_real_server_error_is_not_retried(http_server):
    with ApiClient(http_server.url) as client:
        result = client.request("GET", "/unavailable")
    with pytest.raises(AssertionError, match="получен 503"):
        json_response(result)
    assert http_server.calls == ["/unavailable"]


def test_real_read_timeout_propagates_without_retry(http_server):
    with ApiClient(http_server.url, timeout=0.1) as client:
        with pytest.raises(requests.Timeout):
            client.request("GET", "/slow")
    assert http_server.calls == ["/slow"]
