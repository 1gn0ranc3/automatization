import json
import math
from urllib.parse import urlsplit

import allure
import requests

from automation.config import validate_base_url


def report_path(url: str) -> str:
    """В отчёте остаётся только путь: query, fragment и credentials не сохраняются."""
    return urlsplit(url).path


class ApiClient:
    """Транспорт публичных API: тайм-ауты, метаданные, без скрытых повторов."""

    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = validate_base_url(base_url)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout: требуется конечное положительное число")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or "\\" in path
            or "#" in path
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in path)
        ):
            raise ValueError("Нужен относительный путь, начинающийся с /")
        if {"timeout", "allow_redirects"} & kwargs.keys():
            raise ValueError("timeout задаётся в клиенте; redirect запрещён политикой транспорта")
        label = report_path(path)
        # Context step не записывает kwargs с ключами/паролями в параметры отчёта.
        with allure.step(f"{method} {label}"):
            try:
                response = self.session.request(
                    method,
                    f"{self.base_url}{path}",
                    timeout=self.timeout,
                    allow_redirects=False,
                    **kwargs,
                )
            except requests.RequestException as exc:
                allure.attach(type(exc).__name__, name="Transport error")
                raise
            allure.attach(
                json.dumps(
                    {
                        "method": method,
                        "path": label,
                        "status": response.status_code,
                        "content_type": response.headers.get("Content-Type", ""),
                        "elapsed_ms": round(response.elapsed.total_seconds() * 1000),
                        "rate_limit": {
                            header: response.headers[header]
                            for header in (
                                "Retry-After",
                                "RateLimit-Limit",
                                "RateLimit-Remaining",
                                "RateLimit-Reset",
                                "X-RateLimit-Limit",
                                "X-RateLimit-Remaining",
                                "X-RateLimit-Reset",
                            )
                            if header in response.headers
                        },
                    },
                    indent=2,
                ),
                name="HTTP response metadata",
                attachment_type=allure.attachment_type.JSON,
            )
            return response

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
