"""
app.py
Запускает Qt-приложение с асинхронным event-loop (qasync).
"""

import sys, asyncio
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop
from .widgets import MainWindow


def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    win = MainWindow()
    win.resize(600, 500)
    win.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
