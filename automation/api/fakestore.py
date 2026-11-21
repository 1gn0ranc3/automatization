from urllib.parse import quote

from automation.api.client import ApiClient


class FakeStoreClient(ApiClient):
    def products(self, **params):
        return self.request("GET", "/products", params=params)

    def product(self, product_id):
        return self.request("GET", f"/products/{product_id}")

    def categories(self):
        return self.request("GET", "/products/categories")

    def category(self, name, **params):
        return self.request("GET", f"/products/category/{quote(name, safe='')}", params=params)
