import os
import warnings

import allure
import pytest

from automation.config import Settings
from automation.selenoid import browser_session, create_remote


@pytest.fixture
def settings():
    return Settings.from_env()


@pytest.fixture
def remote_driver(request):
    with browser_session(
        lambda: create_remote(
            os.getenv("SELENOID_URL", "http://localhost:4444/wd/hub"),
            request.node.nodeid,
            os.getenv("SELENOID_BROWSER_VERSION", ""),
        )
    ) as driver:
        allure.attach(driver.session_id, name="Selenoid session")
        yield driver


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    result = yield
    report = result.get_result()
    driver = item.funcargs.get("remote_driver")
    if report.failed and report.when in {"setup", "call"} and driver is not None:
        try:
            allure.attach(
                driver.get_screenshot_as_png(),
                name=f"selenoid-{report.when}",
                attachment_type=allure.attachment_type.PNG,
            )
        except Exception as exc:
            warnings.warn(f"Скриншот Selenoid недоступен: {type(exc).__name__}", stacklevel=1)
