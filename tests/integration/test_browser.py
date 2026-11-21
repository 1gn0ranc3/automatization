from pathlib import Path

import pytest
from playwright.sync_api import expect

from automation.pages.buttons import ButtonsPage
from automation.pages.dynamic_properties import DynamicPropertiesPage
from automation.pages.text_box import TextBoxPage

pytestmark = pytest.mark.integration


@pytest.fixture
def component_page(page):
    page.set_content(Path(__file__).with_name("components.html").read_text())
    return page


def test_form_page_object_submits_unicode_in_real_browser(component_page):
    form = TextBoxPage(component_page, "http://localhost")
    form.send("Анна Тест", "anna@example.com", "Москва, 1", "Казань, 2")
    expect(form.output).to_have_text("Анна Тест|anna@example.com|Москва, 1|Казань, 2")


@pytest.mark.parametrize(
    "action,result",
    [
        ("click", "click_result"),
        ("double_click", "double_click_result"),
        ("right_click", "right_click_result"),
    ],
)
def test_mouse_actions_use_real_browser_events(component_page, action, result):
    buttons = ButtonsPage(component_page, "http://localhost")
    getattr(buttons, action)()
    expect(getattr(buttons, result)).to_have_text("done")


def test_dynamic_controls_are_awaited(component_page):
    controls = DynamicPropertiesPage(component_page, "http://localhost")
    expect(controls.enable_button).to_be_disabled()
    expect(controls.visible_button).not_to_be_visible()
    component_page.get_by_role("button", name="Start transition", exact=True).click()
    expect(controls.enable_button).to_be_enabled()
    expect(controls.visible_button).to_be_visible()
