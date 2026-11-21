import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("workers", [0, 2], ids=["serial", "loadfile"])
def test_actual_reqres_suite_uses_ten_requests(tmp_path, workers):
    # Подменяем только HTTP-транспорт дочернего pytest; сценарии и session fixtures реальные.
    (tmp_path / "budget_transport.py").write_text("""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests


@pytest.fixture(scope="session", autouse=True)
def controlled_transport():
    calls = []
    users = [{"id": n, "email": f"user{n}@example.com", "first_name": "Test",
              "last_name": "User", "avatar": "https://example.com/avatar.png"}
             for n in range(1, 5)]

    def send(session, method, url, **kwargs):
        path = urlsplit(url).path
        assert path.startswith("/api/users"), url
        params = kwargs.get("params", {})
        calls.append([method, path, params])
        status = 200
        if method == "GET" and path == "/api/users":
            page = params["page"]
            data = users[(page - 1) * 2:page * 2]
            body = {"page": page, "total": 4, "total_pages": 2, "per_page": 2, "data": data}
        elif method == "GET":
            user_id = int(path.rsplit("/", 1)[1])
            if user_id == 99999:
                status, body = 404, {}
            else:
                body = {"data": users[user_id - 1]}
        elif method == "POST":
            status = 201
            body = {**kwargs["json"], "id": "5", "createdAt": "2026-01-01T00:00:00Z"}
        elif method in ("PUT", "PATCH"):
            body = {**kwargs["json"], "updatedAt": "2026-01-01T00:00:00Z"}
        elif method == "DELETE":
            status, body = 204, None
        else:
            raise AssertionError(method)
        response = requests.Response()
        response.status_code = status
        response.headers["Content-Type"] = "application/json"
        response._content = b"" if status == 204 else json.dumps(body).encode()
        response.url = url
        response.request = requests.Request(method, url).prepare()
        return response

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(requests.Session, "request", send)
        yield
    target = Path(os.environ["QA_BUDGET_PATH"]) / f"calls-{os.getpid()}.json"
    target.write_text(json.dumps(calls))
""")
    project = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(project)])
    env["QA_BUDGET_PATH"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/sites/api/test_reqres_users.py",
            "-p",
            "budget_transport",
            "-n",
            str(workers),
            "--dist=loadfile",
            "-q",
        ],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "12 passed" in result.stdout
    calls = [
        call for path in tmp_path.glob("calls-*.json") for call in json.loads(path.read_text())
    ]
    assert len(calls) == 10, calls
    assert sum(method == "GET" for method, _, _ in calls) == 6
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert sum(verb == method for verb, _, _ in calls) == 1
    assert calls.count(["GET", "/api/users", {"page": 1}]) == 1
    assert calls.count(["GET", "/api/users/1", {}]) == 1
