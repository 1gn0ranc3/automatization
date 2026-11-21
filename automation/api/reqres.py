from automation.api.client import ApiClient


class ReqresClient(ApiClient):
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 15):
        super().__init__(base_url, timeout)
        if api_key:
            self.session.headers["x-api-key"] = api_key
