from uuid import uuid4

import pytest
from playwright.sync_api import expect

from automation.pages.web_tables import WebTablesPage

pytestmark = [pytest.mark.ui, pytest.mark.demoqa, pytest.mark.external, pytest.mark.regression]


@pytest.fixture
def table(ui_page, settings):
    table = WebTablesPage(ui_page, settings.demoqa_url)
    table.open()
    return table


@pytest.fixture
def employee():
    return {
        "firstName": "Anna",
        "lastName": "Tester",
        # Короткий уникальный email для CRUD; длинные значения — отдельный layout-кейс.
        "userEmail": f"{uuid4().hex[:12]}@example.com",
        "age": "29",
        "salary": "75000",
        "department": "Quality",
    }


def test_add_edit_delete_own_record(table, employee):
    table.start_add()
    table.fill(employee)
    table.submit()
    expect(table.dialog).not_to_be_visible()
    row = table.row(employee["userEmail"])
    expect(row).to_have_count(1)
    for value in employee.values():
        expect(row).to_contain_text(value)
    table.edit(employee["userEmail"])
    table.fill({"salary": "85000", "department": "Automation"})
    table.submit()
    expect(table.dialog).not_to_be_visible()
    expect(row).to_contain_text("85000")
    expect(row).to_contain_text("Automation")
    expect(row).not_to_contain_text("75000")
    table.delete(employee["userEmail"])
    expect(row).to_have_count(0)


def test_search_and_reset_preserve_record(table, employee):
    table.start_add()
    table.fill(employee)
    table.submit()
    expect(table.dialog).not_to_be_visible()
    table.search(employee["userEmail"])
    expect(table.row(employee["userEmail"])).to_have_count(1)
    table.search(f"missing-{uuid4().hex}")
    expect(table.table).to_be_visible()
    expect(table.records).to_have_count(0)
    expect(table.row(employee["userEmail"])).to_have_count(0)
    table.search("")
    expect(table.row(employee["userEmail"])).to_have_count(1)


@pytest.mark.parametrize("email", ["plainaddress", "anna@", "@example.com"])
def test_invalid_email_does_not_create_record(table, employee, email):
    table.start_add()
    table.fill({**employee, "userEmail": email})
    table.submit()
    expect(table.dialog).to_be_visible()
    expect(table.dialog.locator("#userEmail:invalid")).to_be_visible()
    expect(table.row(email)).to_have_count(0)
