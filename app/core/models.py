from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


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
    raw_sentence: Optional[str]


@dataclass
class NMEADataset:
    receiver_name: str
    source_path: str
    points: List[NMEAPoint] = field(default_factory=list)

    def metric_series(self, metric: str) -> tuple[list[float], list[float]]:
        x_vals: list[float] = []
        y_vals: list[float] = []
        for point in self.points:
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
