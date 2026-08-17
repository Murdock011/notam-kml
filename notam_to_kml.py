#!/usr/bin/env python3
"""
NOTAM → KML generator for South Africa
- Downloads the latest CAA SUMMARY.pdf
- Parses all NOTAMs
- Generates a clean KML with:
  - One index number per NOTAM
  - Closed polygons + centre pin at centroid
  - Circle only when no polygon and radius > 0
  - Colour by G) height (<1000 ft = red, ≥1000 ft = blue)
"""
import re
import math
import urllib.request
from pathlib import Path
from typing import List, Tuple, Optional, Dict
try:
    from pypdf import PdfReader
except ImportError:
    print("Please install pypdf: pip install pypdf")
    raise
try:
    import simplekml
except ImportError:
    print("Please install simplekml: pip install simplekml")
    raise
# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
PDF_URL = "https://caasanwebsitestorage.blob.core.windows.net/notam-summaries-and-pib/SUMMARY.pdf"
PDF_FILE = "notam.pdf"
OUTPUT_KML = "notams.kml"

# Distance filter (set FILTER_ICAO = None to disable and include all NOTAMs)
# Example: 50 NM around FASD (Saldanha / Vredenburg)
FILTER_ICAO = "FASD"          # ICAO code, or None for no filter
FILTER_RADIUS_NM = 50.0       # radius in nautical miles

# Built-in SA aerodrome positions (lat, lon). Extend or load airports.csv as needed.
AIRPORTS = {
    "FASD": (-32.964066, 17.969331),   # Saldanha / Vredenburg
    "FALW": (-32.968900, 18.160300),   # Langebaanweg
    "FACT": (-33.971500, 18.602100),   # Cape Town Intl
    "FAJS": (-26.139200, 28.246000),   # OR Tambo (legacy code sometimes seen)
    "FAOR": (-26.139200, 28.246000),   # OR Tambo
    "FALA": (-25.938500, 27.925800),   # Lanseria
    "FAGG": (-34.005600, 22.375800),   # George
    "FAPE": (-33.984900, 25.617300),   # Port Elizabeth / Gqeberha
    "FADN": (-29.970300, 30.950500),   # Durban / King Shaka area (Virginia nearby)
    "FALE": (-29.614400, 31.119700),   # King Shaka
    "FAUP": (-28.400600, 21.260300),   # Upington
    "FABL": (-29.092700, 26.302400),   # Bloemfontein
    "FAPP": (-23.845300, 29.458700),   # Polokwane
    "FAKM": (-28.805000, 24.765000),   # Kimberley
}
# ------------------------------------------------------------------
# Coordinate parsing
# ------------------------------------------------------------------
def dms_to_decimal(coord: str) -> Optional[float]:
    coord = coord.strip().upper().replace(" ", "")
    if not coord:
        return None
    m = re.match(r"^(\d{2})(\d{2})(\d{2})([NS])$", coord)
    if m:
        deg, minutes, seconds = int(m.group(1)), int(m.group(2)), int(m.group(3))
        val = deg + minutes / 60.0 + seconds / 3600.0
        return -val if m.group(4) == "S" else val
    m = re.match(r"^(\d{3})(\d{2})(\d{2})([EW])$", coord)
    if m:
        deg, minutes, seconds = int(m.group(1)), int(m.group(2)), int(m.group(3))
        val = deg + minutes / 60.0 + seconds / 3600.0
        return -val if m.group(4) == "W" else val
    m = re.match(r"^(\d{2})(\d{2})([NS])$", coord)
    if m:
        deg, minutes = int(m.group(1)), int(m.group(2))
        val = deg + minutes / 60.0
        return -val if m.group(3) == "S" else val
    m = re.match(r"^(\d{3})(\d{2})([EW])$", coord)
    if m:
        deg, minutes = int(m.group(1)), int(m.group(2))
        val = deg + minutes / 60.0
        return -val if m.group(3) == "W" else val
    return None
