from __future__ import annotations

from math import cos, radians, sin
from typing import Sequence

import pyqtgraph as pg
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QGraphicsEllipseItem, QLabel, QVBoxLayout, QWidget

from app.core.models import NMEAPoint


CONSTELLATION_COLORS = {
    "GPS": "#3b82f6",
    "GLONASS": "#22c55e",
    "Galileo": "#f59e0b",
    "BeiDou": "#ef4444",
    "QZSS": "#a855f7",
    "NavIC": "#06b6d4",
    "Mixed": "#94a3b8",
    "Other": "#64748b",
}


class SatelliteViewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._title_color = "#dbeafe"
        self._plot_bg = "#0b1323"
        self._axis_pen = "#425266"
        self._axis_text_pen = "#a3b6cc"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        legend_row = QHBoxLayout()
        legend_row.setSpacing(10)
        legend_title = QLabel("Legend:")
        legend_row.addWidget(legend_title)

        self._legend_dots: list[QLabel] = []
        for constellation in ["GPS", "GLONASS", "Galileo", "BeiDou", "QZSS", "NavIC", "Other"]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {CONSTELLATION_COLORS[constellation]};")
            text = QLabel(constellation)
            self._legend_dots.append(dot)
            legend_row.addWidget(dot)
            legend_row.addWidget(text)

        legend_row.addStretch(1)
        root.addLayout(legend_row)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        root.addLayout(self._grid, 1)

        self._pane_widgets: list[QWidget] = []
        self._receiver_labels: list[QLabel] = []
        self._summary_labels: list[QLabel] = []
        self._sky_plots: list[pg.PlotWidget] = []
        self._sky_plot_items: list[pg.PlotItem] = []
        self._snr_plots: list[pg.PlotWidget] = []
        self._snr_plot_items: list[pg.PlotItem] = []

        for pane_idx in range(2):
            pane = QWidget(self)
            pane_layout = QVBoxLayout(pane)
            pane_layout.setContentsMargins(0, 0, 0, 0)
            pane_layout.setSpacing(6)

            receiver_label = QLabel(f"Receiver {pane_idx + 1}")
            pane_layout.addWidget(receiver_label)

            summary_label = QLabel("Satellites: 0 | Used: 0 | Avg SNR: N/A")
            pane_layout.addWidget(summary_label)

            sky_plot = pg.PlotWidget(self)
            sky_plot_item = sky_plot.getPlotItem()
            sky_plot_item.hideAxis("bottom")
            sky_plot_item.hideAxis("left")
            sky_plot_item.setAspectLocked(True)
            sky_plot_item.setTitle("Skyplot", color=self._title_color, size="12pt")
            pane_layout.addWidget(sky_plot, 1)

            snr_plot = pg.PlotWidget(self)
            snr_plot_item = snr_plot.getPlotItem()
            snr_plot_item.setLabel("left", "SNR (dB-Hz)")
            snr_plot_item.setLabel("bottom", "Satellite ID")
            snr_plot_item.setTitle("SNR by Satellite", color=self._title_color, size="12pt")
            pane_layout.addWidget(snr_plot, 1)

            self._pane_widgets.append(pane)
            self._receiver_labels.append(receiver_label)
            self._summary_labels.append(summary_label)
            self._sky_plots.append(sky_plot)
            self._sky_plot_items.append(sky_plot_item)
            self._snr_plots.append(snr_plot)
            self._snr_plot_items.append(snr_plot_item)

            self._grid.addWidget(pane, 0, pane_idx)

        self.set_theme("dark")
        self.clear_view()

    def set_view_data(self, entries: Sequence[tuple[str, NMEAPoint | None]]) -> None:
        visible_entries = list(entries[:2])

        if not visible_entries:
            self.clear_view()
            return

        for pane_idx in range(2):
            if pane_idx < len(visible_entries):
                receiver_name, point = visible_entries[pane_idx]
                self._pane_widgets[pane_idx].show()
                self._receiver_labels[pane_idx].setText(f"Receiver: {receiver_name}")
                self._set_point_for_pane(pane_idx, point)
            else:
                self._pane_widgets[pane_idx].hide()

    def clear_view(self) -> None:
        self._pane_widgets[0].show()
        self._pane_widgets[1].hide()
        self._receiver_labels[0].setText("Receiver: N/A")
        self._summary_labels[0].setText("Satellites: 0 | Used: 0 | Avg SNR: N/A")
        self._render_skyplot(0, [], set())
        self._render_snr(0, [])

    def _set_point_for_pane(self, pane_idx: int, point: NMEAPoint | None) -> None:
        if point is None or not point.satellites:
            self._summary_labels[pane_idx].setText("Satellites: 0 | Used: 0 | Avg SNR: N/A")
            self._render_skyplot(pane_idx, [], set())
            self._render_snr(pane_idx, [])
            return

        satellites = point.satellites
        used = set(point.used_satellite_ids)

        snr_values = [s.snr_dbhz for s in satellites if s.snr_dbhz is not None]
        avg_snr_text = f"{(sum(snr_values) / len(snr_values)):.1f}" if snr_values else "N/A"
        self._summary_labels[pane_idx].setText(
            f"Satellites: {len(satellites)} | Used: {len(used)} | Avg SNR: {avg_snr_text}"
        )

        self._render_skyplot(pane_idx, satellites, used)
        self._render_snr(pane_idx, satellites)

    def _render_skyplot(self, pane_idx: int, satellites, used_ids: set[int]) -> None:
        sky_plot_item = self._sky_plot_items[pane_idx]
        sky_plot_item.clear()

        # Skyplot grid: outer ring is horizon, center is zenith.
        for r in [0.25, 0.5, 0.75, 1.0]:
            circle = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
            circle.setPen(pg.mkPen(self._axis_pen, width=1))
            sky_plot_item.addItem(circle)

        sky_plot_item.plot([0, 0], [-1, 1], pen=pg.mkPen(self._axis_pen, width=1))
        sky_plot_item.plot([-1, 1], [0, 0], pen=pg.mkPen(self._axis_pen, width=1))

        for sat in satellites:
            if sat.azimuth_deg is None or sat.elevation_deg is None:
                continue

            radius = max(0.0, min(1.0, (90.0 - sat.elevation_deg) / 90.0))
            theta = radians(sat.azimuth_deg)
            x = radius * sin(theta)
            y = radius * cos(theta)

            color = CONSTELLATION_COLORS.get(sat.constellation, CONSTELLATION_COLORS["Other"])
            pen_width = 2.5 if sat.sat_id in used_ids else 1.2
            sky_plot_item.plot(
                [x],
                [y],
                pen=None,
                symbol="o",
                symbolSize=10,
                symbolBrush=pg.mkBrush(color),
                symbolPen=pg.mkPen("#f8fafc", width=pen_width),
            )

            label = pg.TextItem(text=str(sat.sat_id), color=self._axis_text_pen, anchor=(0.5, -0.2))
            label.setPos(x, y)
            sky_plot_item.addItem(label)

        sky_plot_item.setXRange(-1.08, 1.08, padding=0)
        sky_plot_item.setYRange(-1.08, 1.08, padding=0)

    def _render_snr(self, pane_idx: int, satellites) -> None:
        snr_plot_item = self._snr_plot_items[pane_idx]
        snr_plot_item.clear()
        if not satellites:
            snr_plot_item.setXRange(0, 1, padding=0)
            snr_plot_item.setYRange(0, 1, padding=0)
            return

        sats_sorted = sorted(satellites, key=lambda s: s.sat_id)
        x_vals = list(range(len(sats_sorted)))
        heights = [float(s.snr_dbhz) if s.snr_dbhz is not None else 0.0 for s in sats_sorted]
        brushes = [
            pg.mkBrush(CONSTELLATION_COLORS.get(s.constellation, CONSTELLATION_COLORS["Other"]))
            for s in sats_sorted
        ]

        bar = pg.BarGraphItem(x=x_vals, height=heights, width=0.8, brushes=brushes)
        snr_plot_item.addItem(bar)

        labels = [(idx, str(s.sat_id)) for idx, s in enumerate(sats_sorted)]
        axis = snr_plot_item.getAxis("bottom")
        axis.setTicks([labels])
        y_max = max(10.0, max(heights) + 5.0)
        snr_plot_item.setYRange(0, y_max, padding=0.02)
        snr_plot_item.setXRange(-0.8, len(x_vals) - 0.2, padding=0)

    def set_theme(self, theme: str) -> None:
        if theme == "light":
            self._title_color = "#1e3a5f"
            self._plot_bg = "#ffffff"
            self._axis_pen = "#97a6b7"
            self._axis_text_pen = "#475569"
            self.setStyleSheet("QLabel { color: #0f172a; }")
        else:
            self._title_color = "#dbeafe"
            self._plot_bg = "#0b1323"
            self._axis_pen = "#425266"
            self._axis_text_pen = "#a3b6cc"
            self.setStyleSheet("QLabel { color: #e2e8f0; }")

        for dot, constellation in zip(
            self._legend_dots,
            ["GPS", "GLONASS", "Galileo", "BeiDou", "QZSS", "NavIC", "Other"],
        ):
            dot.setStyleSheet(f"color: {CONSTELLATION_COLORS[constellation]};")

        for plot in (*self._sky_plots, *self._snr_plots):
            plot.setBackground(self._plot_bg)
            plot.showGrid(x=True, y=True, alpha=0.2)
            plot.getAxis("left").setPen(pg.mkPen(self._axis_pen, width=1))
            plot.getAxis("left").setTextPen(pg.mkPen(self._axis_text_pen))
            plot.getAxis("bottom").setPen(pg.mkPen(self._axis_pen, width=1))
            plot.getAxis("bottom").setTextPen(pg.mkPen(self._axis_text_pen))

        for sky_item in self._sky_plot_items:
            sky_item.setTitle("Skyplot", color=self._title_color, size="12pt")
        for snr_item in self._snr_plot_items:
            snr_item.setTitle("SNR by Satellite", color=self._title_color, size="12pt")
