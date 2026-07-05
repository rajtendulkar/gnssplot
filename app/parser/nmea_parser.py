from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Optional

from app.core.models import NMEADataset, NMEAPoint, SatelliteInfo


def parse_int_field(raw: str) -> Optional[int]:
    if not raw:
        return None
    cleaned = raw.split("*")[0]
    try:
        return int(cleaned)
    except ValueError:
        return None


def constellation_from_talker(talker: str) -> str:
    if talker == "GP":
        return "GPS"
    if talker == "GL":
        return "GLONASS"
    if talker == "GA":
        return "Galileo"
    if talker in {"GB", "BD"}:
        return "BeiDou"
    if talker in {"QZ", "GQ"}:
        return "QZSS"
    if talker == "GI":
        return "NavIC"
    if talker == "GN":
        return "Mixed"
    return "Other"


def constellation_from_svid(svid: int) -> str:
    if 1 <= svid <= 32:
        return "GPS"
    if 65 <= svid <= 96:
        return "GLONASS"
    if 193 <= svid <= 200:
        return "QZSS"
    if 201 <= svid <= 237:
        return "BeiDou"
    if 301 <= svid <= 336:
        return "Galileo"
    if 401 <= svid <= 414:
        return "NavIC"
    return "Other"


def parse_lat_lon(raw: str, direction: str) -> Optional[float]:
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
        if direction in ("S", "W"):
            value *= -1.0
        return value
    except ValueError:
        return None


def parse_hhmmss(raw: str) -> Optional[time]:
    if not raw:
        return None
    try:
        hh = int(raw[0:2])
        mm = int(raw[2:4])
        ss_float = float(raw[4:])
        ss = int(ss_float)
        micros = int((ss_float - ss) * 1_000_000)
        return time(hour=hh, minute=mm, second=ss, microsecond=micros)
    except (ValueError, IndexError):
        return None


def parse_ddmmyy(raw: str) -> Optional[date]:
    if len(raw) != 6:
        return None
    try:
        day = int(raw[0:2])
        month = int(raw[2:4])
        year = int(raw[4:6]) + 2000
        return date(year=year, month=month, day=day)
    except ValueError:
        return None


