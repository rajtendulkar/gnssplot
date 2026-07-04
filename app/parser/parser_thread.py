from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from app.core.models import NMEADataset
from app.parser.nmea_parser import parse_nmea_file


class NMEAParserThread(QThread):
    started_parse = pyqtSignal(str)
    progress = pyqtSignal(str, int)
    parsed = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, file_path: str, receiver_name: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.receiver_name = receiver_name

    def run(self) -> None:
        self.started_parse.emit(self.receiver_name)
        try:
            dataset: NMEADataset = parse_nmea_file(
                self.file_path,
                receiver_name=self.receiver_name,
                progress_cb=lambda pct: self.progress.emit(self.receiver_name, pct),
            )
            self.parsed.emit(self.receiver_name, dataset)
        except Exception as exc:  # pragma: no cover - UI signal path
            self.failed.emit(self.receiver_name, str(exc))
