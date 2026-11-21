from playwright.sync_api import Page

from automation.pages.base import BasePage


class DynamicPropertiesPage(BasePage):
    path = "/dynamic-properties"

    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
        self.enable_button = page.get_by_role("button", name="Will enable 5 seconds", exact=True)
        self.visible_button = page.get_by_role("button", name="Visible After 5 Seconds", exact=True)
