import allure
from playwright.sync_api import Page

from automation.pages.base import BasePage


class ButtonsPage(BasePage):
    path = "/buttons"

    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        self.click_result = page.locator("#dynamicClickMessage")
        self.double_click_result = page.locator("#doubleClickMessage")
        self.right_click_result = page.locator("#rightClickMessage")

    @allure.step("Обычный клик")
    def click(self):
        self.page.get_by_role("button", name="Click Me", exact=True).click()

    @allure.step("Двойной клик")
    def double_click(self):
        self.page.get_by_role("button", name="Double Click Me", exact=True).dblclick()

    @allure.step("Клик правой кнопкой")
    def right_click(self):
        self.page.get_by_role("button", name="Right Click Me", exact=True).click(button="right")
