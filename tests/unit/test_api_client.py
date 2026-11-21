import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests

from automation.api.client import ApiClient
from automation.api.contracts import json_response
from automation.api.reqres import ReqresClient


def response(content_type="application/json", status=200):
    result = requests.Response()
    result.status_code = status
    result.headers["Content-Type"] = content_type
    result._content = b'{"id": 1}'
    result.url = "https://example.com/api/users"
    result.request = requests.Request("GET", result.url).prepare()
    result.elapsed = timedelta(milliseconds=25)
    return result


@pytest.fixture
def client(monkeypatch):
    session = Mock(spec=requests.Session)
    session.headers = {}
    session.request.return_value = response()
    monkeypatch.setattr(requests, "Session", lambda: session)
    client = ReqresClient("https://example.com/", api_key="secret-key", timeout=2.5)
    yield client
    client.close()
    session.close.assert_called_once_with()


def test_request_preserves_transport_policy_and_excludes_secrets_from_report(client, monkeypatch):
    attachment = Mock()
    monkeypatch.setattr("automation.api.client.allure.attach", attachment)
    payload = {"password": "secret-password"}
    result = client.request("POST", "/api/users", json=payload)
    assert result is client.session.request.return_value
    client.session.request.assert_called_once_with(
        "POST", "https://example.com/api/users", timeout=2.5, allow_redirects=False, json=payload
    )
    assert client.session.headers == {"Accept": "application/json", "x-api-key": "secret-key"}
    assert attachment.call_count == 1
    assert "secret-key" not in str(attachment.call_args)
    assert "secret-password" not in str(attachment.call_args)


@pytest.mark.parametrize("path", ["https://other.example/api", "//other.example/api", "api"])
def test_client_rejects_non_relative_paths_before_network(client, path):
    with pytest.raises(ValueError):
        client.request("GET", path)
    client.session.request.assert_not_called()


def test_timeout_propagates_without_retry(client):
    failure = requests.Timeout("request timed out")
    client.session.request.side_effect = failure
    with pytest.raises(requests.Timeout) as caught:
        client.request("GET", "/api/users")
    assert caught.value is failure
    assert client.session.request.call_count == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_failure_is_reported_before_attempting_json(status):
    result = response("text/html", status)
    result._content = b"<html>Unavailable</html>"
    with pytest.raises(AssertionError, match=f"получен {status}"):
        json_response(result)


@pytest.mark.parametrize("content_type", ["application/json", "Application/JSON; charset=utf-8"])
def test_json_content_type_is_case_insensitive(content_type):
    assert json_response(response(content_type)) == {"id": 1}


@pytest.mark.parametrize("content_type", ["text/html", "application/jsonp", ""])
def test_json_content_type_must_match_exactly(content_type):
    with pytest.raises(AssertionError, match="Ожидался JSON"):
        json_response(response(content_type))


def test_query_secrets_are_not_in_http_metadata_or_step(client, monkeypatch):
    attachment, step = Mock(), Mock()
    from contextlib import nullcontext

    step.return_value = nullcontext()
    monkeypatch.setattr("automation.api.client.allure.attach", attachment)
    monkeypatch.setattr("automation.api.client.allure.step", step)
    client.request("GET", "/api/users?token=private-value", params={"password": "other-value"})
    assert step.call_args.args == ("GET /api/users",)
    assert "private-value" not in str(attachment.call_args)
    assert "other-value" not in str(attachment.call_args)
    assert client.session.request.call_args.args[1].endswith("?token=private-value")


def test_contract_error_omits_url_credentials_query_and_fragment():
    result = response(status=403)
    result.url = "https://user:secret@example.com/api/users?token=private#fragment-secret"
    with pytest.raises(AssertionError) as caught:
        json_response(result)
    assert "/api/users" in str(caught.value)
    assert all(word not in str(caught.value) for word in ("secret", "private", "user:"))


@pytest.mark.parametrize("path", [None, "/api\nusers", "/api\\users", "/api#token", "/api\x00"])
def test_invalid_paths_do_not_reach_transport(client, path):
    with pytest.raises(ValueError):
        client.request("GET", path)
    client.session.request.assert_not_called()


@pytest.mark.parametrize("option", [{"timeout": None}, {"allow_redirects": True}])
def test_transport_policy_cannot_be_overridden_by_request(client, option):
    with pytest.raises(ValueError, match="timeout"):
        client.request("GET", "/api", **option)
    client.session.request.assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, True, None, float("nan"), float("inf")])
def test_client_validates_timeout_without_settings(timeout):
    with pytest.raises(ValueError, match="timeout"):
        ApiClient("https://example.com", timeout)


def test_context_manager_closes_session_after_error(monkeypatch):
    session = Mock()
    monkeypatch.setattr(requests, "Session", lambda: session)
    with pytest.raises(RuntimeError):
        with ApiClient("https://example.com"):
            raise RuntimeError("test failed")
    session.close.assert_called_once_with()


def test_rate_limit_metadata_is_allowlisted_and_response_is_not_retried(client, monkeypatch):
    attachment = Mock()
    monkeypatch.setattr("automation.api.client.allure.attach", attachment)
    limited = response(status=429)
    limited.headers.update(
        {"Retry-After": "120", "X-RateLimit-Remaining": "0", "Set-Cookie": "private-cookie"}
    )
    client.session.request.return_value = limited
    assert client.request("GET", "/api/users") is limited
    client.session.request.assert_called_once()
    metadata = json.loads(attachment.call_args.args[0])
    assert metadata["status"] == 429
    assert metadata["rate_limit"] == {"Retry-After": "120", "X-RateLimit-Remaining": "0"}
    assert "private-cookie" not in attachment.call_args.args[0]
