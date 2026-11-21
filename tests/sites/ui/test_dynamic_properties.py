import pytest
from playwright.sync_api import expect

from automation.pages.dynamic_properties import DynamicPropertiesPage

pytestmark = [pytest.mark.ui, pytest.mark.regression, pytest.mark.external, pytest.mark.demoqa]


@pytest.fixture
def dynamic(ui_page, settings):
    dynamic = DynamicPropertiesPage(ui_page, settings.demoqa_url)
    dynamic.open()
    return dynamic


def test_button_becomes_enabled(dynamic):
    expect(dynamic.enable_button).to_be_enabled()


def test_button_becomes_visible(dynamic):
    expect(dynamic.visible_button).to_be_visible()
