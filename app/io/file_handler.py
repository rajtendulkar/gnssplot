from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from PyQt6.QtWidgets import QFileDialog, QWidget

from app.core.models import NMEADataset


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


def export_summary_csv(csv_path: str, datasets: Iterable[NMEADataset]) -> None:
    rows = [d.summary() for d in datasets]
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
