import allure


class SeleniumTextBoxPage:
    """Тот же Page Object подход, отдельная реализация для Selenium."""

    def __init__(self, driver, timeout=10):
        from selenium.webdriver.support.ui import WebDriverWait

        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    def _visible(self, selector):
        from selenium.webdriver.support import expected_conditions as conditions

        return self.wait.until(conditions.visibility_of_element_located(("css selector", selector)))

    @allure.step("Открыть Text Box через удалённый Chrome")
    def open(self, base_url):
        self.driver.get(f"{base_url.rstrip('/')}/text-box")

    @allure.step("Заполнить и отправить форму через Selenium")
    def send(self, name, email, current_address, permanent_address):
        from selenium.webdriver.support import expected_conditions as conditions

        for selector, value in (
            ('[placeholder="Full Name"]', name),
            ('[placeholder="name@example.com"]', email),
            ("#currentAddress", current_address),
            ("#permanentAddress", permanent_address),
        ):
            field = self._visible(selector)
            field.clear()
            field.send_keys(value)
        self.wait.until(
            conditions.element_to_be_clickable(("css selector", "button[type=submit]"))
        ).click()

    def output_text(self):
        return self._visible("#output").text

    def output_value(self, field):
        return self._visible(f"#output #{field}").text.partition(":")[2].strip()
