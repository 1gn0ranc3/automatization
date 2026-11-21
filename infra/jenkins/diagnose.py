"""Collect bounded Jenkins startup diagnostics without changing containers."""

import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "artifacts" / "jenkins-startup.log"


def redact(text):
    # Jenkins prints the initial administrator password as a 32-character hex string.
    return re.sub(r"\b[0-9a-fA-F]{32}\b", "[REDACTED]", text)


def run(args):
    try:
        result = subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, timeout=20, check=False
        )
        return f"exit={result.returncode}\n{result.stdout}{result.stderr}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Diagnostic command failed: {exc}\n"


def main():
    compose = ["docker", "compose", "-f", "compose.jenkins.yml"]
    sections = [
        ("Containers", run([*compose, "ps", "-a", "jenkins", "docker"])),
        (
            "Jenkins startup logs",
            run([*compose, "logs", "--no-color", "--tail=200", "jenkins"]),
        ),
    ]
    for path in ("/", "/login"):
        sections.append(
            (
                f"HTTP inside Jenkins container: {path}",
                run(
                    [
                        *compose,
                        "exec",
                        "-T",
                        "jenkins",
                        "curl",
                        "--noproxy",
                        "*",
                        "--silent",
                        "--show-error",
                        "--connect-timeout",
                        "2",
                        "--max-time",
                        "5",
                        "--output",
                        "/dev/null",
                        "--write-out",
                        "HTTP %{http_code}; connect=%{time_connect}s; total=%{time_total}s\\n",
                        f"http://127.0.0.1:8080{path}",
                    ]
                ),
            )
        )
    opener = build_opener(ProxyHandler({}))
    for url in (
        "http://127.0.0.1:8080/",
        "http://127.0.0.1:8080/login",
        "http://localhost:8080/login",
    ):
        try:
            with opener.open(url, timeout=5) as response:
                status = f"HTTP {response.status}"
        except HTTPError as exc:
            status = f"HTTP {exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            status = str(exc)
        sections.append((url, status))
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(
        redact("\n\n".join(f"=== {name} ===\n{body}" for name, body in sections)),
        encoding="utf-8",
    )
    print(f"Диагностика сохранена: {REPORT}")
    print("Контейнеры и настройки не изменены; первоначальный пароль скрыт.")


if __name__ == "__main__":
    main()
