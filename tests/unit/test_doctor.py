import json
from importlib.metadata import PackageNotFoundError

from automation import doctor


def test_diagnostics_continue_after_failure_and_do_not_probe_browser_by_default(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(doctor, "dependencies", lambda: "ok")
    monkeypatch.setenv("API_TIMEOUT_SECONDS", "nan")
    monkeypatch.setenv("REQRES_API_KEY", "secret-value")
    monkeypatch.setattr(doctor, "browser", lambda: (_ for _ in ()).throw(AssertionError("called")))
    result = doctor.diagnose(tmp_path)
    checks = {item["name"]: item for item in result["checks"]}
    assert result["ok"] is False
    assert checks["configuration"]["status"] == "failed"
    assert checks["storage"]["status"] == "passed"
    assert "chromium" not in checks
    assert "secret-value" not in json.dumps(result)
    assert list(tmp_path.iterdir()) == []


def test_missing_and_different_dependency_versions_are_reported(tmp_path, monkeypatch):
    lock = tmp_path / "requirements.lock.txt"
    lock.write_text("# locked\n\none==1\ntwo==2\n")

    def version(name):
        if name == "one":
            raise PackageNotFoundError(name)
        return "3"

    monkeypatch.setattr(doctor, "version", version)
    import pytest

    with pytest.raises(RuntimeError, match="one: missing, expected 1; two: 3, expected 2"):
        doctor.dependencies(lock)


def test_doctor_json_and_exit_code(tmp_path, monkeypatch, capsys):
    expected = {"ok": False, "checks": [{"name": "test", "status": "failed", "detail": "failed"}]}
    monkeypatch.setattr(doctor, "diagnose", lambda *args: expected)
    assert doctor.main(["--json", "--artifacts", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out) == expected


def test_integration_diagnostics_report_both_failures(tmp_path, monkeypatch):
    def unavailable():
        raise PermissionError("restricted environment")

    monkeypatch.setattr(doctor, "dependencies", lambda: "ok")
    monkeypatch.setattr(doctor, "loopback", unavailable)
    monkeypatch.setattr(doctor, "browser", unavailable)
    result = doctor.diagnose(tmp_path, integration=True)
    assert [item["status"] for item in result["checks"][-2:]] == ["failed", "failed"]
