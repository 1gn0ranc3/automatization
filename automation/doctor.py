"""Диагностика checkout и среды без обращения к публичным сервисам."""

import argparse
import json
import socket
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import TemporaryDirectory

from automation.config import Settings
from automation.telemetry.events import make_event
from automation.telemetry.storage import Outbox

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BROWSER_PROBE = """
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(timeout=10000)
    try:
        page = browser.new_page()
        page.set_content('<h1>ready</h1>')
        assert page.locator('h1').inner_text() == 'ready'
        print(browser.version)
    finally:
        browser.close()
"""


def dependencies(lock_path=PROJECT_ROOT / "requirements.lock.txt"):
    mismatches = []
    for line in lock_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, expected = line.split("==", 1)
        try:
            installed = version(name)
        except PackageNotFoundError:
            installed = "missing"
        if installed != expected:
            mismatches.append(f"{name}: {installed}, expected {expected}")
    if mismatches:
        raise RuntimeError("; ".join(mismatches))
    return "Installed versions match requirements.lock.txt"


def configuration():
    Settings.from_env()
    return "URLs and timeouts are valid; secrets omitted"


def storage(artifacts):
    artifacts.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".doctor-", dir=artifacts) as directory:
        outbox = Outbox(Path(directory) / "probe.sqlite")
        event = make_event("doctor", "storage-probe", 1, "internal", "controller", "passed", 0)
        outbox.append(event)
        if outbox.pending() != [event]:
            raise RuntimeError("SQLite round trip failed")
        outbox.mark_delivered(event["event_id"])
        if outbox.counts() != {"pending": 0, "delivered": 1}:
            raise RuntimeError("SQLite update failed")
    return "Artifact directory and SQLite are writable"


def loopback():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
    return "Local HTTP server can bind to loopback"


def browser():
    result = subprocess.run(
        [sys.executable, "-c", BROWSER_PROBE], capture_output=True, text=True, timeout=20
    )
    if result.returncode:
        raise RuntimeError(
            "Chromium launch/page check failed; run make integration-tests for logs. "
            "Install Chromium with: python -m playwright install chromium"
        )
    return f"Chromium {result.stdout.strip()} launched and rendered a page"


def diagnose(artifacts, integration=False):
    checks = []

    def check(name, probe):
        try:
            detail = probe()
        except Exception as exc:
            checks.append({"name": name, "status": "failed", "detail": str(exc)})
        else:
            checks.append({"name": name, "status": "passed", "detail": detail})

    def python_version():
        if sys.version_info < (3, 12):
            raise RuntimeError("Python 3.12+ is required")
        return sys.version.split()[0]

    check("python", python_version)
    check("dependencies", dependencies)
    check("configuration", configuration)
    check("storage", lambda: storage(Path(artifacts)))
    if integration:
        check("loopback", loopback)
        check("chromium", browser)
    return {"ok": all(item["status"] == "passed" for item in checks), "checks": checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/doctor"))
    parser.add_argument("--integration", action="store_true", help="Проверить loopback и Chromium")
    parser.add_argument("--json", action="store_true", help="Машиночитаемый отчёт")
    args = parser.parse_args(argv)
    result = diagnose(args.artifacts, args.integration)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for check in result["checks"]:
            print(f"{check['status'].upper():6} {check['name']}: {check['detail']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
