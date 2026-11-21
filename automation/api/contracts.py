import math
from urllib.parse import urlsplit

from automation.api.client import report_path


def json_response(response, status=200):
    assert response.status_code == status, (
        f"{response.request.method} {report_path(response.url)}: ожидался HTTP {status}, "
        f"получен {response.status_code}; Content-Type={response.headers.get('Content-Type')}. "
        "401/403 могут означать ключ/WAF, 429 — квоту; это не пропуск теста."
    )
    content_type = response.headers.get("Content-Type", "").partition(";")[0].strip().lower()
    assert content_type == "application/json", f"Ожидался JSON, получен {content_type!r}"
    return response.json()


def assert_product(product):
    """Контракт чтения товара, отдельно от имитируемых write-ответов."""
    assert isinstance(product, dict), "Product must be an object"
    assert {"id", "title", "price", "description", "category", "image", "rating"} <= product.keys()
    assert type(product["id"]) is int and product["id"] > 0
    for field in ("title", "description", "category"):
        assert isinstance(product[field], str) and product[field].strip(), field
    assert type(product["price"]) in (int, float)
    assert math.isfinite(product["price"]) and product["price"] >= 0
    assert isinstance(product["image"], str)
    image_url = urlsplit(product["image"])
    assert image_url.scheme in {"http", "https"} and image_url.netloc
    rating = product["rating"]
    assert isinstance(rating, dict)
    assert {"rate", "count"} <= rating.keys()
    assert type(rating["rate"]) in (int, float) and 0 <= rating["rate"] <= 5
    assert type(rating["count"]) is int and rating["count"] >= 0