def parse_float_field(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = raw.split("*")[0]
    try:
        return float(cleaned)
    except ValueError:
        return None


def validate_nmea_checksum(line: str) -> bool:
    if not line.startswith("$") or "*" not in line:
        return True
    data_part, checksum_part = line[1:].split("*", 1)
    if not checksum_part:
        return False
    try:
        expected = int(checksum_part[:2], 16)
    except ValueError:
        return False

    value = 0
    for ch in data_part:
        value ^= ord(ch)
    return value == expected


def parse_nmea_file(
    file_path: str,
    receiver_name: Optional[str] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> NMEADataset:
    path = Path(file_path)
    name = receiver_name or path.stem

    dataset = NMEADataset(receiver_name=name, source_path=str(path))

    with path.open("r", encoding="utf-8", errors="ignore") as fp:
        total_lines = sum(1 for _ in fp)

    last_date: Optional[date] = None
    last_speed: Optional[float] = None
    last_alt: Optional[float] = None
    last_sats: Optional[int] = None
    last_hdop: Optional[float] = None
    last_vdop: Optional[float] = None
    last_pdop: Optional[float] = None
    last_cn0: Optional[float] = None
    last_vtg_knots: Optional[float] = None
    last_vtg_kmh: Optional[float] = None
    last_satellites: dict[int, SatelliteInfo] = {}
    last_used_satellite_ids: set[int] = set()
    inferred_date: Optional[date] = None
    last_time_of_day: Optional[time] = None

    def current_satellite_snapshot() -> tuple[list[SatelliteInfo], list[int]]:
        satellites = sorted(last_satellites.values(), key=lambda s: (s.constellation, s.sat_id))
        used_ids = sorted(last_used_satellite_ids)
        return satellites, used_ids

    def build_timestamp(t: Optional[time]) -> Optional[datetime]:
        nonlocal inferred_date
        nonlocal last_date
        nonlocal last_time_of_day

        if t is None:
            return None

        # If RMC date is known, prefer it; otherwise infer date from the first
        # observed GGA/RMC time and keep continuity across midnight.
        if last_date is not None:
            if last_time_of_day is not None and t < last_time_of_day:
                last_date = last_date + timedelta(days=1)
            last_time_of_day = t
            return datetime.combine(last_date, t)

        if inferred_date is None:
            inferred_date = date.today()
        elif last_time_of_day is not None and t < last_time_of_day:
            inferred_date = inferred_date + timedelta(days=1)

        last_time_of_day = t
        return datetime.combine(inferred_date, t)

    with path.open("r", encoding="utf-8", errors="ignore") as fp:
        for idx, line in enumerate(fp):
            line = line.strip()
            if not line.startswith("$"):
                continue

            if total_lines and progress_cb and idx % 1000 == 0:
                progress_cb(int((idx / total_lines) * 100))

            parts = line.split(",")
            sentence = parts[0]
            checksum_ok = validate_nmea_checksum(line)

            # GGA: time, lat, ns, lon, ew, fix_quality, sats, hdop, alt
            if sentence.endswith("GGA") and len(parts) >= 10:
                t = parse_hhmmss(parts[1])
                lat = parse_lat_lon(parts[2], parts[3])
                lon = parse_lat_lon(parts[4], parts[5])
                fix_quality = parse_int_field(parts[6])

                try:
                    sats = int(parts[7]) if parts[7] else None
                except ValueError:
                    sats = None

                try:
                    hdop = float(parts[8]) if parts[8] else None
                except ValueError:
                    hdop = None

                try:
                    alt = float(parts[9]) if parts[9] else None
                except ValueError:
                    alt = None

                dt = build_timestamp(t)

                last_alt = alt if alt is not None else last_alt
                last_sats = sats if sats is not None else last_sats
                last_hdop = hdop if hdop is not None else last_hdop
                sat_snapshot, used_ids = current_satellite_snapshot()

                errors: list[str] = []
                if not checksum_ok:
                    errors.append("checksum_error")
                if fix_quality == 0:
                    errors.append("loss_of_lock")
                if t is None:
                    errors.append("invalid_time")
                if lat is None or lon is None:
                    errors.append("invalid_position")
                else:
                    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                        errors.append("invalid_position")
                if hdop is not None and hdop < 0:
                    errors.append("invalid_hdop")
                if last_vdop is not None and last_vdop < 0:
                    errors.append("invalid_vdop")
                if last_pdop is not None and last_pdop < 0:
                    errors.append("invalid_pdop")
                if sats is not None and sats < 0:
                    errors.append("invalid_satellite_count")
                if alt is not None and not (-10000.0 <= alt <= 100000.0):
                    errors.append("invalid_altitude")

                dataset.points.append(
                    NMEAPoint(
                        timestamp=dt,
                        latitude=lat,
                        longitude=lon,
                        altitude_m=alt,
                        num_sats=sats,
                        hdop=hdop,
                        vdop=last_vdop,
                        pdop=last_pdop,
                        cn0=last_cn0,
                        speed_knots=last_speed,
                        ground_speed_knots=last_vtg_knots,
                        ground_speed_kmh=last_vtg_kmh,
                        has_error=bool(errors),
                        error_reasons=errors,
                        satellites=sat_snapshot,
                        used_satellite_ids=used_ids,
                        raw_sentence=line,
                    )
                )

            # RMC: time, status, lat, ns, lon, ew, speed_knots, course, date
            elif sentence.endswith("RMC") and len(parts) >= 10:
                t = parse_hhmmss(parts[1])
                status = parts[2]
                lat = parse_lat_lon(parts[3], parts[4])
                lon = parse_lat_lon(parts[5], parts[6])

                try:
                    speed = float(parts[7]) if parts[7] else None
                except ValueError:
                    speed = None

                d = parse_ddmmyy(parts[9])
                if d:
                    last_date = d
                    inferred_date = None

                dt = build_timestamp(t)

                sat_snapshot, used_ids = current_satellite_snapshot()

                errors: list[str] = []
                if not checksum_ok:
                    errors.append("checksum_error")
                if status != "A":
                    errors.append("loss_of_lock")
                if t is None:
                    errors.append("invalid_time")
                if lat is None or lon is None:
                    errors.append("invalid_position")
                else:
                    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                        errors.append("invalid_position")
                if speed is not None and speed < 0:
                    errors.append("invalid_speed")

                if status == "A" and speed is not None:
                    last_speed = speed

                dataset.points.append(
                    NMEAPoint(
                        timestamp=dt,
                        latitude=lat,
                        longitude=lon,
                        altitude_m=last_alt,
                        num_sats=last_sats,
                        hdop=last_hdop,
                        vdop=last_vdop,
                        pdop=last_pdop,
                        cn0=last_cn0,
                        speed_knots=speed if status == "A" else last_speed,
                        ground_speed_knots=last_vtg_knots,
                        ground_speed_kmh=last_vtg_kmh,
                        has_error=bool(errors),
                        error_reasons=errors,
                        satellites=sat_snapshot,
                        used_satellite_ids=used_ids,
                        raw_sentence=line,
                    )
                )

            # VTG: course and speed over ground (knots, km/h)
            elif sentence.endswith("VTG") and len(parts) >= 8:
                knots = parse_float_field(parts[5])
                kmh = parse_float_field(parts[7])

                if knots is not None:
                    last_vtg_knots = knots
                if kmh is not None:
                    last_vtg_kmh = kmh

            # GSA: PDOP, HDOP, VDOP
            elif sentence.endswith("GSA") and len(parts) >= 18:
                pdop = parse_float_field(parts[15])
                hdop = parse_float_field(parts[16])
                vdop = parse_float_field(parts[17])
                used_ids: set[int] = set()
                for field_idx in range(3, 15):
                    sat_id = parse_int_field(parts[field_idx])
                    if sat_id is not None:
                        used_ids.add(sat_id)
                if used_ids:
                    last_used_satellite_ids = used_ids

                if pdop is not None:
                    last_pdop = pdop
                if hdop is not None:
                    last_hdop = hdop
                if vdop is not None:
                    last_vdop = vdop

            # GSV: CN0(SNR) appears in every 4th satellite field of each message block.
            elif sentence.endswith("GSV") and len(parts) >= 8:
                snr_values: list[float] = []
                talker = sentence[1:3] if len(sentence) >= 3 else ""
                talker_constellation = constellation_from_talker(talker)

                for field_idx in range(4, len(parts), 4):
                    sat_id = parse_int_field(parts[field_idx])
                    if sat_id is None:
                        continue
                    elev = parse_float_field(parts[field_idx + 1]) if field_idx + 1 < len(parts) else None
                    az = parse_float_field(parts[field_idx + 2]) if field_idx + 2 < len(parts) else None
                    snr = parse_float_field(parts[field_idx + 3]) if field_idx + 3 < len(parts) else None

                    constellation = (
                        constellation_from_svid(sat_id)
                        if talker_constellation == "Mixed"
                        else talker_constellation
                    )
                    last_satellites[sat_id] = SatelliteInfo(
                        sat_id=sat_id,
                        elevation_deg=elev,
                        azimuth_deg=az,
                        snr_dbhz=snr,
                        constellation=constellation,
                    )

                for field_idx in range(7, len(parts), 4):
                    snr = parse_float_field(parts[field_idx])
                    if snr is not None:
                        snr_values.append(snr)

                if snr_values:
                    last_cn0 = sum(snr_values) / len(snr_values)

    if progress_cb:
        progress_cb(100)

    return dataset
