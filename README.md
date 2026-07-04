# GNSS NMEA Comparator (PyQt)

A modular desktop tool to compare GNSS receiver performance from NMEA logs.

## Features

- Load multiple NMEA log files (one per receiver).
- Parse large files in background threads (`QThread`) to keep UI responsive.
- Compare metrics using dynamic `pyqtgraph` plots:
  - 4 simultaneous plot panels (2x2)
  - Metric selection per panel (CN0, latitude, longitude, HDOP, VDOP, PDOP, satellites, altitude, speed)
- Playback timeline across loaded logs.
- OpenStreetMap pop-out window (`QWebEngineView` + Leaflet) with live receiver marker updates.
- Optional CSV summary export.

## Project Structure

```text
app/
  core/
    engine.py           # Playback and dataset orchestration
    models.py           # NMEA data models
  io/
    file_handler.py     # File dialogs and summary export helpers
  parser/
    nmea_parser.py      # Raw NMEA parsing logic
    parser_thread.py    # QThread wrapper for parser
  ui/
    main_window.py      # Main application window
    plot_widget.py      # PyQtGraph multi-metric plots
    map_widget.py       # OpenStreetMap QWebEngineView widget
main.py
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run:

```bash
python main.py
```

## Notes

- The map widget uses Leaflet with OpenStreetMap tiles in an embedded HTML page.
- Parser currently extracts common fields from GGA and RMC sentences.
