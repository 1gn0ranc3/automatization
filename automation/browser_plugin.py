import warnings

import allure
import pytest
from playwright.sync_api import Error, expect


@pytest.fixture
def ui_page(page, settings):
    page.set_default_timeout(settings.ui_timeout)
    page.set_default_navigation_timeout(30_000)
    expect.set_options(timeout=settings.ui_timeout)
    page.on("pageerror", lambda error: allure.attach(str(error), name="Browser JavaScript error"))
    return page


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    # Этот hook срабатывает до teardown: браузер ещё открыт.
    if report.failed and report.when in {"setup", "call"}:
        page = item.funcargs.get("page")
        if page is not None and not page.is_closed():
            try:
                allure.attach(
                    page.screenshot(timeout=5_000),
                    name=f"failure-{report.when}",
                    attachment_type=allure.attachment_type.PNG,
                )
            except Error as exc:
                warnings.warn(f"Скриншот недоступен: {type(exc).__name__}", stacklevel=1)
