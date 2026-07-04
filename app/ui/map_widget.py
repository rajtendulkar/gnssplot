from __future__ import annotations

import json

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class MapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.view = QWebEngineView(self)
        self._loaded = False
        self._force_auto_zoom = True
        self._show_dots = False
        self._pending_positions: list[dict[str, dict[str, float | str | None]]] = []
        self._pending_scripts: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self.view.loadFinished.connect(self._on_load_finished)
        self._load_page()

    def _load_page(self) -> None:
        html = """
        <!DOCTYPE html>
        <html>
          <head>
            <meta charset=\"utf-8\" />
            <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
            <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\" crossorigin=\"\" />
            <style>
              html, body, #map { height: 100%; margin: 0; padding: 0; }
              body { font-family: sans-serif; }
            </style>
            <script>
              let map;
              let markers = {};
              let polylines = {};
              let dotLayers = {};

              const lineColors = [
                '#2563eb', '#dc2626', '#16a34a', '#ea580c',
                '#9333ea', '#0891b2', '#ca8a04', '#475569'
              ];

              function colorForReceiver(receiver) {
                let hash = 0;
                for (let i = 0; i < receiver.length; i++) {
                  hash = ((hash << 5) - hash) + receiver.charCodeAt(i);
                  hash |= 0;
                }
                return lineColors[Math.abs(hash) % lineColors.length];
              }

              function initMap() {
                map = L.map('map', { zoomControl: true }).setView([0, 0], 2);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                  maxZoom: 19,
                  attribution: '&copy; OpenStreetMap contributors'
                }).addTo(map);
              }

              function clearMapData() {
                Object.values(markers).forEach((m) => map.removeLayer(m));
                Object.values(polylines).forEach((l) => map.removeLayer(l));
                Object.values(dotLayers).forEach((g) => map.removeLayer(g));
                markers = {};
                polylines = {};
                dotLayers = {};
              }

              function upsertReceiverMarker(receiver, lat, lng, timeText, forceAutoZoom, showDots) {
                if (lat === null || lng === null) return;

                const position = [lat, lng];
                const tooltip = `${receiver}<br/>${timeText || ''}<br/>${lat.toFixed(6)}, ${lng.toFixed(6)}`;
                const color = colorForReceiver(receiver);

                if (!markers[receiver]) {
                  markers[receiver] = L.marker(position).addTo(map);
                } else {
                  markers[receiver].setLatLng(position);
                }

                if (!polylines[receiver]) {
                  polylines[receiver] = L.polyline([], {
                    color: color,
                    weight: 3,
                    opacity: 0.85,
                  }).addTo(map);
                }
                polylines[receiver].addLatLng(position);

                if (!dotLayers[receiver]) {
                  dotLayers[receiver] = L.layerGroup().addTo(map);
                }
                if (showDots) {
                  L.circleMarker(position, {
                    radius: 3,
                    color: color,
                    fillColor: color,
                    fillOpacity: 0.8,
                    weight: 1,
                  }).addTo(dotLayers[receiver]);
                }

                markers[receiver].bindPopup(tooltip);
                markers[receiver].bindTooltip(receiver, { permanent: false });

                if (forceAutoZoom) {
                  map.setView(position, 16);
                } else {
                  map.panTo(position);
                }
              }
            </script>
          </head>
          <body onload=\"initMap()\">
            <div id=\"map\"></div>
            <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\" integrity=\"sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=\" crossorigin=\"\"></script>
          </body>
        </html>
        """

        self.view.setHtml(html)

    def _on_load_finished(self, ok: bool) -> None:
        self._loaded = ok
        if not ok:
            return

        if self._pending_scripts:
            for script in self._pending_scripts:
                self.view.page().runJavaScript(script)
            self._pending_scripts.clear()

        if self._pending_positions:
            for positions in self._pending_positions:
                self._apply_positions(positions)
            self._pending_positions.clear()

    def update_positions(self, positions: dict[str, dict[str, float | str | None]]) -> None:
        if not self._loaded:
            self._pending_positions.append(positions)
            return
        self._apply_positions(positions)

    def reset_auto_zoom(self) -> None:
        self._force_auto_zoom = True

    def set_show_dots(self, enabled: bool) -> None:
        self._show_dots = enabled

    def reset_tracks(self) -> None:
        self._force_auto_zoom = True
        self._run_js("clearMapData();")

    def _run_js(self, script: str) -> None:
        if not self._loaded:
            self._pending_scripts.append(script)
            return
        self.view.page().runJavaScript(script)

    def _apply_positions(self, positions: dict[str, dict[str, float | str | None]]) -> None:
        auto_zoom_applied = False
        for receiver, payload in positions.items():
            lat = payload.get("lat")
            lon = payload.get("lon")
            time_text = payload.get("time")
            if lat is None or lon is None:
                continue

            do_auto_zoom = self._force_auto_zoom and not auto_zoom_applied
            script = "upsertReceiverMarker(%s, %s, %s, %s, %s, %s);" % (
                json.dumps(receiver),
                float(lat),
                float(lon),
                json.dumps(time_text),
                "true" if do_auto_zoom else "false",
                "true" if self._show_dots else "false",
            )
            self._run_js(script)
            if do_auto_zoom:
                auto_zoom_applied = True

        if auto_zoom_applied:
            self._force_auto_zoom = False
