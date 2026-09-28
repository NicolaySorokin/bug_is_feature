"""Снимок установленных версий зависимостей: make lock.

requirements.txt задаёт диапазоны, requirements.lock фиксирует то, что стоит
в образе. Dockerfile ставит зависимости из lock, поэтому сборка повторяется.
"""

import subprocess
import sys
from datetime import UTC, datetime

HEADER = """\
# Снимок версий зависимостей из собранного образа.
# Не редактируйте вручную: пересоздаётся командой `make lock`.
#
# Образ: python:3.12-slim
# Снят: {stamp}
"""


def main() -> None:
    frozen = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--exclude-editable"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    packages = sorted(
        (line.strip() for line in frozen.splitlines() if line.strip()),
        key=str.lower,
    )
    print(HEADER.format(stamp=datetime.now(UTC).strftime("%Y-%m-%d")))
    print("\n".join(packages))


if __name__ == "__main__":
    main()
