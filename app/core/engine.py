from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Literal, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app.core.models import NMEADataset, NMEAPoint


class CoreEngine(QObject):
    datasets_changed = pyqtSignal(object)
    playback_updated = pyqtSignal(int, int, str, object)
    playback_state_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.datasets: "OrderedDict[str, NMEADataset]" = OrderedDict()
        self._timeline_mode: Literal["index", "aligned", "gga"] = "aligned"
        self._aligned_timeline: list[datetime] = []
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

    @property
    def timeline_mode(self) -> Literal["index", "aligned", "gga"]:
        return self._timeline_mode

    def playback_time_at(self, index: int) -> Optional[datetime]:
        return self._resolve_timestamp(index)

    def clear(self) -> None:
        self.pause()
        self.datasets.clear()
        self._aligned_timeline.clear()
        self._max_points = 0
        self._index = 0
        self.datasets_changed.emit(dict(self.datasets))
        self._emit_playback()

    def add_dataset(self, dataset: NMEADataset) -> None:
        self.datasets[dataset.receiver_name] = dataset
        self._recompute_timeline()
        self._index = 0
        self.datasets_changed.emit(dict(self.datasets))
        self._emit_playback()

    def remove_dataset(self, receiver_name: str) -> None:
        if receiver_name not in self.datasets:
            return
        del self.datasets[receiver_name]
        self._recompute_timeline()
        self.datasets_changed.emit(dict(self.datasets))
        self._emit_playback()

    def set_timeline_mode(self, mode: Literal["index", "aligned", "gga"]) -> None:
        if mode == self._timeline_mode:
            return
        self._timeline_mode = mode
        self._recompute_timeline()
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

    def step_forward(self) -> None:
        if self._is_playing:
            return
        if self._max_points <= 1:
            return
        if self._index >= self._max_points - 1:
            return
        self._index += 1
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
            _, point = self.resolve_dataset_point(ds, self._index)
            if not point:
                continue
            positions[name] = {
                "lat": point.latitude,
                "lon": point.longitude,
                "time": point.timestamp.isoformat(sep=" ") if point.timestamp else None,
            }

        self.playback_updated.emit(self._index, max(self._max_points - 1, 0), time_label, positions)

    def _resolve_timestamp(self, index: int) -> Optional[datetime]:
        if self._timeline_mode in {"aligned", "gga"}:
            if 0 <= index < len(self._aligned_timeline):
                return self._aligned_timeline[index]
            return None

        for ds in self.datasets.values():
            point = ds.sample_at(index)
            if point and point.timestamp:
                return point.timestamp
        return None

    def resolve_dataset_point(
        self, dataset: NMEADataset, index: int
    ) -> tuple[Optional[int], Optional[NMEAPoint]]:
        if self._timeline_mode in {"aligned", "gga"}:
            if not (0 <= index < len(self._aligned_timeline)):
                return None, None
            target_time = self._aligned_timeline[index]
            prefer_suffix = "GGA" if self._timeline_mode == "gga" else None
            sample_idx = dataset.sample_index_at_or_before_time(target_time, prefer_suffix)
            if sample_idx is not None:
                return sample_idx, dataset.points[sample_idx]

        # Keep all visual panels populated when logs have disjoint absolute dates.
        # Falling back to the index-based sample preserves per-log continuity.
        point = dataset.sample_at(index)
        if point is None:
            return None, None
        safe_idx = max(0, min(index, len(dataset.points) - 1))
        return safe_idx, point

    def _recompute_timeline(self) -> None:
        if self._timeline_mode in {"aligned", "gga"}:
            times: set[datetime] = set()
            for ds in self.datasets.values():
                for point in ds.points:
                    if point.timestamp is not None and (
                        self._timeline_mode != "gga"
                        or (point.raw_sentence is not None and point.raw_sentence.endswith("GGA"))
                    ):
                        times.add(point.timestamp)

                # If a dataset has no GGA sentences, fall back to its timestamps so the
                # timeline still advances instead of collapsing to empty.
                if self._timeline_mode == "gga" and not any(
                    p.timestamp is not None and p.raw_sentence is not None and p.raw_sentence.endswith("GGA")
                    for p in ds.points
                ):
                    for point in ds.points:
                        if point.timestamp is not None:
                            times.add(point.timestamp)

            self._aligned_timeline = sorted(times)
            self._max_points = len(self._aligned_timeline)
        else:
            self._aligned_timeline = []
            self._max_points = max((len(d.points) for d in self.datasets.values()), default=0)

        if self._index >= self._max_points:
            self._index = max(self._max_points - 1, 0)
