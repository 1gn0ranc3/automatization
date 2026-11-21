"""Remote WebDriver: явные тайм-ауты и освобождение браузерной сессии."""

import os
import warnings
from contextlib import contextmanager

from automation.config import validate_base_url


def create_remote(url, name, version=""):
    url = validate_base_url(url, "SELENOID_URL")
    try:
        from selenium import webdriver
        from selenium.webdriver.remote.client_config import ClientConfig
    except ImportError as exc:
        raise RuntimeError("Установите pip install -r requirements-selenoid.txt") from exc
    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    if version:
        options.browser_version = version
    settings = {"name": name, "sessionTimeout": "2m"}
    if project := os.getenv("SELENOID_PROJECT"):
        settings["labels"] = {"qa.selenoid.project": project}
    options.set_capability("selenoid:options", settings)
    return webdriver.Remote(
        command_executor=url,
        options=options,
        client_config=ClientConfig(remote_server_addr=url, timeout=60),
    )


@contextmanager
def browser_session(factory):
    driver = factory()
    try:
        driver.implicitly_wait(0)
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(10)
        driver.set_window_size(1600, 900)
        yield driver
    except BaseException:
        try:
            driver.quit()
        except Exception as exc:
            # Ошибка очистки не должна заменить исходную ошибку setup/сценария.
            warnings.warn(f"Не удалось закрыть Selenoid: {type(exc).__name__}", stacklevel=2)
        raise
    else:
        driver.quit()
