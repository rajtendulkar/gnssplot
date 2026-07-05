from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Literal

import pyqtgraph as pg
from PyQt6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget
from pyqtgraph.exporters import ImageExporter

from app.core.models import NMEADataset


class ComparisonPlotWidget(QWidget):
    AVAILABLE_METRICS = {
        "cn0": "CN0 (dB-Hz)",
        "latitude": "Latitude",
        "longitude": "Longitude",
        "hdop": "HDOP",
        "vdop": "VDOP",
        "pdop": "PDOP",
        "num_sats": "Satellites Used",
        "ground_speed_knots": "VTG Ground Speed (knots)",
        "ground_speed_kmh": "VTG Ground Speed (km/h)",
        "altitude_m": "Altitude (m)",
        "speed_knots": "Speed (knots)",
    }

    COLORS = [
        "#1f77b4",
        "#d62728",
        "#2ca02c",
        "#ff7f0e",
        "#8c564b",
        "#17becf",
        "#bcbd22",
        "#9467bd",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("plotHost")

        self._theme = "dark"
        self._title_color = "#dbeafe"
        self._cursor_color = "#93c5fd"
        self._plot_bg = "#0b1323"
        self._axis_pen = "#425266"
        self._axis_text_pen = "#a3b6cc"
        self._grid_alpha = 0.2

        self._plots: list[pg.PlotWidget] = []
        self._plot_items: list[pg.PlotItem] = []
        self._metric_boxes: list[QComboBox] = []
        self._panel_widgets: list[QWidget] = []
        self._maximize_buttons: list[QToolButton] = []
        self._maximized_index: int | None = None
        self._cursor_lines: list[pg.InfiniteLine] = []
        self._datasets: Dict[str, NMEADataset] = {}
        self._timeline_mode: Literal["index", "aligned", "gga"] = "aligned"
        self._aligned_anchor_ts = datetime(2000, 1, 1).timestamp()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)

        defaults = ["latitude", "longitude", "hdop", "vdop"]
        for idx in range(4):
            container = QWidget(self)
            container.setObjectName("plotPanel")
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(8, 8, 8, 8)

            head = QHBoxLayout()
            panel_label = QLabel(f"Plot {idx + 1}:")
            panel_label.setObjectName("plotPanelLabel")
            head.addWidget(panel_label)

            metric_box = QComboBox(container)
            for key, label in self.AVAILABLE_METRICS.items():
                metric_box.addItem(label, key)
            metric_box.setCurrentIndex(max(metric_box.findData(defaults[idx]), 0))
            metric_box.currentIndexChanged.connect(self._refresh_all_plots)
            self._metric_boxes.append(metric_box)

            head.addWidget(metric_box)

            maximize_btn = QToolButton(container)
            maximize_btn.setText("□")
            maximize_btn.setToolTip("Maximize")
            maximize_btn.setFixedSize(24, 22)
            maximize_btn.clicked.connect(lambda _checked=False, i=idx: self._toggle_maximize_plot(i))
            self._maximize_buttons.append(maximize_btn)
            head.addStretch(1)
            head.addWidget(maximize_btn)
            container_layout.addLayout(head)

            plot = pg.PlotWidget(container, axisItems={"bottom": pg.DateAxisItem()})
            plot.setBackground(self._plot_bg)
            plot.showGrid(x=True, y=True, alpha=self._grid_alpha)
            plot.setLabel("bottom", "Time")
            plot.getAxis("left").setPen(pg.mkPen(self._axis_pen, width=1))
            plot.getAxis("left").setTextPen(pg.mkPen(self._axis_text_pen))
            plot.getAxis("bottom").setPen(pg.mkPen(self._axis_pen, width=1))
            plot.getAxis("bottom").setTextPen(pg.mkPen(self._axis_text_pen))
            container_layout.addWidget(plot)

            self._plots.append(plot)
            self._plot_items.append(plot.getPlotItem())
            self._panel_widgets.append(container)

        self._apply_panel_layout()

        root_layout.addLayout(self._grid)
        self.set_theme("dark")

        self._refresh_all_plots()

    def _apply_panel_layout(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget() is not None:
                self._grid.removeWidget(item.widget())

        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._grid.setRowStretch(0, 1)
        self._grid.setRowStretch(1, 1)

        if self._maximized_index is None:
            for idx, panel in enumerate(self._panel_widgets):
                panel.show()
                self._grid.addWidget(panel, idx // 2, idx % 2)
                self._maximize_buttons[idx].setText("□")
                self._maximize_buttons[idx].setToolTip("Maximize")
        else:
            for idx, panel in enumerate(self._panel_widgets):
                if idx == self._maximized_index:
                    panel.show()
                    self._grid.addWidget(panel, 0, 0, 2, 2)
                    self._maximize_buttons[idx].setText("❐")
                    self._maximize_buttons[idx].setToolTip("Restore")
                else:
                    panel.hide()
                    self._maximize_buttons[idx].setText("□")
                    self._maximize_buttons[idx].setToolTip("Maximize")

    def _toggle_maximize_plot(self, plot_index: int) -> None:
        if self._maximized_index == plot_index:
            self._maximized_index = None
        else:
            self._maximized_index = plot_index
        self._apply_panel_layout()

    def _selected_metric(self, slot_index: int) -> str:
        return str(self._metric_boxes[slot_index].currentData())

    def _refresh_all_plots(self) -> None:
        self._cursor_lines.clear()

        for slot_index, plot_item in enumerate(self._plot_items):
            metric = self._selected_metric(slot_index)
            metric_label = self.AVAILABLE_METRICS.get(metric, metric)

            plot_item.clear()
            plot_item.setTitle(metric_label, color=self._title_color, size="12pt")
            plot_item.setLabel("bottom", "Time")
            if plot_item.legend is not None:
                plot_item.legend.scene().removeItem(plot_item.legend)
                plot_item.legend = None
            plot_item.addLegend(offset=(10, 10))

            cursor = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(self._cursor_color, width=1.2))
            plot_item.addItem(cursor)
            self._cursor_lines.append(cursor)

            for dataset_index, (receiver, dataset) in enumerate(self._datasets.items()):
                x_vals, y_vals = self._metric_series_for_plot(dataset, metric)
                if not x_vals:
                    continue
                pen = pg.mkPen(color=self.COLORS[dataset_index % len(self.COLORS)], width=2)
                plot_item.plot(x=x_vals, y=y_vals, pen=pen, name=receiver)

            self._apply_data_bounds(plot_item, metric)

    def update_datasets(self, datasets: Dict[str, NMEADataset]) -> None:
        self._datasets = datasets
        self._refresh_all_plots()
        self.reset_all_views()

    def set_timeline_mode(self, mode: Literal["index", "aligned", "gga"]) -> None:
        if mode not in ("index", "aligned", "gga"):
            return
        self._timeline_mode = mode
        self._refresh_all_plots()
        self.reset_all_views()

    def reset_all_views(self) -> None:
        for slot_index, plot_item in enumerate(self._plot_items):
            metric = self._selected_metric(slot_index)
            self._apply_data_bounds(plot_item, metric)

    def export_panel_images(self, output_dir: str) -> list[tuple[str, str]]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        exported_files: list[tuple[str, str]] = []
        for slot_index, plot_item in enumerate(self._plot_items, start=1):
            metric = self._selected_metric(slot_index - 1)
            metric_label = self.AVAILABLE_METRICS.get(metric, metric)
            file_name = f"plot_{slot_index}_{metric}.png"
            file_path = output_path / file_name

            exporter = ImageExporter(plot_item)
            try:
                exporter.parameters()["width"] = max(800, int(self.width() / 2))
            except Exception:
                pass
            exporter.export(str(file_path))
            exported_files.append((file_name, str(file_path)))

        return exported_files

    def export_metric_gallery(
        self,
        datasets: Dict[str, NMEADataset],
        output_dir: str,
        group_name: str,
    ) -> list[tuple[str, str]]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        exported_files: list[tuple[str, str]] = []
        for metric, metric_label in self.AVAILABLE_METRICS.items():
            plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
            self._configure_export_plot(plot)

            plot.setTitle(f"{group_name}: {metric_label}", color=self._title_color, size="12pt")
            plot.setLabel("bottom", "Time")
            plot.setLabel("left", metric_label)
            plot.addLegend(offset=(10, 10))

            for dataset_index, (receiver, dataset) in enumerate(datasets.items()):
                x_vals, y_vals = self._metric_series_for_plot(dataset, metric)
                if not x_vals:
                    continue
                pen = pg.mkPen(color=self.COLORS[dataset_index % len(self.COLORS)], width=2)
                plot.plot(x=x_vals, y=y_vals, pen=pen, name=receiver)

            self._apply_export_bounds(plot.getPlotItem(), metric, datasets)

            file_name = f"{group_name}_{metric}.png"
            file_path = output_path / file_name
            exporter = ImageExporter(plot.getPlotItem())
            try:
                exporter.parameters()["width"] = max(1200, int(self.width()))
            except Exception:
                pass
            exporter.export(str(file_path))
            exported_files.append((f"{group_name}/{file_name}", str(file_path)))

        return exported_files

    def _configure_export_plot(self, plot: pg.PlotWidget) -> None:
        plot.setBackground(self._plot_bg)
        plot.showGrid(x=True, y=True, alpha=self._grid_alpha)
        plot.getAxis("left").setPen(pg.mkPen(self._axis_pen, width=1))
        plot.getAxis("left").setTextPen(pg.mkPen(self._axis_text_pen))
        plot.getAxis("bottom").setPen(pg.mkPen(self._axis_pen, width=1))
        plot.getAxis("bottom").setTextPen(pg.mkPen(self._axis_text_pen))

    def _apply_export_bounds(
        self,
        plot_item: pg.PlotItem,
        metric: str,
        datasets: Dict[str, NMEADataset],
    ) -> None:
        x_values: list[float] = []
        y_values: list[float] = []

        for dataset in datasets.values():
            xs, ys = self._metric_series_for_plot(dataset, metric)
            x_values.extend(xs)
            y_values.extend(ys)

        if x_values:
            x_min = min(x_values)
            x_max = max(x_values)
            if x_min == x_max:
                delta = max(1.0, abs(x_min) * 0.001)
                x_min -= delta
                x_max += delta
            plot_item.setXRange(x_min, x_max, padding=0.02)
        if y_values:
            y_min = min(y_values)
            y_max = max(y_values)
            if y_min == y_max:
                delta = max(0.1, abs(y_min) * 0.001)
                y_min -= delta
                y_max += delta
            plot_item.setYRange(y_min, y_max, padding=0.08)

    def _apply_data_bounds(self, plot_item: pg.PlotItem, metric: str) -> None:
        x_values: list[float] = []
        y_values: list[float] = []

        for dataset in self._datasets.values():
            xs, ys = self._metric_series_for_plot(dataset, metric)
            x_values.extend(xs)
            y_values.extend(ys)

        if x_values:
            x_min = min(x_values)
            x_max = max(x_values)
            if x_min == x_max:
                delta = max(1.0, abs(x_min) * 0.001)
                x_min -= delta
                x_max += delta
            plot_item.setXRange(x_min, x_max, padding=0.02)
        else:
            plot_item.enableAutoRange(axis=pg.ViewBox.XAxis, enable=True)

        if y_values:
            y_min = min(y_values)
            y_max = max(y_values)
            if y_min == y_max:
                delta = max(0.1, abs(y_min) * 0.001)
                y_min -= delta
                y_max += delta
            plot_item.setYRange(y_min, y_max, padding=0.08)
        else:
            plot_item.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)

    def set_playback_index(self, index: int) -> None:
        cursor_x = self._resolve_cursor_time(index)
        if cursor_x is None:
            return
        for cursor in self._cursor_lines:
            cursor.setValue(cursor_x)

    def set_playback_time(self, timestamp: datetime | None) -> None:
        if timestamp is None:
            return
        cursor_x = self._timestamp_for_timeline_mode(timestamp)
        for cursor in self._cursor_lines:
            cursor.setValue(cursor_x)

    def _resolve_cursor_time(self, index: int) -> float | None:
        for dataset in self._datasets.values():
            point = dataset.sample_at(index)
            if point and point.timestamp is not None:
                return point.timestamp.timestamp()
        return None

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        if theme == "light":
            self._title_color = "#1e3a5f"
            self._cursor_color = "#2563eb"
            self._plot_bg = "#ffffff"
            self._axis_pen = "#97a6b7"
            self._axis_text_pen = "#475569"
            self._grid_alpha = 0.15
            self.setStyleSheet(
                """
                QWidget#plotPanel {
                    background: #f8fafc;
                    border: 1px solid #d3deea;
                    border-radius: 10px;
                }
                QLabel#plotPanelLabel {
                    color: #0f4c81;
                    font-weight: 600;
                }
                QWidget#plotPanel QComboBox {
                    background: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 3px 8px;
                    color: #1e293b;
                }
                QWidget#plotPanel QToolButton {
                    background: #eff6ff;
                    border: 1px solid #bfd2e8;
                    border-radius: 6px;
                    padding: 1px;
                    color: #1e3a5f;
                    font-weight: 700;
                }
                QWidget#plotPanel QToolButton:hover {
                    background: #dbeafe;
                }
                """
            )
        else:
            self._title_color = "#dbeafe"
            self._cursor_color = "#93c5fd"
            self._plot_bg = "#0b1323"
            self._axis_pen = "#425266"
            self._axis_text_pen = "#a3b6cc"
            self._grid_alpha = 0.2
            self.setStyleSheet(
                """
                QWidget#plotPanel {
                    background: #111827;
                    border: 1px solid #223246;
                    border-radius: 10px;
                }
                QLabel#plotPanelLabel {
                    color: #bfdbfe;
                    font-weight: 600;
                }
                QWidget#plotPanel QComboBox {
                    background: #0b1220;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 3px 8px;
                    color: #e2e8f0;
                }
                QWidget#plotPanel QToolButton {
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 1px;
                    color: #dbeafe;
                    font-weight: 700;
                }
                QWidget#plotPanel QToolButton:hover {
                    background: #334155;
                }
                """
            )

        for plot in self._plots:
            plot.setBackground(self._plot_bg)
            plot.showGrid(x=True, y=True, alpha=self._grid_alpha)
            plot.getAxis("left").setPen(pg.mkPen(self._axis_pen, width=1))
            plot.getAxis("left").setTextPen(pg.mkPen(self._axis_text_pen))
            plot.getAxis("bottom").setPen(pg.mkPen(self._axis_pen, width=1))
            plot.getAxis("bottom").setTextPen(pg.mkPen(self._axis_text_pen))

        self._refresh_all_plots()

    def _timestamp_for_timeline_mode(self, timestamp: datetime) -> float:
        if self._timeline_mode in {"aligned", "gga"}:
            seconds_of_day = (
                timestamp.hour * 3600
                + timestamp.minute * 60
                + timestamp.second
                + timestamp.microsecond / 1_000_000
            )
            return self._aligned_anchor_ts + seconds_of_day
        return timestamp.timestamp()

    def _metric_series_for_plot(self, dataset: NMEADataset, metric: str) -> tuple[list[float], list[float]]:
        if self._timeline_mode == "index":
            return dataset.metric_series(metric)
        return self._metric_series_time_aligned(dataset, metric)

    def _metric_series_time_aligned(self, dataset: NMEADataset, metric: str) -> tuple[list[float], list[float]]:
        x_vals: list[float] = []
        y_vals: list[float] = []
        day_offset_seconds = 0.0
        last_seconds_of_day: float | None = None

        for point in dataset.points:
            if point.has_error or point.timestamp is None:
                continue

            if self._timeline_mode == "gga":
                raw_sentence = point.raw_sentence or ""
                sentence_id = raw_sentence.split(",", 1)[0]
                if not sentence_id.endswith("GGA"):
                    continue

            value = getattr(point, metric)
            if value is None:
                continue

            seconds_of_day = (
                point.timestamp.hour * 3600
                + point.timestamp.minute * 60
                + point.timestamp.second
                + point.timestamp.microsecond / 1_000_000
            )
            if last_seconds_of_day is not None and seconds_of_day < last_seconds_of_day:
                day_offset_seconds += 86400.0
            last_seconds_of_day = seconds_of_day

            x_vals.append(self._aligned_anchor_ts + day_offset_seconds + seconds_of_day)
            y_vals.append(float(value))

        return x_vals, y_vals