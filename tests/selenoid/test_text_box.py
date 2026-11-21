from pathlib import Path
from urllib.parse import quote

import allure
import pytest

from automation.pages.selenium_text_box import SeleniumTextBoxPage

pytestmark = [pytest.mark.selenoid, pytest.mark.ui, pytest.mark.regression]


def test_remote_chrome_submits_local_form(remote_driver):
    allure.dynamic.feature("Selenoid · удалённый браузер")
    html = Path(__file__).parents[1].joinpath("integration/components.html").read_text()
    remote_driver.get(f"data:text/html;charset=utf-8,{quote(html, safe='')}")
    form = SeleniumTextBoxPage(remote_driver)
    form.send("Анна Тест", "anna@example.com", "Москва, 1", "Казань, 2")
    assert form.output_text() == "Анна Тест|anna@example.com|Москва, 1|Казань, 2"


@pytest.mark.external
@pytest.mark.demoqa
@pytest.mark.smoke
def test_demoqa_text_box_in_remote_chrome(remote_driver, settings):
    allure.dynamic.feature("DemoQA · Selenoid")
    form = SeleniumTextBoxPage(remote_driver, timeout=settings.ui_timeout / 1000)
    form.open(settings.demoqa_url)
    form.send("Anna Tester", "anna@example.com", "Moscow, 1", "Kazan, 2")
    assert form.output_value("name") == "Anna Tester"
    assert form.output_value("email") == "anna@example.com"
    assert form.output_value("currentAddress") == "Moscow, 1"
    assert form.output_value("permanentAddress") == "Kazan, 2"
