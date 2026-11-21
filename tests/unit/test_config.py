import pytest

from automation.config import Settings, validate_base_url


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch):
    for name in (
        "DEMOQA_BASE_URL",
        "REQRES_BASE_URL",
        "FAKESTORE_BASE_URL",
        "REQRES_API_KEY",
        "API_TIMEOUT_SECONDS",
        "UI_TIMEOUT_MS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_read_current_environment_and_normalize_urls(monkeypatch):
    original = Settings.from_env()
    monkeypatch.setenv("DEMOQA_BASE_URL", " https://example.com/demo/ ")
    monkeypatch.setenv("REQRES_API_KEY", " test-key ")
    monkeypatch.setenv("API_TIMEOUT_SECONDS", "2.5")
    current = Settings.from_env()
    assert original.demoqa_url == "https://demoqa.com"
    assert current.demoqa_url == "https://example.com/demo"
    assert current.reqres_api_key == "test-key"
    assert current.api_timeout == 2.5


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "https://",
        "https://user:secret@example.com",
        "https://example.com?key=secret",
        "https://example.com#fragment",
        "https://example.com:invalid",
        "https://example.com:65536",
        "https://[broken",
        "https://exa mple.com",
        "https://example.com\\@other.com",
    ],
)
def test_invalid_url_fails_at_configuration_boundary(monkeypatch, url):
    monkeypatch.setenv("DEMOQA_BASE_URL", url)
    with pytest.raises(ValueError, match="DEMOQA_BASE_URL"):
        Settings.from_env()


@pytest.mark.parametrize("name", ["API_TIMEOUT_SECONDS", "UI_TIMEOUT_MS"])
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "abc"])
def test_invalid_timeout_fails_at_configuration_boundary(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        Settings.from_env()


def test_settings_repr_omits_api_key(monkeypatch):
    monkeypatch.setenv("REQRES_API_KEY", "private-test-key")
    assert "private-test-key" not in repr(Settings.from_env())


def test_direct_url_validation_rejects_null_byte():
    with pytest.raises(ValueError, match="base_url"):
        validate_base_url("https://example.com/\x00")
