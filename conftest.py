import pytest

pytest_plugins = ["automation.telemetry.pytest_plugin", "automation.browser_plugin"]


@pytest.fixture(scope="session")
def base_url(pytestconfig):
    # conftest имеет приоритет над поздно зарегистрированным fallback Playwright.
    # В обычном plugin-модуле фикстура могла быть перекрыта методом экземпляра.
    return pytestconfig.getoption("--base-url") or pytestconfig.getini("base_url") or None
