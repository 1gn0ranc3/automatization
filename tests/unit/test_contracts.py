import pytest

from automation.api.contracts import assert_product


@pytest.fixture
def product():
    return {
        "id": 1,
        "title": "Book",
        "price": 10.5,
        "description": "A book",
        "category": "books",
        "image": "https://example.com/book.jpg",
        "rating": {"rate": 4.5, "count": 3},
    }


def test_product_contract_accepts_valid_entity_and_additional_fields(product):
    assert_product({**product, "future_field": "value"})


@pytest.mark.parametrize(
    "change",
    [
        {"id": True},
        {"price": float("nan")},
        {"price": -1},
        {"title": "   "},
        {"image": "javascript:alert(1)"},
        {"rating": {"rate": True, "count": 1}},
        {"rating": {"rate": 5.1, "count": 1}},
        {"rating": {"rate": 4, "count": -1}},
    ],
)
def test_product_contract_rejects_invalid_catalog_data(product, change):
    with pytest.raises(AssertionError):
        assert_product({**product, **change})
