import pytest
from playwright.sync_api import expect

from automation.pages.web_tables import WebTablesPage

pytestmark = pytest.mark.integration


def test_employee_actions_target_exact_email_in_native_row(page):
    page.set_content("""
        <input placeholder="Type to search">
        <table><thead><tr><th>Email</th><th>Action</th></tr></thead><tbody>
        <tr><td>other-qa@example.com</td><td><span title="Edit">Edit</span></td></tr>
        <tr><td>qa@example.com</td><td>
          <span title="Edit" onclick="this.closest('tr').dataset.edited='yes'">Edit</span>
          <span title="Delete" onclick="this.closest('tr').remove()">Delete</span>
        </td></tr></tbody></table>
    """)
    employees = WebTablesPage(page, "http://localhost")
    expect(employees.records).to_have_count(2)
    expect(employees.row("qa@example.com")).to_have_count(1)
    employees.edit("qa@example.com")
    expect(employees.row("qa@example.com")).to_have_attribute("data-edited", "yes")
    employees.delete("qa@example.com")
    expect(employees.row("qa@example.com")).to_have_count(0)
    expect(employees.row("other-qa@example.com")).to_have_count(1)
