from __future__ import annotations

import os
import sys
import tempfile
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from statistics import median

from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from app.core.engine import CoreEngine
from app.core.models import NMEADataset, NMEAPoint
from app.io.file_handler import (
    choose_nmea_files,
    choose_report_bundle_path,
    export_report_bundle as write_report_bundle,
    receiver_name_from_path,
)
from app.parser.parser_thread import NMEAParserThread
from app.ui.accuracy_widget import AccuracyWidget
from app.ui.map_widget import MapWidget
from app.ui.plot_widget import ComparisonPlotWidget
from app.ui.satellite_widget import SatelliteViewWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GNSS NMEA Comparator")
        self.resize(1600, 900)

        self.engine = CoreEngine(self)
        self.parse_threads: dict[str, NMEAParserThread] = {}
        self.parse_progress: dict[str, int] = {}
        self.log_visibility: dict[str, bool] = {}
        self._last_map_index: int | None = None
        self._last_accuracy_rows: list[dict[str, float | int | str]] = []
        self._pending_console_index: int | None = None
        self._console_tab_index: int = 2
        self._console_window_by_log: dict[str, tuple[int, int]] = {}
        self._console_selection_key: tuple[str, ...] = ()

        self.plot_widget = ComparisonPlotWidget(self)
        self.accuracy_widget = AccuracyWidget(self)
        self.satellite_widget = SatelliteViewWidget(self)
        self.map_popout_window = QMainWindow(self)
        self.map_popout_window.setWindowTitle("GNSS Playback Map")
        self.map_popout_window.resize(950, 650)
        self.map_widget = MapWidget(self)
        self.map_popout_host = QWidget(self.map_popout_window)
        self.map_popout_layout = QVBoxLayout(self.map_popout_host)
        self.map_popout_layout.setContentsMargins(0, 0, 0, 0)
        self.map_popout_window.setCentralWidget(self.map_popout_host)
        self._map_is_popped_out = False
        self.map_popout_window.installEventFilter(self)

        self.load_button = QPushButton("Add NMEA Logs")
        self.remove_button = QPushButton("Remove Selected")
        self.clear_button = QPushButton("Clear Logs")
        self.play_button = QToolButton(self)
        self.play_button.setText("")
        self.play_button.setToolTip("Play")
        self.play_button.setFixedWidth(34)

        self.pause_button = QToolButton(self)
        self.pause_button.setText("")
        self.pause_button.setToolTip("Pause")
        self.pause_button.setFixedWidth(34)

        self.stop_button = QToolButton(self)
        self.stop_button.setText("")
        self.stop_button.setToolTip("Stop")
        self.stop_button.setFixedWidth(34)
        self.step_button = QToolButton(self)
        self.step_button.setText("")
        self.step_button.setToolTip("Step Forward")
        self.step_button.setFixedWidth(34)
        self.step_button.setEnabled(False)
        self.reset_plots_button = QPushButton("Reset Plots")
        self.export_button = QPushButton("Export Report Bundle")
        self.map_tab_popout_button = QPushButton("Pop Out")
        self.map_fit_button = QPushButton("Fit Visible")
        self.map_follow_checkbox = QCheckBox("Follow Playback")
        self.map_follow_checkbox.setChecked(True)

        self.speed_box = QComboBox()
        self.speed_box.addItems(["0.5x", "1x", "2x", "4x"])
        self.speed_box.setCurrentText("1x")

        self.timeline_mode_box = QComboBox()
        self.timeline_mode_box.addItem("Aligned Time", "aligned")
        self.timeline_mode_box.addItem("GGA Time", "gga")
        self.timeline_mode_box.addItem("Index", "index")
        self.timeline_mode_box.setCurrentIndex(0)

        self.theme_box = QComboBox()
        self.theme_box.addItems(["Dark", "Light"])
        self.theme_box.setCurrentText("Dark")

        self.map_dots_checkbox = QCheckBox("Show Dots")
        self.map_dots_checkbox.setChecked(False)

        self.time_label = QLabel("Time: N/A")
        self.index_label = QLabel("Index: 0/0")

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setObjectName("timelineSlider")

        self.tabs = QTabWidget(self)
        self.console_view = QPlainTextEdit(self)
        self.console_view.setReadOnly(True)
        self.console_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.console_view.setObjectName("consoleView")

        self.log_list = QListWidget()
        self.log_list.setMaximumWidth(280)
        self.log_list.setObjectName("logList")
        self.log_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.log_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.time_label.setObjectName("toolbarInfo")
        self.index_label.setObjectName("toolbarInfo")
        self._setup_transport_icons()

        self._build_toolbar()
        self._build_ui()
        self._apply_theme("dark")
        self._wire_signals()
        self._update_playback_buttons(False)
        self.setAcceptDrops(True)

    def _setup_transport_icons(self) -> None:
        style = self.style()
        self.play_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.pause_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.stop_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.step_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        toolbar.setObjectName("mainToolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        toolbar.addWidget(self.load_button)
        toolbar.addWidget(self.remove_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addWidget(self.play_button)
        toolbar.addWidget(self.pause_button)
        toolbar.addWidget(self.stop_button)
        toolbar.addWidget(self.step_button)
        toolbar.addWidget(self.reset_plots_button)
        toolbar.addWidget(self.export_button)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Playback:"))
        toolbar.addWidget(self.speed_box)
        toolbar.addWidget(QLabel("Timeline:"))
        toolbar.addWidget(self.timeline_mode_box)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Theme:"))
        toolbar.addWidget(self.theme_box)
        toolbar.addWidget(self.map_dots_checkbox)

        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        toolbar.addSeparator()
        toolbar.addWidget(self.time_label)
        toolbar.addWidget(self.index_label)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        sidebar = QWidget()
        sidebar.setObjectName("sidePanel")
        sidebar_layout = QVBoxLayout(sidebar)
        side_title = QLabel("Loaded Logs")
        side_title.setObjectName("sectionTitle")
        sidebar_layout.addWidget(side_title)
        sidebar_layout.addWidget(self.log_list)

        plots_tab = QWidget(self)
        plots_tab_layout = QVBoxLayout(plots_tab)
        plots_tab_layout.setContentsMargins(0, 0, 0, 0)
        plots_tab_layout.addWidget(self.plot_widget)

        console_tab = QWidget(self)
        console_layout = QVBoxLayout(console_tab)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.addWidget(self.console_view)

        map_tab = QWidget(self)
        map_tab_layout = QVBoxLayout(map_tab)
        map_tab_layout.setContentsMargins(0, 0, 0, 0)

        map_head = QHBoxLayout()
        map_head.addWidget(self.map_follow_checkbox)
        map_head.addWidget(self.map_fit_button)
        map_head.addStretch(1)
        map_head.addWidget(self.map_tab_popout_button)
        map_tab_layout.addLayout(map_head)

        self.map_host = QWidget(map_tab)
        self.map_host_layout = QVBoxLayout(self.map_host)
        self.map_host_layout.setContentsMargins(0, 0, 0, 0)
        self.map_host_layout.addWidget(self.map_widget)
        map_tab_layout.addWidget(self.map_host)

        self.tabs.addTab(plots_tab, "Plots")
        self.tabs.addTab(self.accuracy_widget, "Accuracy")
        self.tabs.addTab(self.satellite_widget, "Satellite")
        self._console_tab_index = self.tabs.addTab(console_tab, "Console")
        self.tabs.addTab(map_tab, "Map")
        self.tabs.setCurrentIndex(0)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setObjectName("mainSplitter")
        main_splitter.addWidget(sidebar)
        main_splitter.addWidget(self.tabs)
        main_splitter.setSizes([290, 1310])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 5)

        root_layout.addWidget(self.slider)
        root_layout.addWidget(main_splitter, 1)

        self.setStatusBar(QStatusBar(self))
        self.setCentralWidget(root)

    def _wire_signals(self) -> None:
        self.load_button.clicked.connect(self.load_logs)
        self.remove_button.clicked.connect(self.remove_selected_logs)
        self.clear_button.clicked.connect(self.clear_logs)
        self.play_button.clicked.connect(self.on_play_clicked)
        self.pause_button.clicked.connect(self.on_pause_clicked)
        self.stop_button.clicked.connect(self.on_stop_clicked)
        self.step_button.clicked.connect(self.on_step_clicked)
        self.reset_plots_button.clicked.connect(self.plot_widget.reset_all_views)
        self.export_button.clicked.connect(self.export_summary)
        self.map_tab_popout_button.clicked.connect(self.toggle_map_popout)
        self.map_fit_button.clicked.connect(self.on_map_fit_visible)
        self.map_follow_checkbox.toggled.connect(self.on_map_follow_toggled)
        self.accuracy_widget.reference_changed.connect(self.on_reference_changed)

        self.speed_box.currentTextChanged.connect(self.change_speed)
        self.timeline_mode_box.currentIndexChanged.connect(self.on_timeline_mode_changed)
        self.theme_box.currentTextChanged.connect(self.on_theme_changed)
        self.map_dots_checkbox.toggled.connect(self.on_map_dots_toggled)
        self.slider.valueChanged.connect(self.engine.set_index)

        self.engine.datasets_changed.connect(self.on_datasets_changed)
        self.engine.playback_updated.connect(self.on_playback_updated)
        self.engine.playback_state_changed.connect(self.on_playback_state_changed)
        self.log_list.itemChanged.connect(self.on_log_item_changed)
        self.log_list.itemSelectionChanged.connect(self.on_log_selection_changed)
        self.log_list.customContextMenuRequested.connect(self.show_log_list_context_menu)
        self.tabs.currentChanged.connect(self.on_tab_changed)

    def _apply_theme(self, theme: str) -> None:
        if theme == "light":
            stylesheet = """
            QMainWindow { background: #eef2f7; }
            QWidget { color: #1e293b; font-size: 12px; }
            QToolBar#mainToolbar { background: #f8fafc; border: 0; spacing: 8px; padding: 6px; }
            QToolBar#mainToolbar QToolButton, QPushButton {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 7px;
                padding: 6px 10px; color: #0f172a;
            }
            QToolBar#mainToolbar QToolButton {
                min-width: 28px;
                padding: 4px 6px;
            }
            QToolBar#mainToolbar QToolButton:hover, QPushButton:hover {
                background: #f1f5f9; border-color: #7aa2d6;
            }
            QToolBar#mainToolbar QToolButton:pressed, QPushButton:pressed { background: #e2e8f0; }
            QComboBox {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                background: #ffffff; border: 1px solid #cbd5e1;
                selection-background-color: #bfdbfe; selection-color: #0f172a;
                outline: 0;
                alternate-background-color: #ffffff;
            }
            QComboBox QAbstractItemView::item {
                border: none;
                min-height: 20px;
                padding: 2px 6px;
                margin: 0;
            }
            QComboBox QAbstractItemView::item:selected {
                border: none;
                background: #bfdbfe;
                color: #0f172a;
            }
            QWidget#sidePanel { background: #f8fafc; border: 1px solid #d7e0ea; border-radius: 10px; }
            QLabel#sectionTitle {
                color: #0f4c81; font-size: 13px; font-weight: 600; padding: 4px 2px;
            }
            QLabel#toolbarInfo { color: #0f4c81; font-weight: 600; }
            QListWidget#logList {
                background: #ffffff; border: 1px solid #d1dae5; border-radius: 8px; padding: 4px;
            }
            QListWidget#logList::item { padding: 6px; border-radius: 5px; }
            QListWidget#logList::item:selected { background: #bfdbfe; color: #0f172a; }
            QSlider#timelineSlider::groove:horizontal {
                background: #d7e0ea; height: 8px; border-radius: 4px;
            }
            QSlider#timelineSlider::handle:horizontal {
                background: #3b82f6; width: 16px; margin: -4px 0; border-radius: 8px;
            }
            QStatusBar { background: #f8fafc; border-top: 1px solid #d7e0ea; color: #334155; }
            QTabWidget::pane {
                border: 1px solid #d1dae5;
                border-radius: 8px;
                top: -1px;
                background: #f8fafc;
            }
            QTabBar::tab {
                background: #e2e8f0;
                color: #334155;
                border: 1px solid #d1dae5;
                border-bottom: none;
                padding: 6px 12px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: #f8fafc;
                color: #0f172a;
                font-weight: 600;
            }
            QTabBar::tab:hover { color: #0f172a; }
            QPlainTextEdit#consoleView {
                background: #ffffff;
                border: 1px solid #d1dae5;
                border-radius: 8px;
                color: #0f172a;
                font-family: Consolas, 'Liberation Mono', monospace;
                font-size: 12px;
            }
            QFileDialog, QFileDialog QWidget {
                background: #f8fafc;
                color: #0f172a;
            }
            QFileDialog QLabel {
                color: #334155;
            }
            QFileDialog QLineEdit,
            QFileDialog QListView,
            QFileDialog QTreeView {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                selection-background-color: #bfdbfe;
                selection-color: #0f172a;
            }
            QFileDialog QPushButton {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 7px;
                padding: 6px 10px;
            }
            """
        else:
            stylesheet = """
            QMainWindow { background: #0f172a; }
            QWidget { color: #e2e8f0; font-size: 12px; }
            QToolBar#mainToolbar { background: #111827; border: 0; spacing: 8px; padding: 6px; }
            QToolBar#mainToolbar QToolButton, QPushButton {
                background: #1f2937; border: 1px solid #334155; border-radius: 7px;
                padding: 6px 10px; color: #e2e8f0;
            }
            QToolBar#mainToolbar QToolButton {
                min-width: 28px;
                padding: 4px 6px;
            }
            QToolBar#mainToolbar QToolButton:hover, QPushButton:hover {
                background: #263447; border-color: #4f74a8;
            }
            QToolBar#mainToolbar QToolButton:pressed, QPushButton:pressed { background: #1a2433; }
            QComboBox {
                background: #111827; border: 1px solid #334155; border-radius: 6px; padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                background: #0b1220; border: 1px solid #334155;
                selection-background-color: #1d4e89; selection-color: #eff6ff;
                outline: 0;
                alternate-background-color: #0b1220;
            }
            QComboBox QAbstractItemView::item {
                border: none;
                min-height: 20px;
                padding: 2px 6px;
                margin: 0;
            }
            QComboBox QAbstractItemView::item:selected {
                border: none;
                background: #1d4e89;
                color: #eff6ff;
            }
            QWidget#sidePanel { background: #111827; border: 1px solid #1f2a3d; border-radius: 10px; }
            QLabel#sectionTitle {
                color: #bfdbfe; font-size: 13px; font-weight: 600; padding: 4px 2px;
            }
            QLabel#toolbarInfo { color: #bfdbfe; font-weight: 600; }
            QListWidget#logList {
                background: #0b1220; border: 1px solid #243244; border-radius: 8px; padding: 4px;
            }
            QListWidget#logList::item { padding: 6px; border-radius: 5px; }
            QListWidget#logList::item:selected { background: #1d4e89; color: #eff6ff; }
            QSlider#timelineSlider::groove:horizontal {
                background: #1f2a3d; height: 8px; border-radius: 4px;
            }
            QSlider#timelineSlider::handle:horizontal {
                background: #60a5fa; width: 16px; margin: -4px 0; border-radius: 8px;
            }
            QStatusBar { background: #111827; border-top: 1px solid #1f2a3d; color: #cbd5e1; }
            QTabWidget::pane {
                border: 1px solid #223246;
                border-radius: 8px;
                top: -1px;
                background: #0b1220;
            }
            QTabBar::tab {
                background: #1f2937;
                color: #94a3b8;
                border: 1px solid #223246;
                border-bottom: none;
                padding: 6px 12px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: #0b1220;
                color: #e2e8f0;
                font-weight: 600;
            }
            QTabBar::tab:hover { color: #dbeafe; }
            QPlainTextEdit#consoleView {
                background: #0b1220;
                border: 1px solid #243244;
                border-radius: 8px;
                color: #e2e8f0;
                font-family: Consolas, 'Liberation Mono', monospace;
                font-size: 12px;
            }
            QFileDialog, QFileDialog QWidget {
                background: #0b1220;
                color: #e2e8f0;
            }
            QFileDialog QLabel {
                color: #cbd5e1;
            }
            QFileDialog QLineEdit,
            QFileDialog QListView,
            QFileDialog QTreeView {
                background: #111827;
                color: #e2e8f0;
                border: 1px solid #334155;
                selection-background-color: #1d4e89;
                selection-color: #eff6ff;
            }
            QFileDialog QPushButton {
                background: #1f2937;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 6px 10px;
            }
            """

        self.setStyleSheet(stylesheet)
        self.plot_widget.set_theme(theme)
        self.accuracy_widget.set_theme(theme)
        self.satellite_widget.set_theme(theme)

    def on_theme_changed(self, theme_text: str) -> None:
        theme = "light" if theme_text.lower() == "light" else "dark"
        self._apply_theme(theme)

    def on_timeline_mode_changed(self, _idx: int) -> None:
        mode_data = self.timeline_mode_box.currentData()
        mode = "aligned" if mode_data == "aligned" else "index"
        self.engine.set_timeline_mode(mode)
        self._console_window_by_log.clear()
        self._console_selection_key = ()
        self._update_accuracy_panel()

    def load_logs(self) -> None:
        file_paths = choose_nmea_files(self)
        if not file_paths:
            return

        self._add_log_paths(file_paths)

    def _add_log_paths(self, file_paths: list[str]) -> None:
        if not file_paths:
            return

        self.parse_progress.clear()
        self.statusBar().showMessage(f"Starting parse for {len(file_paths)} file(s)...")

        for path in file_paths:
            receiver = self._unique_receiver_name(receiver_name_from_path(path))
            thread = NMEAParserThread(file_path=path, receiver_name=receiver, parent=self)
            thread.started_parse.connect(self.on_parse_started)
            thread.progress.connect(self.on_parse_progress)
            thread.parsed.connect(self.on_parse_done)
            thread.failed.connect(self.on_parse_failed)
            thread.finished.connect(lambda r=receiver: self.parse_threads.pop(r, None))
            self.parse_threads[receiver] = thread
            thread.start()

    def _unique_receiver_name(self, base_name: str) -> str:
        if base_name not in self.engine.datasets and base_name not in self.parse_threads:
            return base_name

        suffix = 2
        while True:
            candidate = f"{base_name}_{suffix}"
            if candidate not in self.engine.datasets and candidate not in self.parse_threads:
                return candidate
            suffix += 1

    def remove_selected_logs(self) -> None:
        selected = self.log_list.selectedItems()
        if not selected:
            QMessageBox.information(self, "Remove logs", "Select one or more logs to remove.")
            return

        names_to_remove: list[str] = []
        for item in selected:
            name = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(name, str):
                names_to_remove.append(name)

        for name in names_to_remove:
            thread = self.parse_threads.pop(name, None)
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
                thread.quit()
                thread.wait(100)
            self.log_visibility.pop(name, None)
            self.parse_progress.pop(name, None)
            self.engine.remove_dataset(name)

        self._console_window_by_log.clear()
        self._console_selection_key = ()
        self.map_widget.reset_tracks()
        self._last_map_index = None
        self._update_console_for_index(self.engine.index)

    def clear_logs(self) -> None:
        for name, thread in list(self.parse_threads.items()):
            if thread.isRunning():
                thread.requestInterruption()
                thread.quit()
                thread.wait(100)
            self.parse_threads.pop(name, None)

        self.log_visibility.clear()
        self.parse_progress.clear()
        self._console_window_by_log.clear()
        self._console_selection_key = ()
        self.engine.clear()
        self.map_widget.reset_tracks()
        self._last_map_index = None
        self.statusBar().showMessage("All logs cleared.", 3000)

    def show_log_list_context_menu(self, pos) -> None:
        item = self.log_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.log_list.clearSelection()
            item.setSelected(True)

        menu = QMenu(self)
        remove_selected_action = menu.addAction("Remove Selected")
        clear_all_action = menu.addAction("Clear Logs")

        has_items = self.log_list.count() > 0
        has_selection = len(self.log_list.selectedItems()) > 0
        remove_selected_action.setEnabled(has_selection)
        clear_all_action.setEnabled(has_items)

        chosen = menu.exec(self.log_list.viewport().mapToGlobal(pos))
        if chosen == remove_selected_action:
            self.remove_selected_logs()
        elif chosen == clear_all_action:
            self.clear_logs()

    def on_parse_started(self, receiver: str) -> None:
        self.parse_progress[receiver] = 0
        self._update_parse_status()

    def on_parse_progress(self, receiver: str, progress: int) -> None:
        self.parse_progress[receiver] = progress
        self._update_parse_status()

    def on_parse_done(self, receiver: str, dataset: NMEADataset) -> None:
        self.parse_progress[receiver] = 100
        self.engine.add_dataset(dataset)
        self._update_parse_status()

    def on_parse_failed(self, receiver: str, error_text: str) -> None:
        QMessageBox.critical(self, "Parse error", f"Receiver '{receiver}' failed:\n{error_text}")
        self.parse_progress[receiver] = 100
        self._update_parse_status()

    def _update_parse_status(self) -> None:
        if not self.parse_progress:
            return
        avg = sum(self.parse_progress.values()) / len(self.parse_progress)
        done = sum(1 for p in self.parse_progress.values() if p >= 100)
        total = len(self.parse_progress)
        self.statusBar().showMessage(f"Parsing progress: {avg:.1f}% ({done}/{total} done)")

    def on_datasets_changed(self, datasets: dict[str, NMEADataset]) -> None:
        self._console_window_by_log.clear()
        self._console_selection_key = ()
        self.map_widget.reset_tracks()
        self.map_widget.set_show_dots(self.map_dots_checkbox.isChecked())
        self._last_map_index = None

        self.log_list.blockSignals(True)
        self.log_list.clear()
        for name, ds in datasets.items():
            is_checked = self.log_visibility.get(name, True)
            self.log_visibility[name] = is_checked

            item = QListWidgetItem(f"{name} ({len(ds.points)} points)")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            self.log_list.addItem(item)
        self.log_list.blockSignals(False)

        if self.log_list.count() > 0 and not self.log_list.selectedItems():
            self.log_list.item(0).setSelected(True)

        self.apply_plot_selection()
        current_ref = self.accuracy_widget.current_reference()
        self.accuracy_widget.set_reference_options(datasets.keys(), current=current_ref)

        max_idx = max(self.engine.max_points - 1, 0)
        self.slider.blockSignals(True)
        self.slider.setRange(0, max_idx)
        self.slider.blockSignals(False)
        self._update_console_for_index(self.engine.index)
        self._update_accuracy_panel()
        self._update_satellite_panel(self.engine.index)
        QTimer.singleShot(0, self.plot_widget.reset_all_views)
        self._sync_step_button()

    def on_log_item_changed(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(name, str):
            return
        self._console_window_by_log.clear()
        self._console_selection_key = ()
        self.log_visibility[name] = item.checkState() == Qt.CheckState.Checked
        self.apply_plot_selection()
        self.map_widget.reset_tracks()
        self.map_widget.update_positions(self._selected_positions_at(self.engine.index))
        self._last_map_index = self.engine.index
        self._update_console_for_index(self.engine.index)
        self._update_accuracy_panel()
        QTimer.singleShot(0, self.plot_widget.reset_all_views)

    def on_log_selection_changed(self) -> None:
        self._console_window_by_log.clear()
        self._console_selection_key = ()
        self._update_console_for_index(self.engine.index)
        self._update_satellite_panel(self.engine.index)

    def on_tab_changed(self, current_idx: int) -> None:
        if current_idx != self._console_tab_index:
            return
        if self._pending_console_index is not None:
            self._update_console_for_index(self._pending_console_index)
            self._pending_console_index = None
        else:
            self._update_console_for_index(self.engine.index)

    def apply_plot_selection(self) -> None:
        selected = {
            name: ds
            for name, ds in self.engine.datasets.items()
            if self.log_visibility.get(name, True)
        }
        self.plot_widget.update_datasets(selected)
        QTimer.singleShot(0, self.plot_widget.reset_all_views)

    def on_playback_updated(self, index: int, max_index: int, time_text: str, positions: object) -> None:
        self.index_label.setText(f"Index: {index}/{max_index}")
        self.time_label.setText(f"Time: {time_text}")

        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)

        self.plot_widget.set_playback_time(self._plot_cursor_time_at(index))
        self._sync_step_button()
        self._update_satellite_panel(index)
        if self.tabs.currentIndex() == self._console_tab_index:
            self._update_console_for_index(index)
            self._pending_console_index = None
        else:
            self._pending_console_index = index
        if isinstance(positions, dict):
            if self._last_map_index is not None and index < self._last_map_index:
                self.map_widget.reset_tracks()
            filtered_positions = {
                name: payload
                for name, payload in positions.items()
                if self.log_visibility.get(name, True)
            }
            self.map_widget.update_positions(filtered_positions)
            self._last_map_index = index

    def on_map_dots_toggled(self, checked: bool) -> None:
        self.map_widget.set_show_dots(checked)
        # Rebuild track from current playback point onward.
        self.map_widget.reset_tracks()
        self.map_widget.update_positions(self._selected_positions_at(self.engine.index))
        self._last_map_index = self.engine.index

    def on_map_follow_toggled(self, checked: bool) -> None:
        self.map_widget.set_follow_playback(checked)

    def on_map_fit_visible(self) -> None:
        self.map_widget.fit_visible()

    def on_reference_changed(self, _name: str) -> None:
        self._update_accuracy_panel()

    def _satellite_receivers_for_view(self) -> list[str]:
        selected_names: list[str] = []
        for item in self.log_list.selectedItems():
            name = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(name, str) and name in self.engine.datasets:
                selected_names.append(name)

        if len(selected_names) >= 2:
            return selected_names[:2]
        if len(selected_names) == 1:
            return selected_names

        visible_names = [
            name for name in self.engine.datasets.keys() if self.log_visibility.get(name, True)
        ]
        if len(visible_names) >= 2:
            return visible_names[:2]
        if len(visible_names) == 1:
            return visible_names

        all_names = list(self.engine.datasets.keys())
        return all_names[:1]

    def _update_satellite_panel(self, index: int) -> None:
        receivers = self._satellite_receivers_for_view()
        if not receivers:
            self.satellite_widget.clear_view()
            return

        entries: list[tuple[str, NMEAPoint | None]] = []
        for receiver in receivers[:2]:
            dataset = self.engine.datasets.get(receiver)
            if dataset is None:
                continue
            _, point = self.engine.resolve_dataset_point(dataset, index)
            entries.append((receiver, point))

        self.satellite_widget.set_view_data(entries)

    def _plot_cursor_time_at(self, index: int):
        selected_datasets = [
            ds for name, ds in self.engine.datasets.items() if self.log_visibility.get(name, True)
        ]
        if not selected_datasets:
            selected_datasets = list(self.engine.datasets.values())

        for ds in selected_datasets:
            _, point = self.engine.resolve_dataset_point(ds, index)
            if point is not None and point.timestamp is not None:
                return point.timestamp

        return self.engine.playback_time_at(index)

    def _selected_positions_at(self, index: int) -> dict[str, dict[str, float | str | None]]:
        positions: dict[str, dict[str, float | str | None]] = {}
        for name, ds in self.engine.datasets.items():
            if not self.log_visibility.get(name, True):
                continue
            _, point = self.engine.resolve_dataset_point(ds, index)
            if not point:
                continue
            positions[name] = {
                "lat": point.latitude,
                "lon": point.longitude,
                "time": point.timestamp.isoformat(sep=" ") if point.timestamp else None,
            }
        return positions

    def _update_console_for_index(self, index: int) -> None:
        font_metrics = self.console_view.fontMetrics()
        line_height = max(1, font_metrics.lineSpacing())
        viewport_height = max(1, self.console_view.viewport().height())
        visible_line_count = max(12, viewport_height // line_height)
        # Reserve room for section headers so the data window approximates what is visible.
        data_window_size = max(12, visible_line_count - 8)
        anchor_offset = max(1, (data_window_size // 4) - 6)
        lines: list[str] = []
        timeline_time = self.engine.playback_time_at(index)
        timeline_time_text = timeline_time.isoformat(sep=" ") if timeline_time else "N/A"
        lines.append(f"Timeline Index: {index}")
        lines.append(f"Timeline Time: {timeline_time_text}")
        lines.append(f"Visible data window: {data_window_size} lines per selected log")
        lines.append("=" * 72)

        if not self.engine.datasets:
            lines.append("No logs loaded.")
            self.console_view.setPlainText("\n".join(lines))
            return

        selected_names: list[str] = []
        for item in self.log_list.selectedItems():
            name = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(name, str):
                selected_names.append(name)

        selection_key = tuple(selected_names)
        if selection_key != self._console_selection_key:
            self._console_window_by_log.clear()
            self._console_selection_key = selection_key

        if not selected_names:
            lines.append("Select a log in 'Loaded Logs' to view console details.")
            self.console_view.setPlainText("\n".join(lines))
            return

        for name in selected_names:
            ds = self.engine.datasets.get(name)
            if ds is None:
                continue
            total = len(ds.points)
            lines.append(f"[{name}] file={ds.source_path}")

            resolved_idx, point_at_cursor = self.engine.resolve_dataset_point(ds, index)
            if resolved_idx is None or point_at_cursor is None:
                lines.append("  No data available at this timeline point.")
                lines.append("")
                continue

            if total == 0:
                lines.append("  No parsed points available.")
                lines.append("")
                continue

            current_idx = resolved_idx
            point_time = point_at_cursor.timestamp.isoformat(sep=" ") if point_at_cursor.timestamp else "N/A"
            lines.append(f"  Resolved sample index: {current_idx}")
            lines.append(f"  Resolved sample time: {point_time}")
            existing_window = self._console_window_by_log.get(name)
            if existing_window is None:
                start_idx = max(0, current_idx - anchor_offset)
                end_idx = min(total - 1, start_idx + data_window_size - 1)
            else:
                start_idx, end_idx = existing_window
                if current_idx < start_idx or current_idx > end_idx:
                    start_idx = max(0, current_idx - anchor_offset)
                    end_idx = min(total - 1, start_idx + data_window_size - 1)

            # Keep window size stable near file end.
            window_len = end_idx - start_idx + 1
            if window_len < data_window_size and total >= data_window_size:
                shift = data_window_size - window_len
                start_idx = max(0, start_idx - shift)
                end_idx = min(total - 1, start_idx + data_window_size - 1)

            self._console_window_by_log[name] = (start_idx, end_idx)

            lines.append(
                f"  Showing lines {start_idx}..{end_idx} of {total - 1} (window={data_window_size}, anchor~25%-6)"
            )

            for point_idx in range(start_idx, end_idx + 1):
                point = ds.points[point_idx]
                marker = "->" if point_idx == current_idx else "  "
                t_str = point.timestamp.isoformat(sep=" ") if point.timestamp else "N/A"
                raw = point.raw_sentence if point.raw_sentence else "<none>"
                lines.append(f"{marker} [{point_idx:06d}] {t_str} | {raw}")

            lines.append("")

        self.console_view.setPlainText("\n".join(lines))

    def toggle_map_popout(self) -> None:
        if self._map_is_popped_out:
            self.dock_map_back()
        else:
            self.pop_out_map()

    def pop_out_map(self) -> None:
        if self._map_is_popped_out:
            return

        self.map_host_layout.removeWidget(self.map_widget)
        self.map_popout_layout.addWidget(self.map_widget)
        self.map_popout_window.show()
        self.map_popout_window.raise_()
        self.map_popout_window.activateWindow()
        self._map_is_popped_out = True
        self.map_tab_popout_button.setText("Dock Back")

    def dock_map_back(self) -> None:
        if not self._map_is_popped_out:
            return

        self.map_popout_layout.removeWidget(self.map_widget)
        self.map_host_layout.addWidget(self.map_widget)
        self._map_is_popped_out = False
        self.map_tab_popout_button.setText("Pop Out")
        self.map_popout_window.hide()

    def eventFilter(self, watched, event):
        if (
            watched is self.map_popout_window
            and event.type() == QEvent.Type.Close
            and self._map_is_popped_out
        ):
            self.dock_map_back()
            return True
        return super().eventFilter(watched, event)

    def on_playback_state_changed(self, is_playing: bool) -> None:
        self._update_playback_buttons(is_playing)

    def _update_playback_buttons(self, is_playing: bool) -> None:
        self.play_button.setEnabled(not is_playing)
        self.pause_button.setEnabled(is_playing)
        self.stop_button.setEnabled(True)
        self._sync_step_button()

    def _sync_step_button(self) -> None:
        self.step_button.setEnabled(not self.engine.timer.isActive())

    def on_play_clicked(self) -> None:
        self._sync_step_button()
        self.engine.start()

    def on_pause_clicked(self) -> None:
        self.engine.pause()
        self._sync_step_button()

    def on_stop_clicked(self) -> None:
        self.engine.stop()
        self._sync_step_button()

    def on_step_clicked(self) -> None:
        self.engine.step_forward()
        self._sync_step_button()

    def change_speed(self, speed_text: str) -> None:
        speed_map = {
            "0.5x": 500,
            "1x": 250,
            "2x": 120,
            "4x": 60,
        }
        self.engine.set_interval(speed_map.get(speed_text, 250))

    def export_summary(self) -> None:
        datasets = list(self.engine.datasets.values())
        if not datasets:
            QMessageBox.information(self, "Export", "Nothing to export. Load logs first.")
            return

        bundle_path = choose_report_bundle_path(self)
        if not bundle_path:
            return

        reference = self.accuracy_widget.current_reference()
        with tempfile.TemporaryDirectory(prefix="gnss_plot_images_") as tmpdir:
            selected_datasets = {
                name: ds
                for name, ds in self.engine.datasets.items()
                if self.log_visibility.get(name, True)
            }
            if not selected_datasets:
                selected_datasets = dict(self.engine.datasets)

            plot_image_paths: list[tuple[str, str]] = []
            plot_image_paths.extend(
                self.plot_widget.export_metric_gallery(selected_datasets, f"{tmpdir}/combined", "combined")
            )

            for receiver_name, dataset in selected_datasets.items():
                plot_image_paths.extend(
                    self.plot_widget.export_metric_gallery(
                        {receiver_name: dataset},
                        f"{tmpdir}/{receiver_name}",
                        receiver_name,
                    )
                )

            write_report_bundle(
                bundle_path,
                datasets,
                self._last_accuracy_rows,
                reference,
                self.engine.timeline_mode,
                plot_image_paths=plot_image_paths,
            )
        self.statusBar().showMessage(f"Report bundle exported: {Path(bundle_path).name}", 4000)

    def _update_accuracy_panel(self) -> None:
        reference = self.accuracy_widget.current_reference()
        if not reference or reference not in self.engine.datasets:
            self._last_accuracy_rows = []
            self.accuracy_widget.set_accuracy_data({}, [])
            return

        visible_names = [
            name for name in self.engine.datasets.keys() if self.log_visibility.get(name, True)
        ]
        if reference not in visible_names:
            visible_names.insert(0, reference)

        reference_dataset = self.engine.datasets[reference]
        series_by_receiver: dict[str, tuple[list[float], list[float]]] = {}
        rows: list[dict[str, float | int | str]] = []

        for name in visible_names:
            if name == reference:
                continue

            dataset = self.engine.datasets.get(name)
            if dataset is None:
                continue

            x_vals: list[float] = []
            y_vals: list[float] = []

            for idx in range(self.engine.max_points):
                _, ref_point = self.engine.resolve_dataset_point(reference_dataset, idx)
                _, point = self.engine.resolve_dataset_point(dataset, idx)
                ts = self.engine.playback_time_at(idx)
                if ts is None or ref_point is None or point is None:
                    continue
                if (
                    ref_point.latitude is None
                    or ref_point.longitude is None
                    or point.latitude is None
                    or point.longitude is None
                ):
                    continue

                dist_m = self._haversine_m(
                    ref_point.latitude,
                    ref_point.longitude,
                    point.latitude,
                    point.longitude,
                )
                x_vals.append(ts.timestamp())
                y_vals.append(dist_m)

            if not y_vals:
                continue

            y_sorted = sorted(y_vals)
            p95_idx = min(len(y_sorted) - 1, max(0, int(0.95 * (len(y_sorted) - 1))))

            series_by_receiver[name] = (x_vals, y_vals)
            rows.append(
                {
                    "reference": reference,
                    "receiver": name,
                    "samples": len(y_vals),
                    "mean_m": round(sum(y_vals) / len(y_vals), 3),
                    "median_m": round(median(y_vals), 3),
                    "p95_m": round(y_sorted[p95_idx], 3),
                    "max_m": round(max(y_vals), 3),
                }
            )

        rows.sort(key=lambda r: float(r["mean_m"]))
        self._last_accuracy_rows = rows
        self.accuracy_widget.set_accuracy_data(series_by_receiver, rows)

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        # Great-circle distance on Earth in meters.
        earth_radius_m = 6371000.0
        phi1 = radians(lat1)
        phi2 = radians(lat2)
        d_phi = radians(lat2 - lat1)
        d_lambda = radians(lon2 - lon1)

        a = sin(d_phi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2.0) ** 2
        c = 2.0 * asin(min(1.0, sqrt(a)))
        return earth_radius_m * c

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return

        for url in mime.urls():
            if not url.isLocalFile():
                continue
            file_path = Path(url.toLocalFile())
            if file_path.suffix.lower() in {".nmea", ".log", ".txt"}:
                event.acceptProposedAction()
                return

        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return

        paths: list[str] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            file_path = Path(url.toLocalFile())
            if file_path.suffix.lower() in {".nmea", ".log", ".txt"}:
                paths.append(str(file_path))

        if not paths:
            event.ignore()
            return

        self._add_log_paths(paths)
        self.statusBar().showMessage(f"Dropped {len(paths)} file(s). Parsing started...", 4000)
        event.acceptProposedAction()


def run_app() -> None:
    # Use software rendering path to avoid EGL/DRM failures on systems without
    # proper GPU/driver access.
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-gpu-compositing")
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
