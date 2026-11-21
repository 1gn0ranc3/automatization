from uuid import uuid4

import allure
import pytest

from automation.api.contracts import assert_product, json_response

pytestmark = [pytest.mark.api, pytest.mark.fakestore, pytest.mark.external, pytest.mark.regression]


@pytest.mark.smoke
def test_catalog_contract(products_catalog):
    for product in products_catalog:
        assert_product(product)
    assert len({product["id"] for product in products_catalog}) == len(products_catalog), (
        "Повторяющиеся ID товаров"
    )


def test_product_detail_matches_catalog(fakestore, products_catalog):
    expected = products_catalog[0]
    actual = json_response(fakestore.product(expected["id"]))
    assert_product(actual)
    assert actual == expected


@pytest.mark.parametrize("limit", [1, 5, 100], ids=["one", "subset", "above-catalog-size"])
def test_limit_preserves_catalog_prefix(fakestore, products_catalog, limit):
    actual = json_response(fakestore.products(limit=limit))
    expected = sorted(products_catalog, key=lambda p: p["id"])[:limit]
    assert actual == expected


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_by_id_preserves_all_products(fakestore, products_catalog, direction):
    actual = json_response(fakestore.products(sort=direction))
    expected = sorted(products_catalog, key=lambda p: p["id"], reverse=direction == "desc")
    assert actual == expected


def test_sort_reverses_limited_catalog_prefix(fakestore, products_catalog):
    # В живом прогоне 2026-11-17 первый ID равен 3, а не 20: это соответствует
    # ограничению prefix до сортировки. Полный ожидаемый порядок проверяем явно.
    actual = json_response(fakestore.products(sort="desc", limit=3))
    prefix = sorted(products_catalog, key=lambda p: p["id"])[:3]
    expected = list(reversed(prefix))
    assert [product["id"] for product in actual] == [product["id"] for product in expected]
    assert actual == expected


def test_categories_agree_with_catalog(fakestore, products_catalog):
    categories = json_response(fakestore.categories())
    assert isinstance(categories, list)
    assert all(isinstance(category, str) and category for category in categories)
    assert len(categories) == len(set(categories))
    assert set(categories) == {product["category"] for product in products_catalog}


@pytest.mark.parametrize(
    "category", ["electronics", "jewelery", "men's clothing", "women's clothing"]
)
def test_category_filter_is_complete_and_sorted(fakestore, products_catalog, category):
    expected = [product for product in products_catalog if product["category"] == category]
    assert expected, f"В эталонном каталоге отсутствует документированная категория {category!r}"
    actual = json_response(fakestore.category(category, sort="desc"))
    assert actual == sorted(expected, key=lambda p: p["id"], reverse=True)


def test_missing_product_returns_empty_body(fakestore, products_catalog):
    missing_id = max(product["id"] for product in products_catalog) + 1000
    # Развёрнутый сервис возвращает 200 с пустым телом, которое не является JSON null.
    response = fakestore.product(missing_id)
    assert response.status_code == 200
    assert response.content == b""


def test_unknown_category_is_empty(fakestore):
    assert json_response(fakestore.category(f"qa-missing-{uuid4().hex}")) == []


def test_create_echoes_payload_without_persisting(fakestore, products_catalog):
    payload = {
        "title": f"QA product {uuid4().hex}",
        "price": 19.95,
        "description": "Synthetic automation example",
        "image": "https://example.com/test-product.png",
        "category": products_catalog[0]["category"],
    }
    with allure.step("POST возвращает введённые поля и синтетический ID"):
        created = json_response(fakestore.request("POST", "/products", json=payload), status=201)
        assert type(created["id"]) is int and created["id"] > 0
        assert {key: created[key] for key in payload} == payload
    with allure.step("Классический Fake Store не сохраняет созданный товар"):
        current = json_response(fakestore.products())
        assert all(product["title"] != payload["title"] for product in current)


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_update_echoes_fields_but_keeps_original(fakestore, products_catalog, method):
    original = products_catalog[0]
    payload = {
        "title": f"Updated {uuid4().hex}",
        "price": 24.5,
        "description": "Simulated update",
        "image": "https://example.com/updated.png",
        "category": original["category"],
    }
    actual = json_response(fakestore.request(method, f"/products/{original['id']}", json=payload))
    assert actual["id"] == original["id"]
    assert {key: actual[key] for key in payload} == payload
    assert json_response(fakestore.product(original["id"])) == original


def test_partial_patch_echoes_changed_field(fakestore, products_catalog):
    original = products_catalog[0]
    title = f"Partial update {uuid4().hex}"
    actual = json_response(
        fakestore.request("PATCH", f"/products/{original['id']}", json={"title": title})
    )
    assert actual["id"] == original["id"]
    assert actual["title"] == title
    # В write-ответе не требуем rating и все поля GET-модели.
    assert json_response(fakestore.product(original["id"])) == original


def test_delete_returns_product_without_removing_it(fakestore, products_catalog):
    original = products_catalog[0]
    deleted = json_response(fakestore.request("DELETE", f"/products/{original['id']}"))
    assert deleted == original
    assert json_response(fakestore.product(original["id"])) == original
