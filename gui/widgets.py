"""
widgets.py
Все виджеты PyQt-GUI (пока только главное окно).
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QApplication, QMessageBox
)
from PySide6.QtCore import Qt
from qasync import asyncSlot
from .controller import BackendController


class MainWindow(QMainWindow):
    """Главное окно GUI-клиента."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GNS3 / MPI Experiment GUI")

        # ---------- Виджеты ---------- #
        central = QWidget()
        layout  = QVBoxLayout(central)

        layout.addWidget(QLabel("Выберите сетевую топологию:", alignment=Qt.AlignmentFlag.AlignLeft))

        self.combo_topology = QComboBox()
        self.combo_topology.addItems(["torus", "fat-tree", "thin-tree"])
        layout.addWidget(self.combo_topology)

        self.btn_start = QPushButton("Запустить эксперимент")
        layout.addWidget(self.btn_start)

        self.text_log = QTextEdit(readOnly=True)
        layout.addWidget(self.text_log, stretch=1)

        self.setCentralWidget(central)

        # ---------- Backend-контроллер ---------- #
        self.ctrl = BackendController()

        # сигнал/слот-связи
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.ctrl.status_msg.connect(self._append_log)
        self.ctrl.experiment_done.connect(self._on_done)

    # ---------- Слоты ---------- #

    @asyncSlot()
    async def _on_start_clicked(self):
        topo = self.combo_topology.currentText()
        await self.ctrl.run_experiment(topo)

    def _append_log(self, html_text: str):
        self.text_log.append(html_text)

    def _on_done(self, exp_id: int, result: dict):
        QMessageBox.information(self, "Эксперимент завершён",
                                f"Эксперимент #{exp_id} завершён.\n"
                                f"Статус: {result.get('status')}\n"
                                f"Данные см. в логе.")
        self._append_log(f"<b>RESULT {exp_id}:</b> {result}")

    # ---------- closeEvent ---------- #
    def closeEvent(self, ev):
        self.ctrl.close()
        return super().closeEvent(ev)
