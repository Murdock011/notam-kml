# notam-kml

Downloads the latest South African CAA NOTAM summary PDF, parses every NOTAM,
and generates a KML file (for Google Earth / Google Maps) plus a GeoJSON feed
for the live web map.

Each NOTAM becomes a numbered folder containing:
- A closed polygon (when the `E)` text lists 3+ coordinate points) plus a pin at its centroid
- Otherwise a pin at the single point or `Q)`-line centre, with a radius circle if a radius is given
- Colour coding by upper limit height from `G)`: red below 1000 ft, blue at or above (blue if unknown)

## Usage

```bash
pip install -r requirements.txt
python notam_to_kml.py
```

By default this filters to NOTAMs at FALW (Langebaanweg), 0 NM radius, and
writes `notams.kml`. Options:

```bash
python notam_to_kml.py --icao FACT --radius 100 --output cape_town.kml
python notam_to_kml.py --no-filter   # include every NOTAM in the PDF
```

Airport ICAO codes available for `--icao` are listed in
[airports.csv](airports.csv) (`icao,lat,lon,name`) — all ~308 active South
African aerodromes, sourced from [OurAirports](https://ourairports.com/). 


## Web map

[docs/index.html](docs/index.html) is a static Leaflet page that reads
`docs/notams.geojson` and `docs/airports.csv`. Filtering happens entirely
client-side, so it isn't limited to whatever `--icao`/`--radius` the last CI
run used.

- **Centre(s) / route** — type one or more ICAO codes (comma/space separated,
  autocompleted from the full airport list). One code filters around that
  airport; two or more are treated as an ordered route (e.g. `FACT, FALE,
  FALA`) and NOTAMs are shown if they fall within the radius of *any* leg's
  great-circle corridor, not just near an individual airport. A dashed route
  line and green radius circles are drawn for reference.
- **Numbers / Plain toggle** — switches map markers between numbered badges
  (matching the table below) and plain colour dots, for when the numbering
  just adds clutter.
- **Show Table** — opens an on-page results table (`#`, Location, Number,
  Start/End Date UTC, Condition),clicking a row pans/zooms the map to that NOTAM and
  opens its popup.
- **Download KML** — builds a KML client-side from exactly what's currently
  visible (same filter/route/sort as the table) and downloads it, matching
  the structure `notam_to_kml.py` produces server-side.
- **Data-currency banner** — shows when the underlying CAA summary was
  compiled (`pdf_compiled_at`) and how many hours old that is, with a link to
  the source PDF, so you know if the data might be stale.

 It'll be live at
`https://<user>.github.io/<repo>/`.

To preview locally:

```bash
cd docs && python3 -m http.server 8000
# open http://localhost:8000
```

## Automation

[.github/workflows/daily.yml](.github/workflows/daily.yml) runs the script daily at
06:00 UTC via GitHub Actions, uploads `notams.kml` as a build artifact
(3-day retention), and commits the refreshed `docs/notams.geojson` +
`docs/airports.csv` back to the repo so the web map stays current. It can
also be triggered manually from the Actions tab.
