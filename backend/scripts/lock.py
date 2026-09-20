"""Снимок установленных версий зависимостей.

Запуск через make:  make lock

requirements.txt задаёт диапазоны версий - так удобно обновляться.
requirements.lock фиксирует то, что реально стоит в собранном образе,
включая зависимости зависимостей. Сборка по нему повторяется один в один
и через месяц: Dockerfile ставит зависимости из lock, если файл есть.

Скрипт выполняется в разовом контейнере из собранного образа, поэтому
в снимок попадают только рабочие зависимости - инструменты разработки
ставятся отдельно и сюда не приезжают.
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
