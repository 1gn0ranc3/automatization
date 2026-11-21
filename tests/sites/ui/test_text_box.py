import re

import pytest
from playwright.sync_api import expect

from automation.pages.text_box import TextBoxPage

pytestmark = [pytest.mark.ui, pytest.mark.regression, pytest.mark.external, pytest.mark.demoqa]


@pytest.fixture
def form(ui_page, settings):
    form = TextBoxPage(ui_page, settings.demoqa_url)
    form.open()
    return form


@pytest.mark.smoke
@pytest.mark.parametrize("name", ["Anna Tester", "Анна Тестировщик"], ids=["latin", "cyrillic"])
def test_submit_form(form, name):
    form.send(name, "anna@example.com", "Test street 10", "Test street 20")
    expect(form.output.locator("#name")).to_have_text(f"Name:{name}")
    expect(form.output.locator("#email")).to_have_text("Email:anna@example.com")
    expect(form.output.locator("#currentAddress")).to_contain_text("Test street 10")
    expect(form.output.locator("#permanentAddress")).to_contain_text("Test street 20")


@pytest.mark.parametrize("email", ["plainaddress", "anna@", "@example.com"])
def test_invalid_email_is_rejected(form, email):
    form.send("Anna Tester", email, "Test street 10", "Test street 20")
    expect(form.email).to_have_class(re.compile(r"\bfield-error\b"))
    expect(form.output).to_be_empty()
