import allure
from playwright.sync_api import Page


class BasePage:
    path = "/"

    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")

    @allure.step("Открыть страницу")
    def open(self) -> None:
        # Реклама может продолжать загрузку: networkidle здесь не нужен.
        self.page.goto(f"{self.base_url}{self.path}", wait_until="domcontentloaded")