def parse_latlon_pair(text: str) -> Optional[Tuple[float, float]]:
    patterns = [
        r"(\d{4,7}[NS])\s*(\d{5,8}[EW])",
        r"(\d{2,3}\d{2}\d{0,2}\.?\d*[NS])\s*(\d{2,3}\d{2}\d{0,2}\.?\d*[EW])",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            lat = dms_to_decimal(m.group(1))
            lon = dms_to_decimal(m.group(2))
            if lat is not None and lon is not None:
                return lat, lon
    return None
# ------------------------------------------------------------------
# Height parsing
# ------------------------------------------------------------------
def parse_height_ft(g_text: str) -> Optional[int]:
    if not g_text:
        return None
    g = g_text.upper().strip()
    if "UNL" in g or "UNLIMITED" in g:
        return 99999
    m = re.search(r"FL\s*(\d+)", g)
    if m:
        return int(m.group(1)) * 100
    m = re.search(r"(\d+)\s*(?:FT|FEET)", g)
    if m:
        return int(m.group(1))
    m = re.search(r"^(\d+)$", g)
    if m:
        return int(m.group(1))
    return None
# ------------------------------------------------------------------
# Geometry helpers
# ------------------------------------------------------------------
def create_circle(lat: float, lon: float, radius_nm: float, points: int = 36) -> List[Tuple[float, float]]:
    radius_deg = radius_nm / 60.0
    coords = []
    for i in range(points + 1):
        angle = 2 * math.pi * i / points
        dlat = radius_deg * math.cos(angle)
        dlon = radius_deg * math.sin(angle) / max(math.cos(math.radians(lat)), 0.01)
        coords.append((lon + dlon, lat + dlat))
    return coords
def polygon_centroid(coords: List[Tuple[float, float]]) -> Tuple[float, float]:
    if not coords:
        return 0.0, 0.0
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    lon_sum = sum(c[0] for c in coords)
    lat_sum = sum(c[1] for c in coords)
    n = len(coords)
    return lon_sum / n, lat_sum / n
def close_polygon(coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if not coords:
        return coords
    if coords[0] != coords[-1]:
        return coords + [coords[0]]
    return coords


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    R_NM = 3440.065  # Earth radius in NM
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R_NM * c


def notam_center(n: Dict) -> Optional[Tuple[float, float]]:
    """Best available centre (lat, lon) for a parsed NOTAM."""
    if n.get("has_polygon") and n.get("polygon_coords"):
        clon, clat = polygon_centroid(n["polygon_coords"])
        return clat, clon
    if n.get("single_point"):
        lon, lat = n["single_point"]
        return lat, lon
    q = n.get("q_geo")
    if q:
        return q["lat"], q["lon"]
    return None


def filter_by_distance(
    notams: List[Dict],
    center_lat: float,
    center_lon: float,
    radius_nm: float,
    icao: Optional[str] = None,
) -> List[Dict]:
    """Keep NOTAMs whose geometry centre is within radius_nm of the centre,
    or whose A) location mentions the ICAO code."""
    kept = []
    for n in notams:
        # Always keep if A) explicitly lists this aerodrome
        if icao and icao.upper() in (n.get("location") or "").upper():
            kept.append(n)
            continue
        centre = notam_center(n)
        if centre is None:
            continue
        lat, lon = centre
        if haversine_nm(center_lat, center_lon, lat, lon) <= radius_nm:
            kept.append(n)
    return kept
# ------------------------------------------------------------------
# PDF download + parsing
# ------------------------------------------------------------------
def download_pdf():
    print("Downloading latest NOTAM PDF...")
    # Use a real User-Agent – some environments / proxies block the default urllib one
    req = urllib.request.Request(
        PDF_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NOTAM-KML-Generator/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    Path(PDF_FILE).write_bytes(data)
    print(f"Download complete. ({len(data)} bytes)")
def load_notams_from_pdf(filename: str) -> List[str]:
    """Extract raw NOTAM blocks from the CAA SUMMARY.pdf.

    Uses the proven split-on-NOTAMx approach (same idea as the working
    notamAPI class): CAA extracts IDs glued to the type, e.g. A2035/18NOTAMN.
    We split on NOTAMN/R/C, then prepend the ID that sits just before the marker.
    """
    reader = PdfReader(filename)
    text = ""
    # Page 0 is the cover / header – content starts on page 1 (0-based index 1)
    for page in reader.pages[1:]:
        text += (page.extract_text() or "") + "\n"

    # Split on the type marker, keeping the marker
    # e.g. "...A2035/18" + "NOTAMN" + "Q) FAJA/..."
    parts = re.split(r"(NOTAM[NRC])", text, flags=re.IGNORECASE)

    blocks: List[str] = []
    # parts is [preamble, marker, body, marker, body, ...]
    for i in range(1, len(parts) - 1, 2):
        marker = parts[i]          # "NOTAMN" / "NOTAMR" / "NOTAMC"
        body = parts[i + 1]
        prev = parts[i - 1]
        # ID is the last A####/## (or similar) sitting just before the marker
        m = re.search(r"([A-Z]\d{4}/\d{2})\s*$", prev.strip()[-20:])
        if not m:
            # Fallback: search a bit further back
            m = re.search(r"([A-Z]\d{4}/\d{2})\s*$", prev[-40:])
        if m:
            notam_id = m.group(1)
            block = f"{notam_id}{marker}{body}"
            blocks.append(block.strip())

    print(f"Extracted {len(blocks)} NOTAM blocks from PDF")

    if len(blocks) == 0:
        print("DEBUG: No blocks matched. Sample of extracted text (first 2000 chars):")
        print(repr(text[:2000]))
        print("---")
        for marker in ("NOTAMN", "NOTAMR", "NOTAMC"):
            print(f"DEBUG: count of {marker} = {text.count(marker)}")
        ids_found = re.findall(r"[A-Z]\d{4}/\d{2}", text)
        print(f"DEBUG: Raw ID-like tokens found: {len(ids_found)}")
        if ids_found:
            print("DEBUG: First 10 IDs:", ids_found[:10])

    return blocks
# ------------------------------------------------------------------
# Single NOTAM parser
# ------------------------------------------------------------------
def extract_q_line_geo(qline: str) -> Optional[Dict]:
    m = re.search(r"([0-9]{4}[NS][0-9]{5}[EW])([0-9]{3})\s*$", qline)
    if m:
        full = m.group(1)
        rad_str = m.group(2)
        lat_str = full[:5]
        lon_str = full[5:]
    else:
        m = re.search(r"([0-9]{4,6}[NS])\s*([0-9]{5,7}[EW])\s*([0-9]{1,3})", qline)
        if not m:
            return None
        lat_str, lon_str, rad_str = m.group(1), m.group(2), m.group(3)
    lat = dms_to_decimal(lat_str)
    lon = dms_to_decimal(lon_str)
    try:
        radius = int(rad_str)
    except ValueError:
        radius = 0
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon, "radius_nm": radius}
def parse_single_notam(text: str) -> Optional[Dict]:
    text = text.strip()
    if not text:
        return None
    id_match = re.search(r"([A-Z]\d{4}/\d{2})\s*NOTAM[NRC]?", text, re.IGNORECASE)
    if not id_match:
        id_match = re.search(r"([A-Z]\d{4}/\d{2})\b", text)
    notam_id = id_match.group(1) if id_match else "UNKNOWN"
    q_match = re.search(r"Q\)\s*(.+?)(?=\n[A-Z]\)|\Z)", text, re.DOTALL)
    qline = q_match.group(1).strip() if q_match else ""
    # A)/B)/C) often appear on one line in the PDF extract
    a_match = re.search(r"A\)\s*([A-Z0-9 ]+?)(?=\s*B\)|\n[B-Z]\)|\Z)", text, re.DOTALL)
    location = a_match.group(1).strip() if a_match else ""
    b_match = re.search(r"B\)\s*(\d{10})", text)
    c_match = re.search(r"C\)\s*(\S+)", text)
    valid_from = b_match.group(1) if b_match else ""
    valid_to = c_match.group(1) if c_match else ""
    e_match = re.search(r"E\)\s*(.+?)(?=\n[FG]\)|\Z)", text, re.DOTALL)
    e_text = e_match.group(1).strip() if e_match else text
    g_match = re.search(r"G\)\s*(.+?)(?=\n[A-Z]\)|\Z|$)", text, re.DOTALL)
    g_text = g_match.group(1).strip() if g_match else ""
    height_ft = parse_height_ft(g_text)
    q_geo = extract_q_line_geo(qline)
    # Collect coordinates from E)
    coord_list = re.findall(r"([0-9]{4,7}[NS]\s*[0-9]{5,8}[EW])", e_text)
    points = []
    for c in coord_list:
        pair = parse_latlon_pair(c)
        if pair:
            points.append((pair[1], pair[0])) # lon, lat
    has_polygon = len(points) >= 3
    single_point = points[0] if len(points) == 1 else None
    return {
        "id": notam_id,
        "location": location,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "text": e_text[:800] + ("..." if len(e_text) > 800 else ""),
        "q_geo": q_geo,
        "polygon_coords": points if has_polygon else [],
        "single_point": single_point,
        "has_polygon": has_polygon,
        "height_ft": height_ft,
    }
# ------------------------------------------------------------------
# KML generation
# ------------------------------------------------------------------
def create_kml(
    notams: List[Dict],
    output_path: str,
    filter_icao: Optional[str] = None,
    filter_radius_nm: Optional[float] = None,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
):
    name = "NOTAM Locations"
    if filter_icao and filter_radius_nm:
        name = f"NOTAMs within {filter_radius_nm:.0f} NM of {filter_icao}"
    kml = simplekml.Kml(name=name)

    # Styles
    red_point = simplekml.Style()
    red_point.iconstyle.icon.href = "http://maps.google.com/mapfiles/kml/paddle/red-circle.png"
    red_point.iconstyle.scale = 1.1
    red_poly = simplekml.Style()
    red_poly.linestyle.color = simplekml.Color.red
    red_poly.linestyle.width = 2
    red_poly.polystyle.color = simplekml.Color.changealphaint(90, simplekml.Color.red)
    blue_point = simplekml.Style()
    blue_point.iconstyle.icon.href = "http://maps.google.com/mapfiles/kml/paddle/blu-circle.png"
    blue_point.iconstyle.scale = 1.1
    blue_poly = simplekml.Style()
    blue_poly.linestyle.color = simplekml.Color.blue
    blue_poly.linestyle.width = 2
    blue_poly.polystyle.color = simplekml.Color.changealphaint(90, simplekml.Color.blue)

    # Draw filter centre + radius circle when filtering
    if filter_icao and center_lat is not None and center_lon is not None and filter_radius_nm:
        center_folder = kml.newfolder(name=f"Filter: {filter_icao} {filter_radius_nm:.0f} NM")
        green_point = simplekml.Style()
        green_point.iconstyle.icon.href = "http://maps.google.com/mapfiles/kml/paddle/grn-circle.png"
        green_point.iconstyle.scale = 1.3
        p = center_folder.newpoint(
            name=filter_icao,
            description=f"Filter centre: {filter_icao}<br>Radius: {filter_radius_nm} NM",
            coords=[(center_lon, center_lat)],
        )
        p.style = green_point
        green_poly = simplekml.Style()
        green_poly.linestyle.color = simplekml.Color.changealphaint(180, simplekml.Color.green)
        green_poly.linestyle.width = 2
        green_poly.polystyle.color = simplekml.Color.changealphaint(40, simplekml.Color.green)
        circle_coords = create_circle(center_lat, center_lon, filter_radius_nm, points=64)
        pol = center_folder.newpolygon(
            name=f"{filter_radius_nm:.0f} NM radius",
            description=f"Filter radius around {filter_icao}",
        )
        pol.outerboundaryis = circle_coords
        pol.style = green_poly

    for idx, n in enumerate(notams, start=1):
        height = n.get("height_ft")
        is_low = (height is not None and height < 1000)
        point_style = red_point if is_low else blue_point
        poly_style = red_poly if is_low else blue_poly
        colour_note = ""
        if height is not None:
            colour_note = f"<br>Upper limit: {height} ft → {'RED' if is_low else 'BLUE'}"
        else:
            colour_note = "<br>Upper limit: unknown → BLUE (default)"
        folder = kml.newfolder(name=str(idx))
        desc = (f"<b>#{idx}</b> ({n['id']})<br>"
                f"Location: {n['location']}<br>"
                f"Valid: {n['valid_from']} → {n['valid_to']}"
                f"{colour_note}<br><br>"
                f"<pre>{n['text']}</pre>")
        has_polygon = n.get("has_polygon", False)
        single_point = n.get("single_point")
        q_geo = n.get("q_geo")
        if has_polygon:
            closed = close_polygon(n["polygon_coords"])
            pol = folder.newpolygon(name=str(idx), description=desc)
            pol.outerboundaryis = closed
            pol.style = poly_style
            clon, clat = polygon_centroid(closed)
            p = folder.newpoint(name=str(idx), description=desc, coords=[(clon, clat)])
            p.style = point_style
        else:
            if single_point:
                pin_coords = single_point
            elif q_geo:
                pin_coords = (q_geo["lon"], q_geo["lat"])
            else:
                pin_coords = None
            if pin_coords:
                p = folder.newpoint(name=str(idx), description=desc, coords=[pin_coords])
                p.style = point_style
            if q_geo and q_geo["radius_nm"] and q_geo["radius_nm"] > 0:
                coords = create_circle(q_geo["lat"], q_geo["lon"], q_geo["radius_nm"])
                pol = folder.newpolygon(
                    name=str(idx),
                    description=desc + f"<br>Radius: {q_geo['radius_nm']} NM"
                )
                pol.outerboundaryis = coords
                pol.style = poly_style
    kml.save(output_path)
    print(f"KML written to: {output_path}")
    print(f"Total NOTAMs: {len(notams)}")
# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="NOTAM → KML generator for South Africa")
    parser.add_argument(
        "--icao",
        default=FILTER_ICAO,
        help="Filter centre ICAO (e.g. FASD). Omit or set empty for all NOTAMs.",
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=FILTER_RADIUS_NM,
        help="Filter radius in nautical miles (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_KML,
        help="Output KML path (default: %(default)s)",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Disable distance filter and include all NOTAMs",
    )
    args = parser.parse_args()

    filter_icao = None if args.no_filter else (args.icao.upper().strip() if args.icao else None)
    filter_radius = args.radius
    output_path = args.output

    try:
        print("=== Starting NOTAM to KML ===")
        if filter_icao:
            print(f"Filter: {filter_radius:.0f} NM around {filter_icao}")
        else:
            print("Filter: none (all NOTAMs)")

        # 1. Download
        print("Downloading PDF...")
        download_pdf()

        if not Path(PDF_FILE).exists():
            print("ERROR: PDF file was not downloaded!")
            return

        # 2. Extract
        print("Extracting NOTAMs from PDF...")
        blocks = load_notams_from_pdf(PDF_FILE)
        print(f"Found {len(blocks)} raw blocks")
        if len(blocks) == 0:
            print("ERROR: No NOTAM blocks found in the PDF.")
            return

        # 3. Parse
        parsed = []
        for i, block in enumerate(blocks):
            try:
                n = parse_single_notam(block)
                if n:
                    parsed.append(n)
            except Exception as e:
                print(f"Warning: Failed to parse block {i}: {e}")
        print(f"Successfully parsed {len(parsed)} NOTAMs")
        if not parsed:
            print("ERROR: No usable NOTAMs after parsing.")
            return

        # 4. Optional distance filter
        center_lat = center_lon = None
        if filter_icao:
            if filter_icao not in AIRPORTS:
                print(f"ERROR: Unknown ICAO '{filter_icao}'. Add it to AIRPORTS dict or use --no-filter.")
                print("Known:", ", ".join(sorted(AIRPORTS.keys())))
                return
            center_lat, center_lon = AIRPORTS[filter_icao]
            before = len(parsed)
            parsed = filter_by_distance(parsed, center_lat, center_lon, filter_radius, filter_icao)
            print(f"Distance filter: {before} → {len(parsed)} NOTAMs within {filter_radius:.0f} NM of {filter_icao}")
            if not parsed:
                print("WARNING: No NOTAMs within the filter radius.")
                # still write an empty-ish KML with just the centre circle

        # 5. Generate KML
        print("Generating KML...")
        create_kml(
            parsed,
            output_path,
            filter_icao=filter_icao,
            filter_radius_nm=filter_radius if filter_icao else None,
            center_lat=center_lat,
            center_lon=center_lon,
        )
        if Path(output_path).exists():
            print(f"SUCCESS: {output_path} created ({Path(output_path).stat().st_size} bytes)")
        else:
            print("ERROR: KML file was not created!")
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
