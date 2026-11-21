import allure
from playwright.sync_api import Page

from automation.pages.base import BasePage


class TextBoxPage(BasePage):
    path = "/text-box"

    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        self.name = page.get_by_placeholder("Full Name", exact=True)
        self.email = page.get_by_placeholder("name@example.com", exact=True)
        self.current_address = page.get_by_placeholder("Current Address", exact=True)
        # У поля нет надёжной accessible label; стабильный id лучше длинного XPath.
        self.permanent_address = page.locator("#permanentAddress")
        self.submit = page.get_by_role("button", name="Submit", exact=True)
        self.output = page.locator("#output")

    @allure.step("Заполнить и отправить форму")
    def send(self, name: str, email: str, current_address: str, permanent_address: str):
        self.name.fill(name)
        self.email.fill(email)
        self.current_address.fill(current_address)
        self.permanent_address.fill(permanent_address)
        self.submit.click()
