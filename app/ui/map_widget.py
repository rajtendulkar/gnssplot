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
        self._follow_playback = True
        self._pending_full_paths: list[dict[str, list[dict[str, float | str | None]]]] = []
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
              let arrowMarkers = {};
              let previousPositions = {};
              let fullPolylines = {};
              let dotLayers = {};
              let baseLayers = {};
              let currentBaseLayer = null;

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

                baseLayers.street = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                  maxZoom: 19,
                  attribution: '&copy; OpenStreetMap contributors'
                });

                baseLayers.satellite = L.tileLayer(
                  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                  {
                    maxZoom: 19,
                    attribution: 'Tiles &copy; Esri'
                  }
                );

                baseLayers.topographic = L.tileLayer(
                  'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
                  {
                    maxZoom: 17,
                    attribution: 'Map data: &copy; OpenStreetMap contributors, SRTM | Map style: &copy; OpenTopoMap'
                  }
                );

                setBaseLayer('street');
              }

              function setBaseLayer(viewName) {
                if (!map || !baseLayers[viewName]) return;
                if (currentBaseLayer) {
                  map.removeLayer(currentBaseLayer);
                }
                currentBaseLayer = baseLayers[viewName];
                currentBaseLayer.addTo(map);
              }

              function clearMapData() {
                Object.values(arrowMarkers).forEach((m) => map.removeLayer(m));
                Object.values(fullPolylines).forEach((l) => map.removeLayer(l));
                Object.values(dotLayers).forEach((g) => map.removeLayer(g));
                arrowMarkers = {};
                previousPositions = {};
                fullPolylines = {};
                dotLayers = {};
              }

              function buildArrowIcon(color, bearingDeg) {
                // The glyph points to the right by default; subtract 90 deg so 0 deg means north.
                const angle = Number.isFinite(bearingDeg) ? (bearingDeg - 90.0) : -90.0;
                const html = `<div style="transform: rotate(${angle}deg); color:${color}; font-size: 18px; line-height: 18px; text-shadow: 0 0 2px rgba(0,0,0,0.8);">➤</div>`;
                return L.divIcon({
                  className: 'playback-arrow-icon',
                  html: html,
                  iconSize: [20, 20],
                  iconAnchor: [10, 10]
                });
              }

              function bearingDegrees(lat1, lng1, lat2, lng2) {
                const toRad = (v) => v * Math.PI / 180.0;
                const toDeg = (v) => v * 180.0 / Math.PI;

                const phi1 = toRad(lat1);
                const phi2 = toRad(lat2);
                const dLon = toRad(lng2 - lng1);

                const y = Math.sin(dLon) * Math.cos(phi2);
                const x = Math.cos(phi1) * Math.sin(phi2) -
                          Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLon);
                let brng = toDeg(Math.atan2(y, x));
                brng = (brng + 360.0) % 360.0;
                return brng;
              }

              function setFullPaths(pathsByReceiver, showDots) {
                Object.values(fullPolylines).forEach((l) => map.removeLayer(l));
                Object.values(dotLayers).forEach((g) => map.removeLayer(g));
                fullPolylines = {};
                dotLayers = {};

                Object.entries(pathsByReceiver || {}).forEach(([receiver, points]) => {
                  if (!Array.isArray(points) || points.length === 0) return;

                  const color = colorForReceiver(receiver);
                  const latlngs = [];

                  points.forEach((p) => {
                    const lat = p.lat;
                    const lng = p.lon;
                    if (lat === null || lng === null || lat === undefined || lng === undefined) return;
                    latlngs.push([lat, lng]);
                  });

                  if (latlngs.length === 0) return;

                  fullPolylines[receiver] = L.polyline(latlngs, {
                    color: color,
                    weight: 3,
                    opacity: 0.85,
                  }).addTo(map);

                  if (showDots) {
                    const group = L.layerGroup().addTo(map);
                    latlngs.forEach((latlng) => {
                      L.circleMarker(latlng, {
                        radius: 3,
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.8,
                        weight: 1,
                      }).addTo(group);
                    });
                    dotLayers[receiver] = group;
                  }
                });
              }

              function upsertReceiverMarker(receiver, lat, lng, timeText, forceAutoZoom, followPlayback, headingOverride) {
                if (lat === null || lng === null) return;

                const position = [lat, lng];
                const tooltip = `${receiver}<br/>${timeText || ''}<br/>${lat.toFixed(6)}, ${lng.toFixed(6)}`;
                const color = colorForReceiver(receiver);
                const prev = previousPositions[receiver];
                let bearing = 0;
                if (Number.isFinite(headingOverride)) {
                  bearing = headingOverride;
                } else if (prev) {
                  bearing = bearingDegrees(prev.lat, prev.lng, lat, lng);
                }
                previousPositions[receiver] = { lat: lat, lng: lng };

                if (!arrowMarkers[receiver]) {
                  arrowMarkers[receiver] = L.marker(position, {
                    icon: buildArrowIcon(color, bearing),
                  }).addTo(map);
                } else {
                  arrowMarkers[receiver].setLatLng(position);
                  arrowMarkers[receiver].setIcon(buildArrowIcon(color, bearing));
                }

                arrowMarkers[receiver].bindPopup(tooltip);
                arrowMarkers[receiver].bindTooltip(receiver, { permanent: false });

                if (forceAutoZoom) {
                  map.setView(position, 16);
                } else if (followPlayback) {
                  map.panTo(position);
                }
              }

              function fitAllData() {
                if (!map) return;

                let bounds = null;

                Object.values(fullPolylines).forEach((line) => {
                  const lineBounds = line.getBounds();
                  if (!lineBounds.isValid()) return;
                  if (bounds === null) {
                    bounds = lineBounds;
                  } else {
                    bounds.extend(lineBounds);
                  }
                });

                Object.values(arrowMarkers).forEach((marker) => {
                  const latlng = marker.getLatLng();
                  if (bounds === null) {
                    bounds = L.latLngBounds([latlng, latlng]);
                  } else {
                    bounds.extend(latlng);
                  }
                });

                if (bounds && bounds.isValid()) {
                  map.fitBounds(bounds.pad(0.2));
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

        if self._pending_full_paths:
          for full_paths in self._pending_full_paths:
            self._apply_full_paths(full_paths)
          self._pending_full_paths.clear()

        if self._pending_positions:
            for positions in self._pending_positions:
                self._apply_positions(positions)
            self._pending_positions.clear()

    def set_full_paths(self, paths_by_receiver: dict[str, list[dict[str, float | str | None]]]) -> None:
        if not self._loaded:
            self._pending_full_paths.append(paths_by_receiver)
            return
        self._apply_full_paths(paths_by_receiver)

    def update_positions(self, positions: dict[str, dict[str, float | str | None]]) -> None:
        if not self._loaded:
            self._pending_positions.append(positions)
            return
        self._apply_positions(positions)

    def reset_auto_zoom(self) -> None:
        self._force_auto_zoom = True

    def set_show_dots(self, enabled: bool) -> None:
        self._show_dots = enabled

    def set_follow_playback(self, enabled: bool) -> None:
        self._follow_playback = enabled

    def fit_visible(self) -> None:
        self._run_js("fitAllData();")

    def set_map_view(self, view_name: str) -> None:
        safe_view = view_name if view_name in {"street", "satellite", "topographic"} else "street"
        self._run_js(f"setBaseLayer({json.dumps(safe_view)});")

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
            heading = payload.get("heading")
            if lat is None or lon is None:
                continue

            do_auto_zoom = self._force_auto_zoom and not auto_zoom_applied
            script = "upsertReceiverMarker(%s, %s, %s, %s, %s, %s, %s);" % (
                json.dumps(receiver),
                float(lat),
                float(lon),
                json.dumps(time_text),
                "true" if do_auto_zoom else "false",
                "true" if self._follow_playback else "false",
              json.dumps(float(heading)) if isinstance(heading, (float, int)) else "null",
            )
            self._run_js(script)
            if do_auto_zoom:
                auto_zoom_applied = True

        if auto_zoom_applied:
            self._force_auto_zoom = False

    def _apply_full_paths(self, paths_by_receiver: dict[str, list[dict[str, float | str | None]]]) -> None:
        script = "setFullPaths(%s, %s);" % (
            json.dumps(paths_by_receiver),
            "true" if self._show_dots else "false",
        )
        self._run_js(script)
