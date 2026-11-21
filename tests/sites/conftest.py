import allure
import pytest

from automation.api.client import ApiClient
from automation.api.contracts import json_response
from automation.api.fakestore import FakeStoreClient
from automation.api.reqres import ReqresClient
from automation.config import Settings
from tests.reqres_snapshot import ReqresSnapshot


@pytest.fixture(autouse=True)
def report_labels(request):
    feature = "Инфраструктура тестов"
    for marker, title in [
        ("fakestore", "Fake Store · Products"),
        ("reqres", "ReqRes"),
        ("demoqa", "DemoQA"),
    ]:
        if request.node.get_closest_marker(marker):
            feature = title
            break
    allure.dynamic.feature(feature)
    allure.dynamic.story(request.node.module.__name__.split(".")[-1].removeprefix("test_"))


@pytest.fixture(scope="session")
def settings():
    return Settings.from_env()


@pytest.fixture(scope="session")
def reqres(settings):
    client = ReqresClient(settings.reqres_url, settings.reqres_api_key, settings.api_timeout)
    yield client
    client.close()


@pytest.fixture(scope="session")
def reqres_snapshot(reqres):
    # Только явное повторное использование GET-данных. Write-запросы идут напрямую.
    return ReqresSnapshot(reqres)


@pytest.fixture(scope="session")
def fakestore(settings):
    client = FakeStoreClient(settings.fakestore_url, settings.api_timeout)
    yield client
    client.close()


@pytest.fixture(scope="session")
def products_catalog(fakestore):
    products = json_response(fakestore.products())
    assert isinstance(products, list) and products, "Ожидается непустой каталог"
    return products


@pytest.fixture(scope="session")
def demoqa_api(settings):
    client = ApiClient(settings.demoqa_url, settings.api_timeout)
    yield client
    client.close()
