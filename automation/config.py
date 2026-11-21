import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def base_url(name: str, default: str) -> str:
    return validate_base_url(os.getenv(name, default), name)


def validate_base_url(value: str, name: str = "base_url") -> str:
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        parsed.port  # urlsplit откладывает проверку порта до обращения к свойству.
    except ValueError as exc:
        raise ValueError(f"{name}: некорректный HTTP(S) URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or any(char.isspace() for char in value)
    ):
        raise ValueError(f"{name}: нужен HTTP(S) URL без учётных данных, query и fragment")
    return value


def positive_number(name: str, default: str) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError as exc:
        raise ValueError(f"{name}: требуется положительное число") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name}: требуется конечное положительное число")
    return value


@dataclass(frozen=True)
class Settings:
    demoqa_url: str
    reqres_url: str
    fakestore_url: str
    reqres_api_key: str = field(repr=False)
    api_timeout: float
    ui_timeout: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            demoqa_url=base_url("DEMOQA_BASE_URL", "https://demoqa.com"),
            reqres_url=base_url("REQRES_BASE_URL", "https://reqres.in"),
            fakestore_url=base_url("FAKESTORE_BASE_URL", "https://fakestoreapi.com"),
            reqres_api_key=os.getenv("REQRES_API_KEY", "").strip(),
            api_timeout=positive_number("API_TIMEOUT_SECONDS", "15"),
            ui_timeout=positive_number("UI_TIMEOUT_MS", "10000"),
        )
