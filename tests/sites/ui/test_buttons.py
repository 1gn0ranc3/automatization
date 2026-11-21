import pytest
from playwright.sync_api import expect

from automation.pages.buttons import ButtonsPage

pytestmark = [pytest.mark.ui, pytest.mark.regression, pytest.mark.external, pytest.mark.demoqa]


@pytest.fixture
def buttons(ui_page, settings):
    buttons = ButtonsPage(ui_page, settings.demoqa_url)
    buttons.open()
    return buttons


def test_click(buttons):
    buttons.click()
    expect(buttons.click_result).to_have_text("You have done a dynamic click")


def test_double_click(buttons):
    buttons.double_click()
    expect(buttons.double_click_result).to_have_text("You have done a double click")


def test_right_click(buttons):
    buttons.right_click()
    expect(buttons.right_click_result).to_have_text("You have done a right click")
