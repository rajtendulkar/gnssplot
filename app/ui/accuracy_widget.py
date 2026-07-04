from __future__ import annotations

from typing import Iterable

import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class AccuracyWidget(QWidget):
    reference_changed = pyqtSignal(str)

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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("Reference log:"))
        self.reference_box = QComboBox(self)
        self.reference_box.currentTextChanged.connect(self._on_reference_changed)
        top.addWidget(self.reference_box)
        top.addStretch(1)
        root.addLayout(top)

        self.plot = pg.PlotWidget(self, axisItems={"bottom": pg.DateAxisItem()})
        self.plot_item = self.plot.getPlotItem()
        self.plot_item.setLabel("left", "Horizontal Error (m)")
        self.plot_item.setLabel("bottom", "Time")
        root.addWidget(self.plot, 1)

        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Receiver",
            "Samples",
            "Mean (m)",
            "Median (m)",
            "P95 (m)",
            "Max (m)",
        ])
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)

        self.set_theme("dark")

    def _on_reference_changed(self, text: str) -> None:
        if text:
            self.reference_changed.emit(text)

    def current_reference(self) -> str | None:
        text = self.reference_box.currentText().strip()
        return text if text else None

    def set_reference_options(self, names: Iterable[str], current: str | None = None) -> None:
        unique_names = list(dict.fromkeys(names))
        current_text = current if current else self.current_reference()

        self.reference_box.blockSignals(True)
        self.reference_box.clear()
        self.reference_box.addItems(unique_names)

        if current_text:
            idx = self.reference_box.findText(current_text)
            if idx >= 0:
                self.reference_box.setCurrentIndex(idx)
            elif self.reference_box.count() > 0:
                self.reference_box.setCurrentIndex(0)
        elif self.reference_box.count() > 0:
            self.reference_box.setCurrentIndex(0)

        self.reference_box.blockSignals(False)

    def set_accuracy_data(
        self,
        series_by_receiver: dict[str, tuple[list[float], list[float]]],
        rows: list[dict[str, float | int | str]],
    ) -> None:
        self.plot_item.clear()
        if self.plot_item.legend is not None:
            self.plot_item.legend.scene().removeItem(self.plot_item.legend)
            self.plot_item.legend = None
        self.plot_item.addLegend(offset=(10, 10))
        self.plot_item.setTitle("Horizontal Error vs Reference", color=self._title_color, size="12pt")

        for i, (receiver, (x_vals, y_vals)) in enumerate(series_by_receiver.items()):
            if not x_vals:
                continue
            pen = pg.mkPen(color=self.COLORS[i % len(self.COLORS)], width=2)
            self.plot_item.plot(x=x_vals, y=y_vals, pen=pen, name=receiver)

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(row.get("receiver", ""))))
            self.table.setItem(r, 1, QTableWidgetItem(str(row.get("samples", 0))))
            self.table.setItem(r, 2, QTableWidgetItem(str(row.get("mean_m", 0))))
            self.table.setItem(r, 3, QTableWidgetItem(str(row.get("median_m", 0))))
            self.table.setItem(r, 4, QTableWidgetItem(str(row.get("p95_m", 0))))
            self.table.setItem(r, 5, QTableWidgetItem(str(row.get("max_m", 0))))

        self.table.resizeColumnsToContents()

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
                QTableWidget {
                    background: #ffffff;
                    border: 1px solid #d1dae5;
                    border-radius: 8px;
                    color: #0f172a;
                    gridline-color: #e2e8f0;
                }
                QHeaderView::section {
                    background: #f1f5f9;
                    border: 0;
                    border-bottom: 1px solid #d1dae5;
                    padding: 5px;
                    color: #0f172a;
                    font-weight: 600;
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
                QTableWidget {
                    background: #0b1220;
                    border: 1px solid #243244;
                    border-radius: 8px;
                    color: #e2e8f0;
                    gridline-color: #1e2b3e;
                }
                QHeaderView::section {
                    background: #111827;
                    border: 0;
                    border-bottom: 1px solid #243244;
                    padding: 5px;
                    color: #dbeafe;
                    font-weight: 600;
                }
                """
            )

        self.plot.setBackground(self._plot_bg)
        self.plot.showGrid(x=True, y=True, alpha=self._grid_alpha)
        self.plot.getAxis("left").setPen(pg.mkPen(self._axis_pen, width=1))
        self.plot.getAxis("left").setTextPen(pg.mkPen(self._axis_text_pen))
        self.plot.getAxis("bottom").setPen(pg.mkPen(self._axis_pen, width=1))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen(self._axis_text_pen))
