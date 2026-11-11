"""Sobe o daemon (agenda e retry) e a interface do Dagster."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    home = Path(os.environ.get("DAGSTER_HOME", "/app/var/dagster_home"))
    home.mkdir(parents=True, exist_ok=True)
    (home / "dagster.yaml").write_text("telemetry:\n  enabled: false\n", encoding="utf-8")
    (home / "workspace.yaml").write_text(
        "load_from:\n  - python_module:\n      module_name: orquestracao.definicoes\n",
        encoding="utf-8",
    )
    os.environ["DAGSTER_HOME"] = str(home)
    daemon = subprocess.Popen(["dagster-daemon", "run"])
    try:
        return subprocess.call(["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-w", str(home / "workspace.yaml")])
    finally:
        daemon.terminate()


if __name__ == "__main__":
    sys.exit(main())
