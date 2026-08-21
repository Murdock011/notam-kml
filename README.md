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

Airport ICAO codes available for `--icao` are listed in the `AIRPORTS` dict in
[notam_to_kml.py](notam_to_kml.py); add more entries there as needed.

## Automation

[.github/workflows/daily.yml](.github/workflows/daily.yml) runs the script daily at
06:00 UTC via GitHub Actions and uploads `notams.kml` as a build artifact
(7-day retention). It can also be triggered manually from the Actions tab.
