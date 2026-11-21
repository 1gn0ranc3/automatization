import allure
from playwright.sync_api import Response

from automation.pages.base import BasePage


class LinksPage(BasePage):
    path = "/links"

    def __init__(self, page, base_url):
        super().__init__(page, base_url)
        self.response_fields = page.locator("#linkResponse b")

    @allure.step("Вызвать API через ссылку")
    def follow_api_link(self, name: str, endpoint: str) -> Response:
        url = f"{self.base_url}{endpoint}"
        with self.page.expect_response(
            lambda response: response.url == url and response.request.method == "GET"
        ) as received:
            self.page.get_by_role("link", name=name, exact=True).click()
        return received.value
