from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class SatelliteInfo:
    sat_id: int
    elevation_deg: Optional[float]
    azimuth_deg: Optional[float]
    snr_dbhz: Optional[float]
    constellation: str


@dataclass
class NMEAPoint:
    timestamp: Optional[datetime]
    latitude: Optional[float]
    longitude: Optional[float]
    altitude_m: Optional[float]
    num_sats: Optional[int]
    hdop: Optional[float]
    vdop: Optional[float]
    pdop: Optional[float]
    cn0: Optional[float]
    speed_knots: Optional[float]
    ground_speed_knots: Optional[float]
    ground_speed_kmh: Optional[float]
    has_error: bool = False
    error_reasons: List[str] = field(default_factory=list)
    satellites: List[SatelliteInfo] = field(default_factory=list)
    used_satellite_ids: List[int] = field(default_factory=list)
    raw_sentence: Optional[str] = None


@dataclass
class NMEADataset:
    receiver_name: str
    source_path: str
    points: List[NMEAPoint] = field(default_factory=list)

    def metric_series(self, metric: str) -> tuple[list[float], list[float]]:
        x_vals: list[float] = []
        y_vals: list[float] = []
        for point in self.points:
            if point.has_error:
                continue
            if point.timestamp is None:
                continue
            value = getattr(point, metric)
            if value is None:
                continue
            x_vals.append(point.timestamp.timestamp())
            y_vals.append(float(value))
        return x_vals, y_vals

    def sample_at(self, index: int) -> Optional[NMEAPoint]:
        if not self.points:
            return None
        safe_idx = max(0, min(index, len(self.points) - 1))
        return self.points[safe_idx]

    def sample_index_at_or_before_time(
        self, target_time: datetime, prefer_sentence_suffix: str | None = None
    ) -> Optional[int]:
        timed_indices: list[int] = []
        timed_values: list[datetime] = []

        for idx, point in enumerate(self.points):
            if point.timestamp is None:
                continue
            timed_indices.append(idx)
            timed_values.append(point.timestamp)

        if not timed_values:
            return None

        pos = bisect_right(timed_values, target_time) - 1
        if pos < 0:
            return None

        if prefer_sentence_suffix is not None and timed_values[pos] == target_time:
            idx = pos
            while idx >= 0 and timed_values[idx] == target_time:
                point = self.points[timed_indices[idx]]
                if point.raw_sentence and point.raw_sentence.endswith(prefer_sentence_suffix):
                    return timed_indices[idx]
                idx -= 1

        return timed_indices[pos]

    def sample_at_or_before_time(
        self, target_time: datetime, prefer_sentence_suffix: str | None = None
    ) -> Optional[NMEAPoint]:
        idx = self.sample_index_at_or_before_time(target_time, prefer_sentence_suffix)
        if idx is None:
            return None
        return self.points[idx]

    def summary(self) -> dict[str, float | int | str]:
        total_points = len(self.points)
        with_fix = 0
        sats_values: list[int] = []
        hdop_values: list[float] = []
        vdop_values: list[float] = []
        cn0_values: list[float] = []
        speed_values: list[float] = []

        for p in self.points:
            if p.latitude is not None and p.longitude is not None:
                with_fix += 1
            if p.num_sats is not None:
                sats_values.append(p.num_sats)
            if p.hdop is not None:
                hdop_values.append(p.hdop)
            if p.vdop is not None:
                vdop_values.append(p.vdop)
            if p.cn0 is not None:
                cn0_values.append(p.cn0)
            if p.speed_knots is not None:
                speed_values.append(p.speed_knots)

        return {
            "receiver": self.receiver_name,
            "source_path": self.source_path,
            "total_points": total_points,
            "points_with_position": with_fix,
            "avg_sats": round(sum(sats_values) / len(sats_values), 2) if sats_values else 0,
            "avg_hdop": round(sum(hdop_values) / len(hdop_values), 3) if hdop_values else 0,
            "avg_vdop": round(sum(vdop_values) / len(vdop_values), 3) if vdop_values else 0,
            "avg_cn0": round(sum(cn0_values) / len(cn0_values), 3) if cn0_values else 0,
            "avg_speed_knots": round(sum(speed_values) / len(speed_values), 3) if speed_values else 0,
        }
