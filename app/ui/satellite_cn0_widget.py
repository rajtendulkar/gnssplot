from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from pyqtgraph.exporters import ImageExporter

from app.core.models import NMEADataset


class SatelliteCN0Widget(QWidget):
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

        self._theme = "dark"
        self._title_color = "#dbeafe"
        self._plot_bg = "#0b1323"
        self._axis_pen = "#425266"
        self._axis_text_pen = "#a3b6cc"
        self._grid_alpha = 0.2

        self._datasets: dict[str, NMEADataset] = {}
        self._selected_receivers: list[str] = []
        self._plot_widgets: list[pg.PlotWidget] = []
        self._cursor_lines: list[pg.InfiniteLine] = []
        self._playback_timestamp: float | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Plots Per Row:"))
        self.columns_spin = QSpinBox(self)
        self.columns_spin.setObjectName("cn0ColumnsSpin")
        self.columns_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        self.columns_spin.setRange(1, 6)
        self.columns_spin.setValue(2)
        self.columns_spin.valueChanged.connect(self._refresh)
        controls.addWidget(self.columns_spin)
        controls.addWidget(QLabel("Constellation:"))
        self.constellation_box = QComboBox(self)
        self.constellation_box.setObjectName("cn0ConstellationBox")
        self.constellation_box.addItem("All Satellites", "all")
        self.constellation_box.addItem("GPS", "gps")
        self.constellation_box.addItem("GAL", "gal")
        self.constellation_box.addItem("GPS & GAL", "gps_gal")
        self.constellation_box.currentIndexChanged.connect(self._refresh)
        controls.addWidget(self.constellation_box)
        self.summary_label = QLabel("Satellites: 0")
        controls.addWidget(self.summary_label)
        controls.addStretch(1)
        root.addLayout(controls)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("cn0ScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_content = QWidget(self.scroll_area)
        self.scroll_content.setObjectName("cn0ScrollContent")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)
        self.scroll_area.setWidget(self.scroll_content)
        root.addWidget(self.scroll_area, 1)

        self._empty_label = QLabel("No satellite CN0 data available for the selected logs.")
        self._empty_label.setWordWrap(True)

        self.set_theme("dark")
        self._refresh()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        if theme == "light":
            self._title_color = "#1e3a5f"
            self._plot_bg = "#ffffff"
            self._axis_pen = "#97a6b7"
            self._axis_text_pen = "#475569"
            self._grid_alpha = 0.15
            self.setStyleSheet(
                """
                QLabel { color: #0f172a; }
                QSpinBox#cn0ColumnsSpin {
                    background: #ffffff;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 2px 6px;
                    min-height: 24px;
                }
                QSpinBox#cn0ColumnsSpin::up-button,
                QSpinBox#cn0ColumnsSpin::down-button {
                    background: #e2e8f0;
                    color: #0f172a;
                    border: 1px solid #94a3b8;
                    width: 16px;
                }
                QComboBox#cn0ConstellationBox {
                    background: #ffffff;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 2px 8px;
                    min-height: 24px;
                }
                QComboBox#cn0ConstellationBox QAbstractItemView {
                    background: #ffffff;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    selection-background-color: #bfdbfe;
                    selection-color: #0f172a;
                }
                QScrollArea#cn0ScrollArea,
                QWidget#cn0ScrollContent {
                    background: #f8fafc;
                }
                """
            )
        else:
            self._title_color = "#dbeafe"
            self._plot_bg = "#0b1323"
            self._axis_pen = "#425266"
            self._axis_text_pen = "#a3b6cc"
            self._grid_alpha = 0.2
            self.setStyleSheet(
                """
                QLabel { color: #e2e8f0; }
                QSpinBox#cn0ColumnsSpin {
                    background: #0b1220;
                    color: #e2e8f0;
                    border: 1px solid #475569;
                    border-radius: 6px;
                    padding: 2px 6px;
                    min-height: 24px;
                }
                QSpinBox#cn0ColumnsSpin::up-button,
                QSpinBox#cn0ColumnsSpin::down-button {
                    background: #475569;
                    color: #f8fafc;
                    border: 1px solid #94a3b8;
                    width: 16px;
                }
                QComboBox#cn0ConstellationBox {
                    background: #0b1220;
                    color: #e2e8f0;
                    border: 1px solid #475569;
                    border-radius: 6px;
                    padding: 2px 8px;
                    min-height: 24px;
                }
                QComboBox#cn0ConstellationBox QAbstractItemView {
                    background: #111827;
                    color: #e2e8f0;
                    border: 1px solid #475569;
                    selection-background-color: #1d4e89;
                    selection-color: #eff6ff;
                }
                QScrollArea#cn0ScrollArea,
                QWidget#cn0ScrollContent {
                    background: #0b1220;
                }
                """
            )

        for plot in self._plot_widgets:
            self._configure_plot(plot)

    def set_view_data(self, datasets: dict[str, NMEADataset], selected_receivers: list[str]) -> None:
        self._datasets = datasets
        self._selected_receivers = selected_receivers
        self._refresh()

    def set_playback_time(self, timestamp) -> None:
        if timestamp is None:
            self._playback_timestamp = None
            return

        try:
            self._playback_timestamp = float(timestamp.timestamp())
        except Exception:
            self._playback_timestamp = None
            return

        for cursor in self._cursor_lines:
            cursor.setValue(self._playback_timestamp)

    def export_metric_gallery(
        self,
        datasets: dict[str, NMEADataset],
        output_dir: str,
        group_name: str,
        selected_receivers: list[str] | None = None,
    ) -> list[tuple[str, str]]:
        active_receivers = self._active_receivers(datasets, selected_receivers or [])
        if not active_receivers:
            return []

        sat_series = self._build_satellite_series(datasets, active_receivers)
        if not sat_series:
            return []

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        exported_files: list[tuple[str, str]] = []
        for constellation, sat_id in self._sorted_satellite_keys(sat_series.keys()):
            plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
            self._configure_plot(plot)
            plot_item = plot.getPlotItem()
            plot_item.setTitle(
                f"{constellation} {sat_id} CN0",
                color=self._title_color,
                size="12pt",
            )
            plot_item.setLabel("left", "CN0 (dB-Hz)")
            plot_item.setLabel("bottom", "Time")
            plot_item.addLegend(offset=(10, 10))

            for receiver_idx, receiver in enumerate(active_receivers):
                entries = sat_series[(constellation, sat_id)].get(receiver)
                if not entries:
                    continue
                x_vals = [x for x, _ in entries]
                y_vals = [y for _, y in entries]
                pen = pg.mkPen(self.COLORS[receiver_idx % len(self.COLORS)], width=2)
                plot_item.plot(x=x_vals, y=y_vals, pen=pen, name=receiver)

            constellation_slug = constellation.lower().replace(" ", "_")
            file_name = f"{group_name}_{constellation_slug}_{sat_id}.png"
            file_path = output_path / file_name
            exporter = ImageExporter(plot_item)
            try:
                exporter.parameters()["width"] = 1200
            except Exception:
                pass
            exporter.export(str(file_path))
            exported_files.append((f"{group_name}/{file_name}", str(file_path)))

        return exported_files

    def _active_receivers(
        self,
        datasets: dict[str, NMEADataset] | None = None,
        selected_receivers: list[str] | None = None,
    ) -> list[str]:
        data = datasets if datasets is not None else self._datasets
        selected = selected_receivers if selected_receivers is not None else self._selected_receivers

        valid_selected = [name for name in selected if name in data]
        if valid_selected:
            return valid_selected
        return list(data.keys())

    def _build_satellite_series(
        self,
        datasets: dict[str, NMEADataset],
        active_receivers: list[str],
    ) -> dict[tuple[str, int], dict[str, list[tuple[float, float]]]]:
        sat_series: dict[tuple[str, int], dict[str, list[tuple[float, float]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        filter_mode = str(self.constellation_box.currentData() or "all")

        for receiver in active_receivers:
            dataset = datasets.get(receiver)
            if dataset is None:
                continue
            for point in dataset.points:
                if point.timestamp is None:
                    continue
                ts = point.timestamp.timestamp()
                for sat in point.satellites:
                    if sat.snr_dbhz is None:
                        continue
                    if not self._satellite_allowed(filter_mode, sat.constellation):
                        continue
                    sat_series[(sat.constellation, sat.sat_id)][receiver].append((ts, float(sat.snr_dbhz)))

        for sat_key in list(sat_series.keys()):
            for receiver in list(sat_series[sat_key].keys()):
                sat_series[sat_key][receiver].sort(key=lambda pair: pair[0])

        return sat_series

    def _clear_scroll_plots(self) -> None:
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._plot_widgets = []
        self._cursor_lines = []

    def _refresh(self) -> None:
        self._clear_scroll_plots()

        active_receivers = self._active_receivers()
        if not active_receivers:
            self.summary_label.setText("Satellites: 0")
            self.scroll_layout.addWidget(self._empty_label)
            self.scroll_layout.addStretch(1)
            return

        sat_series = self._build_satellite_series(self._datasets, active_receivers)
        sat_keys = self._sorted_satellite_keys(sat_series.keys())
        self.summary_label.setText(f"Satellites: {len(sat_keys)}")

        if not sat_keys:
            self.scroll_layout.addWidget(self._empty_label)
            self.scroll_layout.addStretch(1)
            return

        columns = max(1, self.columns_spin.value())
        min_plot_height = self._target_plot_min_height()
        grid_host = QWidget(self.scroll_content)
        grid = QVBoxLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        row_container: QWidget | None = None
        row_layout: QHBoxLayout | None = None

        for idx, sat_key in enumerate(sat_keys):
            constellation, sat_id = sat_key
            if idx % columns == 0:
                row_container = QWidget(grid_host)
                row_layout = QHBoxLayout(row_container)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)
                grid.addWidget(row_container)

            plot = pg.PlotWidget(row_container, axisItems={"bottom": pg.DateAxisItem()})
            self._configure_plot(plot)
            plot.setMinimumHeight(min_plot_height)
            plot_item = plot.getPlotItem()
            plot_item.setTitle(
                f"{constellation} {sat_id} CN0",
                color=self._title_color,
                size="11pt",
            )
            plot_item.setLabel("left", "CN0 (dB-Hz)")
            plot_item.setLabel("bottom", "Time")
            plot_item.addLegend(offset=(10, 10))

            cursor = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#93c5fd", width=1.2))
            plot_item.addItem(cursor)
            if self._playback_timestamp is not None:
                cursor.setValue(self._playback_timestamp)
            self._cursor_lines.append(cursor)

            for receiver_idx, receiver in enumerate(active_receivers):
                entries = sat_series[sat_key].get(receiver)
                if not entries:
                    continue
                x_vals = [x for x, _ in entries]
                y_vals = [y for _, y in entries]
                pen = pg.mkPen(self.COLORS[receiver_idx % len(self.COLORS)], width=2)
                plot_item.plot(x=x_vals, y=y_vals, pen=pen, name=receiver)

            if row_layout is not None:
                row_layout.addWidget(plot)
            self._plot_widgets.append(plot)

        grid.addStretch(1)
        self.scroll_layout.addWidget(grid_host)

    def _configure_plot(self, plot: pg.PlotWidget) -> None:
        plot.setBackground(self._plot_bg)
        plot.showGrid(x=True, y=True, alpha=self._grid_alpha)
        plot.getAxis("left").setPen(pg.mkPen(self._axis_pen, width=1))
        plot.getAxis("left").setTextPen(pg.mkPen(self._axis_text_pen))
        plot.getAxis("bottom").setPen(pg.mkPen(self._axis_pen, width=1))
        plot.getAxis("bottom").setTextPen(pg.mkPen(self._axis_text_pen))

    def _target_plot_min_height(self) -> int:
        # Keep each plot readable: ~20% of window height, clamped in a sensible range.
        return max(200, min(520, int(self.height() * 0.20)))

    def resizeEvent(self, event) -> None:
        min_height = self._target_plot_min_height()
        for plot in self._plot_widgets:
            plot.setMinimumHeight(min_height)
        super().resizeEvent(event)

    @staticmethod
    def _satellite_allowed(filter_mode: str, constellation: str) -> bool:
        if filter_mode == "all":
            return True
        if filter_mode == "gps":
            return constellation == "GPS"
        if filter_mode == "gal":
            return constellation == "Galileo"
        if filter_mode == "gps_gal":
            return constellation in {"GPS", "Galileo"}
        return True

    @staticmethod
    def _sorted_satellite_keys(keys):
        return sorted(keys, key=lambda key: (str(key[0]), int(key[1])))
