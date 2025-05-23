from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtNetwork import QAbstractSocket
from qasync import asyncSlot
import requests, asyncio

EXPCTL_REST = "http://localhost:8000"
EXPCTL_WS   = "ws://localhost:8000/ws"


class BackendController(QObject):
    status_msg      = Signal(str)
    experiment_done = Signal(int, dict)

    def __init__(self):
        super().__init__()
        self.ws = QWebSocket()
        self.ws.textMessageReceived.connect(self._on_ws_msg)
        self.ws.errorOccurred.connect(self._on_error)
        self._current_exp_id = None

        self._connect_ws(initial=True)

    # ---------- PUBLIC ---------- #
    @asyncSlot(str)
    async def run_experiment(self, topology: str):
        self.status_msg.emit(f"Запускаем топологию «{topology}» …")
        try:
            r = requests.post(f"{EXPCTL_REST}/experiments/start",
                              json={"topology": topology}, timeout=5)
            r.raise_for_status()
            self._current_exp_id = r.json()["experiment_id"]
            self.status_msg.emit(f"Эксперимент #{self._current_exp_id} создан, ждём…")
        except Exception as e:
            self.status_msg.emit(f"<font color='red'>Ошибка запуска: {e}</font>")

    # ---------- INTERNAL ---------- #
    def _connect_ws(self, initial=False):
        """
        Открывает WebSocket; если соединение не удаётся, пытается снова каждые 3 с.
        """
        if not initial:
            self.status_msg.emit("Пробуем снова подключиться к WebSocket …")
        self.ws.open(QUrl(EXPCTL_WS))

    def _on_ws_msg(self, text: str):
        self.status_msg.emit(text)
        if "завершён" in text and self._current_exp_id is not None:
            try:
                r = requests.get(f"{EXPCTL_REST}/experiments/{self._current_exp_id}/result",
                                 timeout=5)
                self.experiment_done.emit(self._current_exp_id, r.json())
            except Exception as e:
                self.status_msg.emit(f"<font color='red'>Ошибка результата: {e}</font>")

    def _on_error(self, err):
        if err == QAbstractSocket.SocketError.ConnectionRefusedError:
            self.status_msg.emit(
                "<font color='red'>WebSocket: Connection refused.</font>"
            )
            # повторное подключение через 3 с
            QTimer.singleShot(3000, self._connect_ws)
        else:
            self.status_msg.emit(f"<font color='red'>WebSocket error: {err}</font>")

    def close(self):
        self.ws.close()
