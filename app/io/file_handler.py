from __future__ import annotations

import csv
import json
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PyQt6.QtWidgets import QFileDialog, QWidget

from app.core.models import NMEADataset


FULL_PARAMETER_FIELDS = [
    "timestamp",
    "latitude",
    "longitude",
    "altitude_m",
    "num_sats",
    "hdop",
    "vdop",
    "pdop",
    "cn0",
    "speed_knots",
    "ground_speed_knots",
    "ground_speed_kmh",
    "raw_sentence",
    "satellites",
    "used_satellite_ids",
]


def choose_nmea_files(parent: QWidget) -> list[str]:
    paths, _ = QFileDialog.getOpenFileNames(
        parent,
        "Select NMEA log files",
        "",
        "NMEA Logs (*.nmea *.log *.txt);;All Files (*)",
    )
    return paths


def receiver_name_from_path(file_path: str) -> str:
    return Path(file_path).stem


def choose_export_path(parent: QWidget) -> str:
    path, _ = QFileDialog.getSaveFileName(
        parent,
        "Export Comparison Summary",
        "nmea_summary.csv",
        "CSV Files (*.csv)",
    )
    return path


def choose_report_bundle_path(parent: QWidget) -> str:
    path, _ = QFileDialog.getSaveFileName(
        parent,
        "Export Report Bundle",
        "gnss_report_bundle.zip",
        "ZIP Files (*.zip)",
    )
    return path


def summary_rows(datasets: Iterable[NMEADataset]) -> list[dict[str, float | int | str]]:
    return [d.summary() for d in datasets]


def full_parameter_rows(dataset: NMEADataset) -> list[dict[str, str | float | int | None]]:
    rows: list[dict[str, str | float | int | None]] = []
    for point in dataset.points:
        rows.append(
            {
                "timestamp": point.timestamp.isoformat(sep=" ") if point.timestamp else "",
                "latitude": point.latitude,
                "longitude": point.longitude,
                "altitude_m": point.altitude_m,
                "num_sats": point.num_sats,
                "hdop": point.hdop,
                "vdop": point.vdop,
                "pdop": point.pdop,
                "cn0": point.cn0,
                "speed_knots": point.speed_knots,
                "ground_speed_knots": point.ground_speed_knots,
                "ground_speed_kmh": point.ground_speed_kmh,
                "raw_sentence": point.raw_sentence or "",
                "satellites": json.dumps(
                    [
                        {
                            "sat_id": sat.sat_id,
                            "elevation_deg": sat.elevation_deg,
                            "azimuth_deg": sat.azimuth_deg,
                            "snr_dbhz": sat.snr_dbhz,
                            "constellation": sat.constellation,
                        }
                        for sat in point.satellites
                    ]
                ),
                "used_satellite_ids": json.dumps(point.used_satellite_ids),
            }
        )
    return rows


def export_summary_csv(csv_path: str, datasets: Iterable[NMEADataset]) -> None:
    rows = summary_rows(datasets)
    if not rows:
        return

    fieldnames = [
        "receiver",
        "source_path",
        "total_points",
        "points_with_position",
        "avg_sats",
        "avg_hdop",
        "avg_vdop",
        "avg_cn0",
        "avg_speed_knots",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_report_bundle(
    bundle_path: str,
    datasets: Iterable[NMEADataset],
    accuracy_rows: list[dict[str, float | int | str]],
    reference_receiver: str | None,
    timeline_mode: str,
    plot_image_paths: list[tuple[str, str]] | None = None,
) -> None:
    summary = summary_rows(datasets)

    with tempfile.TemporaryDirectory(prefix="gnss_report_") as tmpdir:
        temp_dir = Path(tmpdir)
        summary_path = temp_dir / "summary.csv"
        accuracy_path = temp_dir / "accuracy.csv"
        report_path = temp_dir / "report.json"
        plot_csv_paths: list[tuple[str, Path]] = []

        for dataset in datasets:
            csv_path = temp_dir / f"{dataset.receiver_name}_full_parameters.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as fp:
                writer = csv.DictWriter(fp, fieldnames=FULL_PARAMETER_FIELDS)
                writer.writeheader()
                writer.writerows(full_parameter_rows(dataset))
            plot_csv_paths.append((dataset.receiver_name, csv_path))

        summary_fields = [
            "receiver",
            "source_path",
            "total_points",
            "points_with_position",
            "avg_sats",
            "avg_hdop",
            "avg_vdop",
            "avg_cn0",
            "avg_speed_knots",
        ]
        with open(summary_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=summary_fields)
            writer.writeheader()
            writer.writerows(summary)

        accuracy_fields = ["reference", "receiver", "samples", "mean_m", "median_m", "p95_m", "max_m"]
        with open(accuracy_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=accuracy_fields)
            writer.writeheader()
            writer.writerows(accuracy_rows)

        metadata = {
            "generated_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "reference_receiver": reference_receiver,
            "timeline_mode": timeline_mode,
            "dataset_count": len(summary),
            "accuracy_rows": len(accuracy_rows),
            "files": {
                "summary": "summary.csv",
                "accuracy": "accuracy.csv",
                "parameters": [f"parameters/{name}_full_parameters.csv" for name, _ in plot_csv_paths],
                "plots": [f"plots/{name}" for name, _ in (plot_image_paths or [])],
            },
        }
        with open(report_path, "w", encoding="utf-8") as fp:
            json.dump(metadata, fp, indent=2)

        with zipfile.ZipFile(bundle_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(summary_path, arcname="summary.csv")
            zf.write(accuracy_path, arcname="accuracy.csv")
            zf.write(report_path, arcname="report.json")
            for receiver_name, csv_path in plot_csv_paths:
                zf.write(csv_path, arcname=f"parameters/{receiver_name}_full_parameters.csv")
            if plot_image_paths:
                for rel_name, image_path in plot_image_paths:
                    zf.write(image_path, arcname=f"plots/{rel_name}")
