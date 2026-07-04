from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app.core.models import NMEADataset


class CoreEngine(QObject):
    datasets_changed = pyqtSignal(object)
    playback_updated = pyqtSignal(int, int, str, object)
    playback_state_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.datasets: "OrderedDict[str, NMEADataset]" = OrderedDict()
        self._max_points = 0
        self._index = 0
        self._is_playing = False

        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._tick)

    @property
    def max_points(self) -> int:
        return self._max_points

    @property
    def index(self) -> int:
        return self._index

    def clear(self) -> None:
        self.pause()
        self.datasets.clear()
        self._max_points = 0
        self._index = 0
        self.datasets_changed.emit(dict(self.datasets))
        self._emit_playback()

    def add_dataset(self, dataset: NMEADataset) -> None:
        self.datasets[dataset.receiver_name] = dataset
        self._max_points = max((len(d.points) for d in self.datasets.values()), default=0)
        if self._index >= self._max_points:
            self._index = max(self._max_points - 1, 0)
        self.datasets_changed.emit(dict(self.datasets))
        self._emit_playback()

    def remove_dataset(self, receiver_name: str) -> None:
        if receiver_name not in self.datasets:
            return
        del self.datasets[receiver_name]
        self._max_points = max((len(d.points) for d in self.datasets.values()), default=0)
        if self._index >= self._max_points:
            self._index = max(self._max_points - 1, 0)
        self.datasets_changed.emit(dict(self.datasets))
        self._emit_playback()

    def start(self) -> None:
        if self._max_points <= 1:
            return
        self._is_playing = True
        self.timer.start()
        self.playback_state_changed.emit(True)

    def pause(self) -> None:
        self._is_playing = False
        self.timer.stop()
        self.playback_state_changed.emit(False)

    def stop(self) -> None:
        self.pause()
        self.set_index(0)

    def set_interval(self, ms: int) -> None:
        self.timer.setInterval(max(20, ms))

    def set_index(self, index: int) -> None:
        if self._max_points == 0:
            self._index = 0
        else:
            self._index = max(0, min(index, self._max_points - 1))
        self._emit_playback()

    def _tick(self) -> None:
        if self._max_points <= 1:
            self.pause()
            return
        if self._index >= self._max_points - 1:
            self.pause()
            return
        self._index += 1
        self._emit_playback()

    def _emit_playback(self) -> None:
        timestamp = self._resolve_timestamp(self._index)
        time_label = timestamp.isoformat(sep=" ") if timestamp else "N/A"

        positions: dict[str, dict[str, float | str | None]] = {}
        for name, ds in self.datasets.items():
            point = ds.sample_at(self._index)
            if not point:
                continue
            positions[name] = {
                "lat": point.latitude,
                "lon": point.longitude,
                "time": point.timestamp.isoformat(sep=" ") if point.timestamp else None,
            }

        self.playback_updated.emit(self._index, max(self._max_points - 1, 0), time_label, positions)

    def _resolve_timestamp(self, index: int) -> Optional[datetime]:
        for ds in self.datasets.values():
            point = ds.sample_at(index)
            if point and point.timestamp:
                return point.timestamp
        return None
