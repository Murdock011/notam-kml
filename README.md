# notam-kml

Downloads the latest South African CAA NOTAM summary PDF, parses every NOTAM,
and generates a KML file for viewing in Google Earth / Google Maps.

Each NOTAM becomes a numbered folder containing:
- A closed polygon (when the `E)` text lists 3+ coordinate points) plus a pin at its centroid
- Otherwise a pin at the single point or `Q)`-line centre, with a radius circle if a radius is given
- Colour coding by upper limit height from `G)`: red below 1000 ft, blue at or above (blue if unknown)

## Usage

```bash
pip install -r requirements.txt
python notam_to_kml.py
```

By default this filters to NOTAMs within 50 NM of FASD (Saldanha/Vredenburg) and
writes `notams.kml`. Options:

```bash
python notam_to_kml.py --icao FACT --radius 100 --output cape_town.kml
python notam_to_kml.py --no-filter   # include every NOTAM in the PDF
```

Airport ICAO codes available for `--icao` are listed in
[airports.csv](airports.csv) (`icao,lat,lon,name`). Add a row there to support
a new filter centre — no code changes needed.

Every run also writes `docs/notams.geojson` — an **unfiltered** GeoJSON dump of
every parsed NOTAM, used by the web map below (pass `--no-geojson` to skip it,
or `--geojson-output` to change the path).

## Web map

[docs/index.html](docs/index.html) is a static Leaflet page that reads
`docs/notams.geojson` and `docs/airports.csv` and lets you pick a centre
ICAO + radius in the browser — filtering happens client-side, so it's not
limited to whatever `--icao`/`--radius` the last CI run used. Same red/blue
height colour coding as the KML.

To serve it for free via GitHub Pages: repo **Settings → Pages → Source**,
select "Deploy from a branch", branch `main`, folder `/docs`. It'll be live at
`https://<user>.github.io/<repo>/`.

To preview locally:

```bash
cd docs && python3 -m http.server 8000
# open http://localhost:8000
```

## Automation

[.github/workflows/daily.yml](.github/workflows/daily.yml) runs the script daily at
06:00 UTC via GitHub Actions, uploads `notams.kml` as a build artifact
(7-day retention), and commits the refreshed `docs/notams.geojson` +
`docs/airports.csv` back to the repo so the web map stays current. It can
also be triggered manually from the Actions tab.
