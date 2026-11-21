import allure

from automation.pages.base import BasePage


class WebTablesPage(BasePage):
    path = "/webtables"

    def __init__(self, page, base_url):
        super().__init__(page, base_url)
        self.dialog = page.get_by_role("dialog")
        self.search_input = page.get_by_placeholder("Type to search", exact=True)
        self.table = page.get_by_role("table")
        self.records = self.table.get_by_role("row").filter(has=page.locator('[title="Edit"]'))

    def row(self, email):
        return self.table.get_by_role("row").filter(
            has=self.page.get_by_role("cell", name=email, exact=True)
        )

    @allure.step("Открыть форму добавления сотрудника")
    def start_add(self):
        self.page.get_by_role("button", name="Add", exact=True).click()

    @allure.step("Заполнить форму сотрудника")
    def fill(self, employee):
        for field, value in employee.items():
            self.dialog.locator(f"#{field}").fill(str(value))

    @allure.step("Сохранить сотрудника")
    def submit(self):
        self.dialog.get_by_role("button", name="Submit", exact=True).click()

    @allure.step("Изменить свою запись")
    def edit(self, email):
        self.row(email).locator('[title="Edit"]').click()

    @allure.step("Удалить свою запись")
    def delete(self, email):
        self.row(email).locator('[title="Delete"]').click()

    @allure.step("Отфильтровать таблицу")
    def search(self, text):
        self.search_input.fill(text)
