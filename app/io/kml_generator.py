from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable, Optional

from app.core.models import NMEADataset


@dataclass
class KMLEntry:
    timestamp: Optional[datetime]
    latitude: float
    longitude: float
    speed_knots: Optional[float]
    sentence: str


def _parse_hhmmss(raw: str) -> Optional[time]:
    if not raw:
        return None
    try:
        hh = int(raw[0:2])
        mm = int(raw[2:4])
        sec_float = float(raw[4:])
        ss = int(sec_float)
        micros = int((sec_float - ss) * 1_000_000)
        return time(hour=hh, minute=mm, second=ss, microsecond=micros)
    except (ValueError, IndexError):
        return None


def _parse_ddmmyy(raw: str) -> Optional[date]:
    if len(raw) != 6:
        return None
    try:
        day = int(raw[0:2])
        month = int(raw[2:4])
        year = int(raw[4:6]) + 2000
        return date(year=year, month=month, day=day)
    except ValueError:
        return None


def _parse_lat_lon(raw: str, direction: str) -> Optional[float]:
    if not raw or not direction:
        return None
    try:
        dot_idx = raw.find(".")
        if dot_idx < 2:
            return None
        deg_len = dot_idx - 2
        degrees = float(raw[:deg_len])
        minutes = float(raw[deg_len:])
        value = degrees + minutes / 60.0
        if direction in {"S", "W"}:
            value *= -1.0
        return value
    except ValueError:
        return None


def _safe_iso(ts: Optional[datetime]) -> str:
    return ts.isoformat(sep=" ") if ts is not None else "N/A"


def _write_kml(entries: Iterable[KMLEntry], kml_file: str, doc_name: str) -> int:
    point_list = list(entries)

    kml: list[str] = []
    kml.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
    kml.append("<kml xmlns=\"http://www.opengis.net/kml/2.2\">\n")
    kml.append("<Document>\n")
    kml.append(f"<name>{doc_name}</name>\n")
    kml.append(
        "<Style id=\"track\"><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>\n"
    )

    coords = [f"{entry.longitude},{entry.latitude},0" for entry in point_list]
    if coords:
        kml.append("<Placemark><name>Track</name><styleUrl>#track</styleUrl><LineString>")
        kml.append("<tessellate>1</tessellate><coordinates>")
        kml.append(" ".join(coords))
        kml.append("</coordinates></LineString></Placemark>\n")

    for idx, entry in enumerate(point_list, start=1):
        ts_text = _safe_iso(entry.timestamp)
        speed_text = f"{entry.speed_knots:.3f}" if entry.speed_knots is not None else "N/A"
        description = (
            "<![CDATA["
            f"<b>Epoch:</b> {ts_text}<br/>"
            f"<b>Speed (knots):</b> {speed_text}<br/>"
            f"<b>Sentence:</b> {entry.sentence}"
            "]]>")
        kml.append("<Placemark>")
        kml.append(f"<name>{idx:06d} {ts_text}</name>")
        kml.append(f"<description>{description}</description>")
        kml.append("<Point>")
        kml.append(f"<coordinates>{entry.longitude},{entry.latitude},0</coordinates>")
        kml.append("</Point>")
        kml.append("</Placemark>\n")

    kml.append("</Document></kml>\n")

    out_path = Path(kml_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(kml), encoding="utf-8")
    return len(point_list)


def generate_kml_from_nmea_file(nmea_file: str, kml_file: str, doc_name: str | None = None) -> int:
    entries: list[KMLEntry] = []
    last_date: Optional[date] = None

    with open(nmea_file, "r", encoding="utf-8", errors="ignore") as fp:
        for line in fp:
            line = line.strip()
            if not line.startswith("$"):
                continue

            parts = line.split(",")
            sentence = parts[0]

            # GGA: time, lat, ns, lon, ew
            if sentence.endswith("GGA") and len(parts) >= 6:
                t = _parse_hhmmss(parts[1])
                lat = _parse_lat_lon(parts[2], parts[3])
                lon = _parse_lat_lon(parts[4], parts[5])
                if lat is None or lon is None:
                    continue
                ts = datetime.combine(last_date, t) if (last_date and t) else None
                entries.append(
                    KMLEntry(
                        timestamp=ts,
                        latitude=lat,
                        longitude=lon,
                        speed_knots=None,
                        sentence=line,
                    )
                )

            # RMC: time, status, lat, ns, lon, ew, speed, course, date
            elif sentence.endswith("RMC") and len(parts) >= 10:
                t = _parse_hhmmss(parts[1])
                status = parts[2]
                lat = _parse_lat_lon(parts[3], parts[4])
                lon = _parse_lat_lon(parts[5], parts[6])
                d = _parse_ddmmyy(parts[9])
                if d is not None:
                    last_date = d
                if status != "A" or lat is None or lon is None:
                    continue
                try:
                    speed = float(parts[7]) if parts[7] else None
                except ValueError:
                    speed = None
                ts = datetime.combine(last_date, t) if (last_date and t) else None
                entries.append(
                    KMLEntry(
                        timestamp=ts,
                        latitude=lat,
                        longitude=lon,
                        speed_knots=speed,
                        sentence=line,
                    )
                )

    name = doc_name or f"{Path(nmea_file).stem} input"
    return _write_kml(entries, kml_file, name)


def generate_kml_from_dataset(
    dataset: NMEADataset,
    kml_file: str,
    doc_name: str | None = None,
    skip_errors: bool = True,
) -> int:
    entries: list[KMLEntry] = []
    for point in dataset.points:
        if skip_errors and point.has_error:
            continue
        if point.latitude is None or point.longitude is None:
            continue
        entries.append(
            KMLEntry(
                timestamp=point.timestamp,
                latitude=point.latitude,
                longitude=point.longitude,
                speed_knots=point.speed_knots,
                sentence=point.raw_sentence or "",
            )
        )

    name = doc_name or f"{dataset.receiver_name} output"
    return _write_kml(entries, kml_file, name)
