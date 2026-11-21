import pytest


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # Эти сценарии проверяют desktop. При 1280px Web Tables может выйти под sidebar.
    # Явно выбранное --device сохраняет собственный viewport.
    return {"viewport": {"width": 1600, "height": 900}, **browser_context_args}
