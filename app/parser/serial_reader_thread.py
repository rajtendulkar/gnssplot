from __future__ import annotations

from time import monotonic

from PyQt6.QtCore import QThread, pyqtSignal

from app.core.models import NMEAPoint
from app.parser.nmea_parser import NMEAStreamParser


class SerialReaderThread(QThread):
    connected = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    failed = pyqtSignal(str)
    points_received = pyqtSignal(str, object)

    def __init__(self, port_name: str, baud_rate: int, receiver_name: str, parent=None):
        super().__init__(parent)
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.receiver_name = receiver_name

    def run(self) -> None:
        try:
            import serial
        except Exception as exc:  # pragma: no cover - depends on runtime env
            self.failed.emit(f"pyserial not available: {exc}")
            return

        parser = NMEAStreamParser()
        batch: list[NMEAPoint] = []
        last_emit = monotonic()

        serial_port = None
        try:
            serial_port = serial.Serial(self.port_name, self.baud_rate, timeout=0.5)
            self.connected.emit(self.receiver_name)

            while not self.isInterruptionRequested():
                try:
                    raw = serial_port.readline()
                except Exception as exc:
                    self.failed.emit(f"Serial read error: {exc}")
                    break

                if not raw:
                    if batch and (monotonic() - last_emit) > 0.5:
                        self.points_received.emit(self.receiver_name, batch)
                        batch = []
                        last_emit = monotonic()
                    continue

                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                point = parser.parse_line(line)
                if point is None:
                    continue

                batch.append(point)
                if len(batch) >= 25 or (monotonic() - last_emit) > 0.5:
                    self.points_received.emit(self.receiver_name, batch)
                    batch = []
                    last_emit = monotonic()

            if batch:
                self.points_received.emit(self.receiver_name, batch)

        except Exception as exc:  # pragma: no cover - hardware path
            self.failed.emit(f"Serial open error: {exc}")
        finally:
            if serial_port is not None:
                try:
                    serial_port.close()
                except Exception:
                    pass
            self.disconnected.emit(self.receiver_name)
