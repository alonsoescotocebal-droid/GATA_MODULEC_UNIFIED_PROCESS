#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


PORTUGUESE_AQ_ROOT_NAME = "Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024"
BASE_SMOKE_CONTRACT_FOR_OC03C_PASS = "BASE_SMOKE_CONTRACT_FOR_OC03C_PASS"
PORTUGUESE_AQ_BASE_SMOKE_BLOCKED = "BLOCKED_BASE_SMOKE_REGRESSION"
PORTUGUESE_AQ_NO_DATA = "NO_PORTUGUESE_AQ_DATA_FOUND"
PORTUGUESE_AQ_INVENTORIED_ONLY = "PORTUGUESE_AQ_INVENTORIED_ONLY"
PORTUGUESE_AQ_INSUFFICIENT = "PORTUGUESE_AQ_CONSUMED_BUT_SPATIALLY_INSUFFICIENT_FOR_LOCAL_AQ_ANCHOR"
PORTUGUESE_AQ_ANCHORED = "LOCAL_AQ_ANCHORED_PROXY"
PORTUGUESE_AQ_HEALTH_CANDIDATE = "HEALTH_EXPOSURE_VALIDATED_CANDIDATE"

PROXY_TIER_3 = "TIER_3_PEER_REVIEWED_OPERATIONAL_PROXY"
PROXY_TIER_2 = "TIER_2_LOCAL_SMOKE_PROXY_VALIDATED_BY_AQ"
HEALTH_BLOCKED = "HEALTH_EXPOSURE_CLAIM_BLOCKED"
HEALTH_NOT_DECLARED = "HEALTH_EXPOSURE_NOT_DECLARED"
HEALTH_VALIDATED = "HEALTH_EXPOSURE_VALIDATED"

AQ_PROTOCOL_PROXY = "GO_DIRECT_2015_2024_FOR_PROSPECTIVE_PROXY_SCREENING"
AQ_PROTOCOL_PROXY_NOT_CONSUMED_NOTE = "PORTUGUESE_AQ_VALIDATION_NOT_CONSUMED"
AQ_PROTOCOL_PROXY_INSUFFICIENT_NOTE = PORTUGUESE_AQ_INSUFFICIENT
AQ_PROTOCOL_ANCHORED = "GO_WITH_PORTUGUESE_AQ_ANCHORED_PROXY_PROTOCOL"

AQ_ALLOWED_CLAIM = "GFAS/ERA5 smoke proxy is locally supported by Portuguese/EEA air-quality observations"
AQ_PROXY_ONLY_CLAIM = "GFAS/ERA5 smoke proxy remains a prospective screening layer without Portuguese/EEA local AQ anchoring"
AQ_BASE_SMOKE_BLOCKED_CLAIM = "Portuguese AQ validation was not consumed because the base smoke contract regressed"
AQ_FORBIDDEN_CLAIM = "validated health exposure"

_NS_MAIN = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_NS_REL = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

_POLLUTANT_ALIASES = {
    "pm2.5": "PM2.5",
    "pm25": "PM2.5",
    "pm2p5": "PM2.5",
    "pm2_5": "PM2.5",
    "pm2 5": "PM2.5",
    "pm 2 5": "PM2.5",
    "pm 25": "PM2.5",
    "pm 10": "PM10",
    "particulate matter d 2.5 um": "PM2.5",
    "particulate matter d 25 um": "PM2.5",
    "pm10": "PM10",
    "o3": "O3",
    "ozone": "O3",
    "no2": "NO2",
    "nitrogen dioxide": "NO2",
    "so2": "SO2",
    "sulfur dioxide": "SO2",
    "sulphur dioxide": "SO2",
    "co": "CO",
    "carbon monoxide": "CO",
}

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_SPLIT_RE = re.compile(r"[/,()\-]+")
_WORD_RE = re.compile(r"[^a-z0-9]+")


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_float(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in ("nan", "na", "none", "null"):
        return None
    try:
        return float(text)
    except Exception:
        return None


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]], delim: str = ";") -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=delim)
        writer.writerow(list(header))
        for row in rows:
            writer.writerow(list(row))


def write_tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    write_csv(path, header, rows, delim="\t")


def sniff_delimiter(path: Path) -> str:
    sample = path.read_bytes()[:65536].decode("utf-8-sig", errors="replace")
    counts = {";": sample.count(";"), ",": sample.count(","), "\t": sample.count("\t")}
    best = max(counts, key=lambda key: counts[key])
    return best if counts[best] > 0 else ","


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    delim = sniff_delimiter(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=delim))


def load_json_object(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def normalize_text(text: object) -> str:
    value = _strip_accents(str(text or "")).lower()
    value = _WORD_RE.sub(" ", value)
    return " ".join(value.split())


def normalize_pollutant_name(raw: object) -> str:
    cleaned = normalize_text(raw).replace(" ug m3", "").replace(" ug m 3", "")
    cleaned = cleaned.replace("Âµg m3", "").replace("Âµg m 3", "")
    cleaned = cleaned.strip()
    return _POLLUTANT_ALIASES.get(cleaned, str(raw or "").strip())


def _extract_pollutant_and_unit(raw: str) -> Tuple[str, str]:
    text = str(raw or "").strip().replace("\t", " ")
    match = re.search(r"\(([^)]+)\)", text)
    unit = match.group(1).strip() if match else ""
    pollutant = re.sub(r"\([^)]*\)", "", text).strip()
    return pollutant, unit


def _normalize_station_id(name: str) -> str:
    slug = normalize_text(name).replace(" ", "_")
    return slug[:120] if slug else "station_unknown"


def _coerce_iso_date(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    match = _DATE_RE.search(text)
    if not match:
        return ""
    try:
        value = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except Exception:
        return ""
    return value.isoformat()


def _date_shift(raw_date: str, days: int) -> str:
    try:
        value = dt.date.fromisoformat(raw_date)
    except Exception:
        return ""
    return (value + dt.timedelta(days=days)).isoformat()


def _norm_path(path: Path) -> str:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = Path(os.path.abspath(str(path)))
    return os.path.normcase(os.path.normpath(str(resolved)))


def _is_same_or_subpath(path: Path, prefix: Path) -> bool:
    n_path = _norm_path(path)
    n_prefix = _norm_path(prefix)
    return n_path == n_prefix or n_path.startswith(n_prefix + os.sep)


def resolve_portuguese_aq_root(modulec_datos: Path) -> Optional[Path]:
    candidates: List[Path] = []
    env_root = os.environ.get("MODULEC_OC03_PORTUGUESE_AQ_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    if modulec_datos.name == PORTUGUESE_AQ_ROOT_NAME:
        candidates.append(modulec_datos)
    candidates.append(modulec_datos.parent / PORTUGUESE_AQ_ROOT_NAME)
    for candidate in candidates:
        if candidate.exists() and candidate.name == PORTUGUESE_AQ_ROOT_NAME:
            return candidate
    return None


def _is_approved_portuguese_aq_root(aq_root: Optional[Path], allowed_data_prefixes: Sequence[Path]) -> bool:
    if aq_root is None:
        return False
    if aq_root.name != PORTUGUESE_AQ_ROOT_NAME:
        return False
    return any(_is_same_or_subpath(aq_root, prefix) for prefix in allowed_data_prefixes)


def _read_allowed_data_prefixes(repo_root: Path, modulec_datos: Path) -> List[Path]:
    config_path = repo_root / "config" / "module_c_canonical_paths.json"
    if config_path.exists():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
            out: List[Path] = []
            raw_prefixes = payload.get("DATA_ROOT_ALLOWED_PREFIXES")
            if isinstance(raw_prefixes, list):
                for value in raw_prefixes:
                    text = str(value).strip()
                    if text:
                        out.append(Path(text))
            root_text = str(payload.get("DATA_ROOT_ALLOWED_PREFIX") or "").strip()
            if root_text:
                out.append(Path(root_text))
            seen = set()
            deduped: List[Path] = []
            for item in out:
                key = _norm_path(item)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            if deduped:
                return deduped
        except Exception:
            pass
    parent = modulec_datos.parent
    return [
        parent / "Datos",
        parent / "Datos_RECOVERY_2015_2024_PIPELINE_GRIB",
        parent / "Datos_RECOVERY_PORTUGUESE_AGENCIES_2015_2024",
        parent / "Datos_RECOVERY_2015_2024",
    ]


def _xlsx_col_to_idx(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    acc = 0
    for ch in letters:
        acc = acc * 26 + (ord(ch) - 64)
    return max(acc - 1, 0)


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values: List[str] = []
    for item in root.findall("a:si", _NS_MAIN):
        texts = [node.text or "" for node in item.iterfind(".//a:t", _NS_MAIN)]
        values.append("".join(texts))
    return values


def _xlsx_first_sheet(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets = workbook.find("a:sheets", _NS_MAIN)
    if sheets is None or len(list(sheets)) <= 0:
        return "xl/worksheets/sheet1.xml"
    first = list(sheets)[0]
    rel_id = first.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall("r:Relationship", _NS_REL):
        if rel.attrib.get("Id") == rel_id:
            return "xl/" + rel.attrib.get("Target", "worksheets/sheet1.xml").lstrip("/")
    return "xl/worksheets/sheet1.xml"


def _xlsx_cell_value(cell: ET.Element, shared: Sequence[str]) -> str:
    kind = cell.attrib.get("t", "")
    if kind == "inlineStr":
        parts = [node.text or "" for node in cell.iterfind(".//a:t", _NS_MAIN)]
        return "".join(parts)
    value_node = cell.find("a:v", _NS_MAIN)
    raw = value_node.text if value_node is not None else ""
    if kind == "s" and raw.isdigit():
        idx = int(raw)
        if 0 <= idx < len(shared):
            return shared[idx]
    return raw


def _xlsx_matrix_rows(path: Path) -> List[Dict[int, str]]:
    with zipfile.ZipFile(path) as zf:
        shared = _xlsx_shared_strings(zf)
        sheet_member = _xlsx_first_sheet(zf)
        root = ET.fromstring(zf.read(sheet_member))
    rows_out: List[Dict[int, str]] = []
    for row in root.findall(".//a:sheetData/a:row", _NS_MAIN):
        row_map: Dict[int, str] = {}
        for cell in row.findall("a:c", _NS_MAIN):
            ref = cell.attrib.get("r", "")
            idx = _xlsx_col_to_idx(ref)
            row_map[idx] = _xlsx_cell_value(cell, shared)
        if row_map:
            rows_out.append(row_map)
    return rows_out


def parse_qualar_xlsx(path: Path) -> Tuple[Dict[str, object], List[Dict[str, object]], List[Dict[str, object]]]:
    rows = _xlsx_matrix_rows(path)
    meta = {
        "file": str(path),
        "format": "xlsx",
        "status": "PASS",
        "pollutant_raw": "",
        "pollutant": "",
        "unit": "",
        "station_count": 0,
        "observation_rows": 0,
        "layout": "QUALAR_WIDE_MATRIX",
        "datetime_field": "A",
        "station_field": "header_row",
        "value_field": "matrix_numeric",
        "note": "",
    }
    if not rows:
        meta["status"] = "FAIL_READ"
        meta["note"] = "XLSX has no readable rows."
        return meta, [], []

    header = rows[0]
    pollutant_raw, unit = _extract_pollutant_and_unit(header.get(0, ""))
    pollutant = normalize_pollutant_name(pollutant_raw)
    stations = {idx: str(value).strip() for idx, value in header.items() if idx > 0 and str(value).strip()}
    meta["pollutant_raw"] = pollutant_raw
    meta["pollutant"] = pollutant
    meta["unit"] = unit
    meta["station_count"] = len(stations)
    if not stations:
        meta["status"] = "FAIL_PARSE"
        meta["note"] = "No station columns detected in header row."
        return meta, [], []

    station_rows: List[Dict[str, object]] = []
    for idx, station_name in sorted(stations.items()):
        station_rows.append(
            {
                "station_key": normalize_text(station_name),
                "station_id": _normalize_station_id(station_name),
                "station_name": station_name,
                "source_file": str(path),
                "source_kind": "QUALAR_XLSX_HEADER",
                "metadata_source": "QUALAR_WIDE_MATRIX",
                "latitude": "",
                "longitude": "",
                "country_code": "PT",
                "aq_metadata_relevant": "YES",
            }
        )

    observations: List[Dict[str, object]] = []
    for row in rows[1:]:
        date_value = _coerce_iso_date(row.get(0, ""))
        if not date_value:
            continue
        datetime_raw = str(row.get(0, "")).strip()
        for idx, station_name in stations.items():
            value = safe_float(row.get(idx))
            if value is None:
                continue
            observations.append(
                {
                    "station_key": normalize_text(station_name),
                    "station_id": _normalize_station_id(station_name),
                    "station_name": station_name,
                    "pollutant_raw": pollutant_raw,
                    "pollutant": pollutant,
                    "unit": unit,
                    "datetime": datetime_raw,
                    "date": date_value,
                    "value": value,
                    "source_file": str(path),
                    "quality_status": "",
                }
            )
    meta["observation_rows"] = len(observations)
    if not observations:
        meta["status"] = "FAIL_PARSE"
        meta["note"] = "No numeric matrix cells produced observations."
    return meta, observations, station_rows


def _find_first_key(obj: Dict[str, object], candidates: Sequence[str]) -> str:
    lookup = {normalize_text(key): key for key in obj.keys()}
    for candidate in candidates:
        key = lookup.get(normalize_text(candidate))
        if key:
            return key
    return ""


def parse_generic_timeseries_table(path: Path) -> Tuple[Dict[str, object], List[Dict[str, object]], List[Dict[str, object]]]:
    rows = read_csv_rows(path)
    meta = {
        "file": str(path),
        "format": path.suffix.lower().lstrip("."),
        "status": "FAIL_PARSE",
        "pollutant_raw": "",
        "pollutant": "",
        "unit": "",
        "station_count": 0,
        "observation_rows": 0,
        "layout": "LONG_TABLE",
        "datetime_field": "",
        "station_field": "",
        "value_field": "",
        "note": "No table rows.",
    }
    if not rows:
        return meta, [], []

    sample = rows[0]
    station_key = _find_first_key(sample, ("station_id", "station_name", "nome_estacao", "codigo_estacao"))
    date_key = _find_first_key(sample, ("datetime", "date", "data", "timestamp"))
    value_key = _find_first_key(sample, ("value", "concentration", "valor", "measurement"))
    pollutant_key = _find_first_key(sample, ("pollutant", "pollutant_code", "poluente"))
    unit_key = _find_first_key(sample, ("unit", "unidade"))
    if not station_key or not date_key or not value_key:
        meta["note"] = "Required long-table fields not detected."
        return meta, [], []

    meta["datetime_field"] = date_key
    meta["station_field"] = station_key
    meta["value_field"] = value_key
    station_rows: Dict[str, Dict[str, object]] = {}
    observations: List[Dict[str, object]] = []
    for row in rows:
        station_name = str(row.get(station_key) or "").strip()
        if not station_name:
            continue
        date_value = _coerce_iso_date(row.get(date_key, ""))
        value = safe_float(row.get(value_key))
        if not date_value or value is None:
            continue
        pollutant_raw = str(row.get(pollutant_key) or "").strip()
        pollutant = normalize_pollutant_name(pollutant_raw)
        unit = str(row.get(unit_key) or "").strip()
        station_norm = normalize_text(station_name)
        station_rows.setdefault(
            station_norm,
            {
                "station_key": station_norm,
                "station_id": _normalize_station_id(station_name),
                "station_name": station_name,
                "source_file": str(path),
                "source_kind": "AQ_LONG_TABLE",
                "metadata_source": "AQ_LONG_TABLE",
                "latitude": str(row.get("latitude") or row.get("lat") or "").strip(),
                "longitude": str(row.get("longitude") or row.get("lon") or "").strip(),
                "country_code": str(row.get("country_code") or "PT").strip() or "PT",
                "aq_metadata_relevant": "YES",
            },
        )
        observations.append(
            {
                "station_key": station_norm,
                "station_id": _normalize_station_id(station_name),
                "station_name": station_name,
                "pollutant_raw": pollutant_raw,
                "pollutant": pollutant,
                "unit": unit,
                "datetime": str(row.get(date_key) or "").strip(),
                "date": date_value,
                "value": value,
                "source_file": str(path),
                "quality_status": str(row.get("quality_status") or row.get("validation_flag") or "").strip(),
            }
        )
    meta["status"] = "PASS" if observations else "FAIL_PARSE"
    meta["observation_rows"] = len(observations)
    meta["station_count"] = len(station_rows)
    meta["pollutant_raw"] = str(rows[0].get(pollutant_key) or "").strip() if pollutant_key else ""
    meta["pollutant"] = normalize_pollutant_name(meta["pollutant_raw"])
    meta["unit"] = str(rows[0].get(unit_key) or "").strip() if unit_key else ""
    meta["note"] = "" if observations else "Rows present but no valid station/date/value tuples."
    return meta, observations, list(station_rows.values())


def _extract_station_records_from_feature_collection(payload: object, path: Path) -> List[Dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    features = payload.get("features")
    if not isinstance(features, list):
        return []
    rows: List[Dict[str, object]] = []
    aq_relevant = "YES" if any(token in str(path).lower() for token in ("eea", "aq", "qualar")) else "NO"
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        if not isinstance(props, dict):
            props = {}
        if not isinstance(geom, dict):
            geom = {}
        name_key = _find_first_key(props, ("station_name", "nome_estacao", "localEstacao", "name"))
        id_key = _find_first_key(props, ("station_id", "codigo_estacao", "idEstacao", "id"))
        coords = geom.get("coordinates")
        if not name_key and not id_key:
            continue
        lon = ""
        lat = ""
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lon = str(coords[0])
            lat = str(coords[1])
        station_name = str(props.get(name_key) or props.get(id_key) or "").strip()
        station_id = str(props.get(id_key) or _normalize_station_id(station_name)).strip()
        rows.append(
            {
                "station_key": normalize_text(station_name or station_id),
                "station_id": station_id or _normalize_station_id(station_name),
                "station_name": station_name or station_id,
                "source_file": str(path),
                "source_kind": "GEOJSON_STATION_METADATA",
                "metadata_source": "FeatureCollection",
                "latitude": lat,
                "longitude": lon,
                "country_code": "PT",
                "aq_metadata_relevant": aq_relevant,
            }
        )
    return rows


def _extract_station_records_from_json(path: Path) -> List[Dict[str, object]]:
    try:
        payload = load_json_object(path)
    except Exception:
        return []
    feature_rows = _extract_station_records_from_feature_collection(payload, path)
    if feature_rows:
        return feature_rows
    if not isinstance(payload, list):
        return []
    out: List[Dict[str, object]] = []
    aq_relevant = "YES" if any(token in str(path).lower() for token in ("eea", "aq", "qualar")) else "NO"
    for row in payload:
        if not isinstance(row, dict):
            continue
        name_key = _find_first_key(row, ("station_name", "nome_estacao", "localEstacao", "name"))
        id_key = _find_first_key(row, ("station_id", "codigo_estacao", "idEstacao", "id"))
        lat_key = _find_first_key(row, ("latitude", "lat"))
        lon_key = _find_first_key(row, ("longitude", "lon"))
        if not name_key and not id_key:
            continue
        station_name = str(row.get(name_key) or row.get(id_key) or "").strip()
        station_id = str(row.get(id_key) or _normalize_station_id(station_name)).strip()
        out.append(
            {
                "station_key": normalize_text(station_name or station_id),
                "station_id": station_id or _normalize_station_id(station_name),
                "station_name": station_name or station_id,
                "source_file": str(path),
                "source_kind": "JSON_STATION_METADATA",
                "metadata_source": "JSON_LIST",
                "latitude": str(row.get(lat_key) or "").strip() if lat_key else "",
                "longitude": str(row.get(lon_key) or "").strip() if lon_key else "",
                "country_code": "PT",
                "aq_metadata_relevant": aq_relevant,
            }
        )
    return out


def inventory_aq_root(aq_root: Optional[Path]) -> List[Path]:
    if aq_root is None or not aq_root.exists():
        return []
    return sorted(path for path in aq_root.rglob("*") if path.is_file())


def _classify_file(path: Path) -> str:
    lower = str(path).lower()
    if "manual_exports" in lower and path.suffix.lower() == ".xlsx":
        return "AQ_TIMESERIES_QUALAR_XLSX"
    if "qualar_direct_api_all_pollutants" in lower and path.suffix.lower() in (".csv", ".tsv"):
        return "AQ_TIMESERIES_STATUS_MANIFEST"
    if path.suffix.lower() in (".json", ".geojson") and any(token in lower for token in ("stations", "estacao", "eea", "aq")):
        return "STATION_METADATA_CANDIDATE"
    if path.suffix.lower() in (".csv", ".tsv"):
        return "TABULAR_AUDIT_OR_CATALOG"
    return "ANCILLARY"


def aggregate_daily_station_rows(observations: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, str, str, str], List[float]] = defaultdict(list)
    sample_rows: Dict[Tuple[str, str, str, str], Dict[str, object]] = {}
    update_daily_station_aggregates(observations, grouped, sample_rows)
    return finalize_daily_station_aggregates(grouped, sample_rows)


def update_daily_station_aggregates(
    observations: Iterable[Dict[str, object]],
    grouped: Dict[Tuple[str, str, str, str], List[float]],
    sample_rows: Dict[Tuple[str, str, str, str], Dict[str, object]],
) -> None:
    for row in observations:
        station_id = str(row.get("station_id") or "")
        station_name = str(row.get("station_name") or "")
        pollutant = str(row.get("pollutant") or row.get("pollutant_raw") or "")
        date_value = str(row.get("date") or "")
        key = (station_id, station_name, pollutant, date_value)
        value = safe_float(row.get("value"))
        if value is None or date_value == "":
            continue
        grouped[key].append(value)
        if key not in sample_rows:
            sample_rows[key] = {
                "station_key": row.get("station_key", normalize_text(station_name)),
                "pollutant_raw": row.get("pollutant_raw", pollutant),
                "unit": row.get("unit", ""),
                "source_file": row.get("source_file", ""),
                "quality_status": row.get("quality_status", ""),
            }


def finalize_daily_station_aggregates(
    grouped: Dict[Tuple[str, str, str, str], List[float]],
    sample_rows: Dict[Tuple[str, str, str, str], Dict[str, object]],
) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for key, values in sorted(grouped.items()):
        sample = sample_rows[key]
        out.append(
            {
                "station_id": key[0],
                "station_name": key[1],
                "station_key": sample.get("station_key", normalize_text(key[1])),
                "pollutant": key[2],
                "pollutant_raw": sample.get("pollutant_raw", key[2]),
                "date": key[3],
                "unit": sample.get("unit", ""),
                "daily_value": sum(values) / len(values),
                "observation_count": len(values),
                "source_file": sample.get("source_file", ""),
                "quality_status": sample.get("quality_status", ""),
            }
        )
    return out


def _load_municipio_unit_map(path: Path) -> Tuple[List[Dict[str, str]], Dict[str, Dict[str, str]]]:
    if not path.exists():
        return [], {}
    rows = read_csv_rows(path)
    out_rows: List[Dict[str, str]] = []
    lookup: Dict[str, Dict[str, str]] = {}
    for row in rows:
        municipio_id = str(row.get("municipio_id") or "").strip()
        nuts3_id = str(row.get("nuts3_id") or "").strip()
        mapping_ok = str(row.get("mapping_ok") or "").strip().lower()
        if not municipio_id or not nuts3_id or mapping_ok in ("0", "false", "no"):
            continue
        out_rows.append(row)
        lookup[normalize_text(municipio_id)] = {"municipio_id": municipio_id, "nuts3_id": nuts3_id}
    return out_rows, lookup


def _load_nuts_names(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    rows = read_csv_rows(path)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        unit_id = str(row.get("unit_id") or "").strip()
        unit_name = str(row.get("unit_name") or "").strip()
        if not unit_id or not unit_name:
            continue
        out[normalize_text(unit_name)] = {"nuts3_id": unit_id, "nuts3_name": unit_name}
    return out


def _name_candidates(station_name: str) -> List[str]:
    full = normalize_text(station_name)
    candidates = [full]
    for part in _SPLIT_RE.split(station_name):
        norm = normalize_text(part)
        if norm and norm not in candidates:
            candidates.append(norm)
    return [candidate for candidate in candidates if candidate]


def assign_station_name(
    station_name: str,
    municipio_lookup: Dict[str, Dict[str, str]],
    nuts_lookup: Dict[str, Dict[str, str]],
) -> Dict[str, str]:
    full = normalize_text(station_name)
    candidates = _name_candidates(station_name)
    for candidate in candidates:
        hit = municipio_lookup.get(candidate)
        if hit:
            return {
                "assignment_method": "municipio_name_exact",
                "assignment_confidence": "HIGH",
                "municipio_id": hit["municipio_id"],
                "nuts3_id": hit["nuts3_id"],
                "nuts3_name": "",
            }
    contains_hits: List[Tuple[int, Dict[str, str]]] = []
    padded = f" {full} "
    for key, hit in municipio_lookup.items():
        if len(key) < 4:
            continue
        if f" {key} " in padded:
            contains_hits.append((len(key), hit))
    if contains_hits:
        contains_hits.sort(key=lambda item: item[0], reverse=True)
        top_len = contains_hits[0][0]
        unique = {item[1]["municipio_id"]: item[1] for item in contains_hits if item[0] == top_len}
        if len(unique) == 1:
            hit = next(iter(unique.values()))
            return {
                "assignment_method": "municipio_name_contains",
                "assignment_confidence": "MEDIUM",
                "municipio_id": hit["municipio_id"],
                "nuts3_id": hit["nuts3_id"],
                "nuts3_name": "",
            }
    for candidate in candidates:
        hit = nuts_lookup.get(candidate)
        if hit:
            return {
                "assignment_method": "nuts_name_exact",
                "assignment_confidence": "HIGH",
                "municipio_id": "",
                "nuts3_id": hit["nuts3_id"],
                "nuts3_name": hit["nuts3_name"],
            }
    return {
        "assignment_method": "UNASSIGNED",
        "assignment_confidence": "LOW",
        "municipio_id": "",
        "nuts3_id": "",
        "nuts3_name": "",
    }


def _load_smoke_lookup(path: Path, level_name: str) -> Dict[Tuple[str, str], Dict[str, object]]:
    if not path.exists():
        return {}
    rows = read_csv_rows(path)
    lookup: Dict[Tuple[str, str], Dict[str, object]] = {}
    for row in rows:
        unit_id = str(row.get("unit_id") or "").strip()
        date_value = str(row.get("date") or "").strip()
        score = safe_float(row.get("smoke_day_score"))
        if not unit_id or not date_value or score is None:
            continue
        threshold_value = safe_float(row.get("threshold_value"))
        smoke_day_proxy = safe_float(row.get("smoke_day_proxy"))
        smoke_day_equivalent = safe_float(row.get("smoke_day_equivalent"))
        high_flag = False
        flag_method = ""
        if smoke_day_proxy is not None:
            high_flag = smoke_day_proxy > 0.0
            flag_method = "smoke_day_proxy_gt_0"
        elif smoke_day_equivalent is not None:
            high_flag = smoke_day_equivalent > 0.0
            flag_method = "smoke_day_equivalent_gt_0"
        elif threshold_value is not None:
            high_flag = score >= threshold_value
            flag_method = "score_gte_threshold_value"
        else:
            high_flag = score > 0.0
            flag_method = "score_gt_0"
        lookup[(unit_id, date_value)] = {
            "unit_level": level_name,
            "unit_id": unit_id,
            "date": date_value,
            "smoke_day_score": score,
            "threshold_value": threshold_value if threshold_value is not None else "",
            "high_smoke_flag": 1 if high_flag else 0,
            "high_smoke_method": flag_method,
        }
    return lookup


def _rank(values: Sequence[float]) -> List[float]:
    order = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    idx = 0
    while idx < len(order):
        end = idx
        while end + 1 < len(order) and order[end + 1][1] == order[idx][1]:
            end += 1
        avg_rank = (idx + end + 2) / 2.0
        for pos in range(idx, end + 1):
            ranks[order[pos][0]] = avg_rank
        idx = end + 1
    return ranks


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x <= 0 or den_y <= 0:
        return None
    return num / (den_x * den_y)


def spearman_correlation(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    return _pearson(_rank(xs), _rank(ys))


def median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    sorted_values = sorted(float(value) for value in values)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def build_concordance(
    daily_station_rows: Sequence[Dict[str, object]],
    smoke_muni_lookup: Dict[Tuple[str, str], Dict[str, object]],
    smoke_nuts_lookup: Dict[Tuple[str, str], Dict[str, object]],
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    joined_rows: List[Dict[str, object]] = []
    portugal_daily: Dict[str, int] = defaultdict(int)
    for key, row in smoke_muni_lookup.items():
        portugal_daily[row["date"]] = max(portugal_daily[row["date"]], int(row["high_smoke_flag"]))
    for key, row in smoke_nuts_lookup.items():
        portugal_daily[row["date"]] = max(portugal_daily[row["date"]], int(row["high_smoke_flag"]))

    for row in daily_station_rows:
        municipio_id = str(row.get("municipio_id") or "").strip()
        nuts3_id = str(row.get("nuts3_id") or "").strip()
        date_value = str(row.get("date") or "").strip()
        smoke_row = None
        unit_level = ""
        if municipio_id:
            smoke_row = smoke_muni_lookup.get((municipio_id, date_value))
            unit_level = "MUNICIPIO"
        if smoke_row is None and nuts3_id:
            smoke_row = smoke_nuts_lookup.get((nuts3_id, date_value))
            unit_level = "NUTS3"
        same_day_high = int(smoke_row.get("high_smoke_flag")) if smoke_row else 0
        pm1_high = max(
            same_day_high,
            int((smoke_muni_lookup.get((municipio_id, _date_shift(date_value, -1))) or {}).get("high_smoke_flag", 0)) if municipio_id else 0,
            int((smoke_muni_lookup.get((municipio_id, _date_shift(date_value, 1))) or {}).get("high_smoke_flag", 0)) if municipio_id else 0,
            int((smoke_nuts_lookup.get((nuts3_id, _date_shift(date_value, -1))) or {}).get("high_smoke_flag", 0)) if nuts3_id else 0,
            int((smoke_nuts_lookup.get((nuts3_id, _date_shift(date_value, 1))) or {}).get("high_smoke_flag", 0)) if nuts3_id else 0,
        )
        joined_rows.append(
            {
                **dict(row),
                "matched_to_smoke_unit": "YES" if smoke_row else "NO",
                "matched_unit_level": unit_level if smoke_row else "",
                "same_day_high_smoke_flag": same_day_high,
                "plusminus1_high_smoke_flag": pm1_high,
                "smoke_day_score": smoke_row.get("smoke_day_score", "") if smoke_row else "",
                "smoke_threshold_value": smoke_row.get("threshold_value", "") if smoke_row else "",
                "smoke_flag_method": smoke_row.get("high_smoke_method", "") if smoke_row else "",
                "portugal_same_day_high_smoke_flag": int(portugal_daily.get(date_value, 0)),
            }
        )

    grouped: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)
    for row in joined_rows:
        pollutant = str(row.get("pollutant") or "")
        grouped[(pollutant, "SPATIAL_MATCHED")].append(row)
        grouped[(pollutant, "PORTUGAL_SUPPLEMENTAL")].append(row)

    summary_rows: List[Dict[str, object]] = []
    for (pollutant, scope), rows in sorted(grouped.items()):
        if scope == "SPATIAL_MATCHED":
            subset = [row for row in rows if str(row.get("matched_to_smoke_unit")) == "YES"]
            high_key = "same_day_high_smoke_flag"
        else:
            subset = list(rows)
            high_key = "portugal_same_day_high_smoke_flag"
        matched_count = len(subset)
        high_rows = [row for row in subset if int(row.get(high_key) or 0) > 0]
        non_high_rows = [row for row in subset if int(row.get(high_key) or 0) <= 0]
        values_high = [float(row["daily_value"]) for row in high_rows if safe_float(row.get("daily_value")) is not None]
        values_non_high = [float(row["daily_value"]) for row in non_high_rows if safe_float(row.get("daily_value")) is not None]
        score_rows = [
            row for row in subset
            if safe_float(row.get("smoke_day_score")) is not None and safe_float(row.get("daily_value")) is not None
        ]
        score_values = [float(row["smoke_day_score"]) for row in score_rows]
        aq_values = [float(row["daily_value"]) for row in score_rows]
        corr = spearman_correlation(score_values, aq_values)
        med_high = median(values_high)
        med_non_high = median(values_non_high)
        delta = None if med_high is None or med_non_high is None else (med_high - med_non_high)
        same_day_hits = sum(int(row.get("same_day_high_smoke_flag") or 0) for row in subset)
        pm1_hits = sum(int(row.get("plusminus1_high_smoke_flag") or 0) for row in subset)
        assigned_stations = sorted({str(row.get("station_id") or "") for row in subset if str(row.get("station_id") or "").strip()})
        unique_units = sorted(
            {
                str(row.get("municipio_id") or row.get("nuts3_id") or "").strip()
                for row in subset
                if str(row.get("municipio_id") or row.get("nuts3_id") or "").strip()
            }
        )
        if matched_count < 10 or len(high_rows) < 3:
            signal = "INSUFFICIENT"
        elif delta is not None and delta > 0 and (corr is None or corr > 0.05):
            signal = "POSITIVE"
        elif delta is not None and delta < 0:
            signal = "NEGATIVE"
        else:
            signal = "WEAK"
        summary_rows.append(
            {
                "pollutant": pollutant,
                "scope": scope,
                "matched_day_count": matched_count,
                "high_gfas_day_count": len(high_rows),
                "non_high_day_count": len(non_high_rows),
                "median_pollutant_on_high_days": "" if med_high is None else round(med_high, 6),
                "median_pollutant_on_non_high_days": "" if med_non_high is None else round(med_non_high, 6),
                "delta_median": "" if delta is None else round(delta, 6),
                "spearman_correlation": "" if corr is None else round(corr, 6),
                "same_day_coincidence_count": same_day_hits,
                "plusminus1_coincidence_count": pm1_hits,
                "station_count": len(assigned_stations),
                "unit_count": len(unique_units),
                "concordance_signal": signal,
            }
        )
    return joined_rows, summary_rows


def determine_gate(
    discovered_files: int,
    timeseries_files_normalized: int,
    daily_station_count: int,
    assigned_station_count: int,
    concordance_rows: Sequence[Dict[str, object]],
    threshold_comparisons_present: bool,
) -> Dict[str, str]:
    best_spatial = [
        row for row in concordance_rows
        if str(row.get("scope")) == "SPATIAL_MATCHED" and str(row.get("concordance_signal")) == "POSITIVE"
    ]
    best_spatial = sorted(best_spatial, key=lambda row: (int(row.get("matched_day_count") or 0), int(row.get("high_gfas_day_count") or 0)), reverse=True)

    if discovered_files <= 0:
        status = PORTUGUESE_AQ_NO_DATA
        tier = PROXY_TIER_3
        claim = AQ_PROTOCOL_PROXY
        claim_note = AQ_PROTOCOL_PROXY_NOT_CONSUMED_NOTE
        health = HEALTH_BLOCKED
    elif timeseries_files_normalized <= 0 or daily_station_count <= 0:
        status = PORTUGUESE_AQ_INVENTORIED_ONLY
        tier = PROXY_TIER_3
        claim = AQ_PROTOCOL_PROXY
        claim_note = AQ_PROTOCOL_PROXY_NOT_CONSUMED_NOTE
        health = HEALTH_BLOCKED
    elif assigned_station_count <= 0 or not best_spatial:
        status = PORTUGUESE_AQ_INSUFFICIENT
        tier = PROXY_TIER_3
        claim = AQ_PROTOCOL_PROXY
        claim_note = AQ_PROTOCOL_PROXY_INSUFFICIENT_NOTE
        health = HEALTH_BLOCKED
    elif threshold_comparisons_present:
        status = PORTUGUESE_AQ_HEALTH_CANDIDATE
        tier = PROXY_TIER_2
        claim = AQ_PROTOCOL_ANCHORED
        claim_note = AQ_ALLOWED_CLAIM
        health = HEALTH_VALIDATED
    else:
        status = PORTUGUESE_AQ_ANCHORED
        tier = PROXY_TIER_2
        claim = AQ_PROTOCOL_ANCHORED
        claim_note = AQ_ALLOWED_CLAIM
        health = HEALTH_NOT_DECLARED

    return {
        "portuguese_aq_validation_status": status,
        "final_proxy_tier": tier,
        "aq_protocol_decision": claim,
        "claim_disposition": claim_note,
        "health_exposure_claim_status": health,
    }


def _status_specific_allowed_claim(gate: Dict[str, str]) -> str:
    status = str(gate.get("portuguese_aq_validation_status") or "").strip()
    if status == PORTUGUESE_AQ_BASE_SMOKE_BLOCKED:
        return AQ_BASE_SMOKE_BLOCKED_CLAIM
    if status in (PORTUGUESE_AQ_NO_DATA, PORTUGUESE_AQ_INVENTORIED_ONLY, PORTUGUESE_AQ_INSUFFICIENT):
        return AQ_PROXY_ONLY_CLAIM
    return AQ_ALLOWED_CLAIM


def _claim_language_sections(gate: Dict[str, str]) -> Tuple[List[str], List[str]]:
    status = str(gate.get("portuguese_aq_validation_status") or "").strip()
    if status == PORTUGUESE_AQ_BASE_SMOKE_BLOCKED:
        allowed = [
            f"- {AQ_BASE_SMOKE_BLOCKED_CLAIM}.",
            f"- The only valid OC-03C runtime conclusion is `{PORTUGUESE_AQ_BASE_SMOKE_BLOCKED}`.",
            "- No Portuguese AQ insufficiency conclusion may be drawn from this runtime.",
        ]
        forbidden = [
            f"- {AQ_FORBIDDEN_CLAIM}",
            "- Portuguese AQ is spatially insufficient for local anchoring in this runtime.",
            "- Portuguese AQ findings refute the Portuguese agency recovery data.",
        ]
        return allowed, forbidden

    if status in (PORTUGUESE_AQ_NO_DATA, PORTUGUESE_AQ_INVENTORIED_ONLY):
        allowed = [
            f"- {AQ_PROXY_ONLY_CLAIM}.",
            "- The IECH remains a prospective territorial screening index.",
            "- Portuguese AQ evidence did not justify a local AQ-anchored upgrade.",
        ]
    elif status == PORTUGUESE_AQ_INSUFFICIENT:
        allowed = [
            "- Portuguese AQ was consumed, but direct station/pollutant evidence was spatially insufficient for a local AQ anchor.",
            f"- {AQ_PROXY_ONLY_CLAIM}.",
            "- The IECH remains a prospective territorial screening index.",
        ]
    else:
        allowed = [
            f"- {AQ_ALLOWED_CLAIM}",
            "- The IECH remains a prospective territorial screening index.",
            "- The Portuguese AQ layer supports the plausibility of high smoke-score days as air-quality-relevant episodes.",
        ]

    forbidden = [
        f"- {AQ_FORBIDDEN_CLAIM}",
        "- The pipeline quantifies health exposure.",
        "- The pipeline proves WHO/EU/EPA exceedances attributable to wildfire smoke.",
        "- The pipeline estimates epidemiological risk, morbidity, mortality or clinical burden.",
    ]
    return allowed, forbidden


def write_claim_disposition(path: Path, gate: Dict[str, str]) -> None:
    allowed_lines, forbidden_lines = _claim_language_sections(gate)
    lines = [
        "# Portuguese AQ Claim Disposition",
        "",
        f"- generated: {now_iso()}",
        f"- portuguese_aq_validation_status: **{gate['portuguese_aq_validation_status']}**",
        f"- final_proxy_tier: **{gate['final_proxy_tier']}**",
        f"- aq_protocol_decision: **{gate['aq_protocol_decision']}**",
        f"- claim_disposition: {gate['claim_disposition']}",
        f"- health_exposure_claim_status: **{gate['health_exposure_claim_status']}**",
        "",
        "## Allowed language",
        *allowed_lines,
        "",
        "## Forbidden language",
        *forbidden_lines,
        "",
        "## Sanitary closure rule",
        "- Full health-exposure closure remains blocked unless concentration variables, official thresholds, territorial assignment, and smoke attribution are all explicitly audited.",
    ]
    ensure_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_path_scope_preflight(
    path: Path,
    repo_root: Path,
    output_root: Path,
    modulec_datos: Path,
    aq_root: Optional[Path],
    generated_paths: Sequence[Path],
) -> str:
    allowed_data_prefixes = _read_allowed_data_prefixes(repo_root, modulec_datos)
    allowed_output_root = repo_root.parent / "03_RUNTIMES"
    cwd = Path.cwd()
    rows: List[List[object]] = []
    blockers: List[str] = []

    def add(check_id: str, status: str, observed: object, expected: object, detail: str) -> None:
        rows.append([now_iso(), check_id, status, observed, expected, detail])
        if str(status).startswith("BLOCKED"):
            blockers.append(str(status))

    add(
        "OC03C_CWD",
        "PASS" if _is_same_or_subpath(cwd, repo_root) else "BLOCKED_PATH_SCOPE_DESYNC",
        cwd,
        repo_root,
        "Current working directory must stay inside the authorized repository.",
    )
    add(
        "OC03C_REPO_ROOT",
        "PASS" if repo_root.exists() else "BLOCKED_PATH_SCOPE_DESYNC",
        repo_root,
        "existing repo root",
        "Repository root must exist.",
    )
    add(
        "OC03C_OUTPUT_ROOT",
        "PASS" if _is_same_or_subpath(output_root, allowed_output_root) else "BLOCKED_PATH_SCOPE_DESYNC",
        output_root,
        allowed_output_root,
        "Runtime output must stay under 03_RUNTIMES.",
    )
    add(
        "OC03C_DATA_ROOT",
        "PASS" if any(_is_same_or_subpath(modulec_datos, prefix) for prefix in allowed_data_prefixes) else "BLOCKED_PATH_SCOPE_DESYNC",
        modulec_datos,
        "; ".join(str(prefix) for prefix in allowed_data_prefixes),
        "Primary data root must be one of the allowed read-only roots.",
    )
    approved_pt_aq_roots = [prefix for prefix in allowed_data_prefixes if prefix.name == PORTUGUESE_AQ_ROOT_NAME]
    approved_pt_aq_expected = "; ".join(str(prefix) for prefix in approved_pt_aq_roots) or PORTUGUESE_AQ_ROOT_NAME
    if aq_root is None:
        add(
            "OC03C_PT_AQ_ROOT",
            "BLOCKED_PATH_SCOPE_DESYNC",
            "MISSING",
            approved_pt_aq_expected,
            "Portuguese AQ root was not resolved to the approved recovery folder.",
        )
    else:
        add(
            "OC03C_PT_AQ_ROOT",
            "PASS" if _is_approved_portuguese_aq_root(aq_root, allowed_data_prefixes) else "BLOCKED_PATH_SCOPE_DESYNC",
            aq_root,
            approved_pt_aq_expected,
            "Portuguese AQ inputs must come only from the approved recovery folder.",
        )
    bad_generated = [str(item) for item in generated_paths if not _is_same_or_subpath(item, output_root)]
    add(
        "OC03C_GENERATED_TARGETS",
        "PASS" if not bad_generated else "BLOCKED_PATH_SCOPE_DESYNC",
        len(generated_paths),
        output_root,
        "Generated artifacts must stay inside the runtime output root." if not bad_generated else " | ".join(bad_generated[:6]),
    )
    data_write_hits = [
        str(item)
        for item in generated_paths
        if any(_is_same_or_subpath(item, prefix) for prefix in allowed_data_prefixes)
    ]
    add(
        "OC03C_DATA_WRITE_GUARD",
        "PASS" if not data_write_hits else "BLOCKED_PATH_SCOPE_DESYNC",
        len(data_write_hits),
        "0",
        "No OC-03C output may be written under any data root." if not data_write_hits else " | ".join(data_write_hits[:6]),
    )
    decision = "PATH_SCOPE_PASS" if not blockers else "BLOCKED_PATH_SCOPE_DESYNC"
    rows.append([now_iso(), "OC03C_SUMMARY", decision, decision, "PATH_SCOPE_PASS", "All checks passed." if decision == "PATH_SCOPE_PASS" else " | ".join(sorted(set(blockers)))])
    write_tsv(path, ["timestamp", "check_id", "status", "observed", "expected", "detail"], rows)
    return decision


def _write_empty_tsv(path: Path, header: Sequence[str]) -> None:
    write_tsv(path, header, [])


def _write_empty_csv(path: Path, header: Sequence[str]) -> None:
    write_csv(path, header, [], delim=";")


def write_blocked_base_smoke_regression_outputs(
    modulec_datos: Path,
    output_root: Path,
    repo_root: Path,
    report_log=None,
) -> Dict[str, object]:
    def log(message: str) -> None:
        if report_log is not None:
            report_log(message)

    qa_dir = output_root / "qa"
    tables_dir = output_root / "tables"
    ensure_dir(qa_dir)
    ensure_dir(tables_dir)

    allowed_data_prefixes = _read_allowed_data_prefixes(repo_root, modulec_datos)
    aq_root = resolve_portuguese_aq_root(modulec_datos)
    aq_root_approved = _is_approved_portuguese_aq_root(aq_root, allowed_data_prefixes)

    _write_empty_tsv(
        qa_dir / "portuguese_aq_input_inventory.tsv",
        ["path", "relative_path", "extension", "bytes", "classification"],
    )
    _write_empty_tsv(
        qa_dir / "portuguese_aq_file_format_audit.tsv",
        ["extension", "file_count", "supported", "detail"],
    )
    _write_empty_tsv(
        qa_dir / "portuguese_aq_station_inventory.tsv",
        ["station_id", "station_name", "latitude", "longitude", "country_code", "source_kind", "metadata_source", "aq_metadata_relevant", "municipio_id", "nuts3_id"],
    )
    _write_empty_tsv(
        qa_dir / "portuguese_aq_timeseries_inventory.tsv",
        ["file", "format", "status", "pollutant_raw", "pollutant", "unit", "station_count", "observation_rows", "layout", "datetime_field", "station_field", "value_field", "note"],
    )
    _write_empty_tsv(
        qa_dir / "portuguese_aq_normalization_audit.tsv",
        ["metric", "value", "status", "detail"],
    )
    _write_empty_tsv(
        qa_dir / "portuguese_aq_station_to_unit_assignment.tsv",
        ["station_id", "station_name", "latitude", "longitude", "municipio_id", "nuts3_id", "assignment_method", "assignment_confidence", "metadata_source", "aq_metadata_relevant"],
    )
    _write_empty_tsv(
        qa_dir / "gfas_era5_vs_portuguese_aq_concordance.tsv",
        [
            "pollutant",
            "scope",
            "matched_day_count",
            "high_gfas_day_count",
            "non_high_day_count",
            "median_pollutant_on_high_days",
            "median_pollutant_on_non_high_days",
            "delta_median",
            "spearman_correlation",
            "same_day_coincidence_count",
            "plusminus1_coincidence_count",
            "station_count",
            "unit_count",
            "concordance_signal",
        ],
    )
    _write_empty_csv(
        tables_dir / "portuguese_aq_daily_station_2015_2024.csv",
        ["station_id", "station_name", "station_key", "pollutant", "pollutant_raw", "date", "unit", "daily_value", "observation_count", "municipio_id", "nuts3_id", "assignment_method", "assignment_confidence", "source_file", "quality_status"],
    )
    _write_empty_csv(
        tables_dir / "portuguese_aq_daily_unit_2015_2024.csv",
        ["unit_level", "unit_id", "pollutant", "date", "daily_value", "station_count"],
    )
    _write_empty_csv(
        tables_dir / "smoke_proxy_aq_concordance_by_unit.csv",
        ["unit_id", "pollutant", "mean_daily_value", "same_day_high_smoke_hits"],
    )

    gate = {
        "portuguese_aq_validation_status": PORTUGUESE_AQ_BASE_SMOKE_BLOCKED,
        "final_proxy_tier": PROXY_TIER_3,
        "aq_protocol_decision": PORTUGUESE_AQ_BASE_SMOKE_BLOCKED,
        "claim_disposition": PORTUGUESE_AQ_BASE_SMOKE_BLOCKED,
        "health_exposure_claim_status": HEALTH_BLOCKED,
    }
    gate_rows = [
        ["portuguese_aq_validation_status", gate["portuguese_aq_validation_status"], "PASS", "OC-03C blocked before AQ consumption because the base smoke contract regressed."],
        ["final_proxy_tier", gate["final_proxy_tier"], "PASS", "Proxy tier remains unchanged when AQ is not consumed."],
        ["aq_protocol_decision", gate["aq_protocol_decision"], "PASS", "AQ protocol is blocked by the base smoke regression."],
        ["claim_disposition", gate["claim_disposition"], "PASS", "No AQ insufficiency conclusion is allowed when the smoke baseline regresses."],
        ["health_exposure_claim_status", gate["health_exposure_claim_status"], "PASS", "Health exposure remains blocked."],
        ["allowed_claim", _status_specific_allowed_claim(gate), "PASS", "Status-specific allowed OC-03C language."],
        ["forbidden_claim", AQ_FORBIDDEN_CLAIM, "PASS", "Forbidden wording without full sanitary evidence."],
    ]
    write_tsv(qa_dir / "portuguese_aq_validation_gate.tsv", ["metric", "value", "status", "detail"], gate_rows)
    write_claim_disposition(qa_dir / "portuguese_aq_claim_disposition.md", gate)

    generated_paths = [
        qa_dir / "portuguese_aq_input_inventory.tsv",
        qa_dir / "portuguese_aq_file_format_audit.tsv",
        qa_dir / "portuguese_aq_station_inventory.tsv",
        qa_dir / "portuguese_aq_timeseries_inventory.tsv",
        qa_dir / "portuguese_aq_normalization_audit.tsv",
        qa_dir / "portuguese_aq_station_to_unit_assignment.tsv",
        qa_dir / "gfas_era5_vs_portuguese_aq_concordance.tsv",
        qa_dir / "portuguese_aq_validation_gate.tsv",
        qa_dir / "portuguese_aq_claim_disposition.md",
        tables_dir / "portuguese_aq_daily_station_2015_2024.csv",
        tables_dir / "portuguese_aq_daily_unit_2015_2024.csv",
        tables_dir / "smoke_proxy_aq_concordance_by_unit.csv",
    ]
    path_scope_decision = write_path_scope_preflight(
        qa_dir / "oc03c_path_scope_preflight.tsv",
        repo_root=repo_root,
        output_root=output_root,
        modulec_datos=modulec_datos,
        aq_root=aq_root if aq_root_approved else None,
        generated_paths=generated_paths,
    )

    result = {
        "portuguese_aq_root": str(aq_root or ""),
        "portuguese_aq_files_discovered": 0,
        "portuguese_aq_station_files_normalized": 0,
        "portuguese_aq_timeseries_files_normalized": 0,
        "portuguese_aq_pollutants_detected": [],
        "portuguese_aq_station_count": 0,
        "portuguese_aq_daily_observation_count": 0,
        "portuguese_aq_assigned_station_count": 0,
        "portuguese_aq_matched_gfas_aq_day_count": 0,
        "portuguese_aq_concordance_rows": 0,
        "portuguese_aq_path_scope_decision": path_scope_decision,
        **gate,
    }
    log("Portuguese AQ validation blocked before AQ consumption: status=BLOCKED_BASE_SMOKE_REGRESSION")
    return result


def run_portuguese_aq_validation(
    modulec_datos: Path,
    output_root: Path,
    repo_root: Path,
    report_log=None,
) -> Dict[str, object]:
    def log(message: str) -> None:
        if report_log is not None:
            report_log(message)

    qa_dir = output_root / "qa"
    tables_dir = output_root / "tables"
    ensure_dir(qa_dir)
    ensure_dir(tables_dir)

    inputs_path = qa_dir / "inputs_resolved.json"
    inputs = {}
    if inputs_path.exists():
        try:
            inputs = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
        except Exception:
            inputs = {}

    allowed_data_prefixes = _read_allowed_data_prefixes(repo_root, modulec_datos)
    aq_root = resolve_portuguese_aq_root(modulec_datos)
    aq_root_approved = _is_approved_portuguese_aq_root(aq_root, allowed_data_prefixes)
    if aq_root is not None and not aq_root_approved:
        log(f"Portuguese AQ validation rejected out-of-scope root: {aq_root}")
    discovered_files = inventory_aq_root(aq_root if aq_root_approved else None)
    input_inventory_rows: List[List[object]] = []
    extension_counts: Counter[str] = Counter()
    for path in discovered_files:
        extension = path.suffix.lower() or "[no_ext]"
        extension_counts[extension] += 1
        input_inventory_rows.append(
            [
                str(path),
                str(path.relative_to(aq_root)) if aq_root else path.name,
                path.suffix.lower(),
                path.stat().st_size,
                _classify_file(path),
            ]
        )
    write_tsv(
        qa_dir / "portuguese_aq_input_inventory.tsv",
        ["path", "relative_path", "extension", "bytes", "classification"],
        input_inventory_rows,
    )

    format_audit_rows: List[List[object]] = []
    for extension, count in sorted(extension_counts.items()):
        supported = "YES" if extension in (".xlsx", ".csv", ".tsv", ".json", ".geojson", ".zip", ".parquet") else "NO"
        note = "actual parser wired" if extension in (".xlsx", ".csv", ".tsv", ".json", ".geojson") else "inventory only"
        format_audit_rows.append([extension, count, supported, note])
    write_tsv(qa_dir / "portuguese_aq_file_format_audit.tsv", ["extension", "file_count", "supported", "detail"], format_audit_rows)

    timeseries_meta_rows: List[Dict[str, object]] = []
    station_rows: List[Dict[str, object]] = []
    station_metadata_files: set[str] = set()
    timeseries_files_normalized = 0
    daily_station_grouped: Dict[Tuple[str, str, str, str], List[float]] = defaultdict(list)
    daily_station_sample_rows: Dict[Tuple[str, str, str, str], Dict[str, object]] = {}

    for path in discovered_files:
        lower = str(path).lower()
        try:
            if path.suffix.lower() == ".xlsx" and "manual_exports" in lower:
                meta, obs_rows, file_station_rows = parse_qualar_xlsx(path)
                timeseries_meta_rows.append(meta)
                update_daily_station_aggregates(obs_rows, daily_station_grouped, daily_station_sample_rows)
                station_rows.extend(file_station_rows)
                if str(meta.get("status")) == "PASS":
                    timeseries_files_normalized += 1
                continue
            if path.suffix.lower() in (".csv", ".tsv") and any(token in lower for token in ("aq", "qualar", "pollutant")):
                meta, obs_rows, file_station_rows = parse_generic_timeseries_table(path)
                timeseries_meta_rows.append(meta)
                update_daily_station_aggregates(obs_rows, daily_station_grouped, daily_station_sample_rows)
                station_rows.extend(file_station_rows)
                if str(meta.get("status")) == "PASS":
                    timeseries_files_normalized += 1
                continue
            if path.suffix.lower() in (".json", ".geojson"):
                file_station_rows = _extract_station_records_from_json(path)
                if file_station_rows:
                    station_rows.extend(file_station_rows)
                    if any(str(row.get("aq_metadata_relevant")) == "YES" for row in file_station_rows):
                        station_metadata_files.add(str(path))
        except Exception as exc:
            timeseries_meta_rows.append(
                {
                    "file": str(path),
                    "format": path.suffix.lower().lstrip("."),
                    "status": "FAIL_READ",
                    "pollutant_raw": "",
                    "pollutant": "",
                    "unit": "",
                    "station_count": 0,
                    "observation_rows": 0,
                    "layout": "",
                    "datetime_field": "",
                    "station_field": "",
                    "value_field": "",
                    "note": str(exc),
                }
            )

    write_tsv(
        qa_dir / "portuguese_aq_timeseries_inventory.tsv",
        [
            "file",
            "format",
            "status",
            "pollutant_raw",
            "pollutant",
            "unit",
            "station_count",
            "observation_rows",
            "layout",
            "datetime_field",
            "station_field",
            "value_field",
            "note",
        ],
        [
            [
                row.get("file", ""),
                row.get("format", ""),
                row.get("status", ""),
                row.get("pollutant_raw", ""),
                row.get("pollutant", ""),
                row.get("unit", ""),
                row.get("station_count", 0),
                row.get("observation_rows", 0),
                row.get("layout", ""),
                row.get("datetime_field", ""),
                row.get("station_field", ""),
                row.get("value_field", ""),
                row.get("note", ""),
            ]
            for row in timeseries_meta_rows
        ],
    )

    station_index: Dict[str, Dict[str, object]] = {}
    for row in station_rows:
        key = str(row.get("station_key") or "")
        if not key:
            continue
        existing = station_index.get(key)
        if existing is None:
            station_index[key] = dict(row)
            continue
        if not str(existing.get("latitude") or "").strip() and str(row.get("latitude") or "").strip():
            existing["latitude"] = row.get("latitude", "")
        if not str(existing.get("longitude") or "").strip() and str(row.get("longitude") or "").strip():
            existing["longitude"] = row.get("longitude", "")
        if str(existing.get("aq_metadata_relevant") or "NO") != "YES" and str(row.get("aq_metadata_relevant") or "NO") == "YES":
            existing["aq_metadata_relevant"] = "YES"
            existing["metadata_source"] = row.get("metadata_source", existing.get("metadata_source", ""))

    daily_station_rows = finalize_daily_station_aggregates(daily_station_grouped, daily_station_sample_rows)

    municipio_map_rows, municipio_lookup = _load_municipio_unit_map(tables_dir / "municipio_unit_map.csv")
    nuts_lookup = _load_nuts_names(output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv")
    assignment_rows: List[List[object]] = []
    assigned_station_count = 0
    assigned_keys = set()
    for key, station_row in sorted(station_index.items()):
        assignment = assign_station_name(str(station_row.get("station_name") or ""), municipio_lookup, nuts_lookup)
        if assignment["assignment_method"] != "UNASSIGNED":
            assigned_keys.add(key)
        assignment_rows.append(
            [
                station_row.get("station_id", ""),
                station_row.get("station_name", ""),
                station_row.get("latitude", ""),
                station_row.get("longitude", ""),
                assignment.get("municipio_id", ""),
                assignment.get("nuts3_id", ""),
                assignment.get("assignment_method", ""),
                assignment.get("assignment_confidence", ""),
                station_row.get("metadata_source", ""),
                station_row.get("aq_metadata_relevant", ""),
            ]
        )
        station_row.update(assignment)
    assigned_station_count = len(assigned_keys)
    write_tsv(
        qa_dir / "portuguese_aq_station_to_unit_assignment.tsv",
        [
            "station_id",
            "station_name",
            "latitude",
            "longitude",
            "municipio_id",
            "nuts3_id",
            "assignment_method",
            "assignment_confidence",
            "metadata_source",
            "aq_metadata_relevant",
        ],
        assignment_rows,
    )

    station_inventory_rows = []
    for row in sorted(station_index.values(), key=lambda item: (str(item.get("station_name") or ""), str(item.get("station_id") or ""))):
        station_inventory_rows.append(
            [
                row.get("station_id", ""),
                row.get("station_name", ""),
                row.get("latitude", ""),
                row.get("longitude", ""),
                row.get("country_code", "PT"),
                row.get("source_kind", ""),
                row.get("metadata_source", ""),
                row.get("aq_metadata_relevant", ""),
                row.get("municipio_id", ""),
                row.get("nuts3_id", ""),
            ]
        )
    write_tsv(
        qa_dir / "portuguese_aq_station_inventory.tsv",
        [
            "station_id",
            "station_name",
            "latitude",
            "longitude",
            "country_code",
            "source_kind",
            "metadata_source",
            "aq_metadata_relevant",
            "municipio_id",
            "nuts3_id",
        ],
        station_inventory_rows,
    )

    station_assignment_by_key = {
        key: {
            "municipio_id": str(row.get("municipio_id") or "").strip(),
            "nuts3_id": str(row.get("nuts3_id") or "").strip(),
            "assignment_method": str(row.get("assignment_method") or "").strip(),
            "assignment_confidence": str(row.get("assignment_confidence") or "").strip(),
        }
        for key, row in station_index.items()
    }
    for row in daily_station_rows:
        assignment = station_assignment_by_key.get(str(row.get("station_key") or ""), {})
        row.update(assignment)

    write_csv(
        tables_dir / "portuguese_aq_daily_station_2015_2024.csv",
        [
            "station_id",
            "station_name",
            "station_key",
            "pollutant",
            "pollutant_raw",
            "date",
            "unit",
            "daily_value",
            "observation_count",
            "municipio_id",
            "nuts3_id",
            "assignment_method",
            "assignment_confidence",
            "source_file",
            "quality_status",
        ],
        [
            [
                row.get("station_id", ""),
                row.get("station_name", ""),
                row.get("station_key", ""),
                row.get("pollutant", ""),
                row.get("pollutant_raw", ""),
                row.get("date", ""),
                row.get("unit", ""),
                row.get("daily_value", ""),
                row.get("observation_count", ""),
                row.get("municipio_id", ""),
                row.get("nuts3_id", ""),
                row.get("assignment_method", ""),
                row.get("assignment_confidence", ""),
                row.get("source_file", ""),
                row.get("quality_status", ""),
            ]
            for row in daily_station_rows
        ],
        delim=";",
    )

    daily_unit_grouped: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    daily_unit_meta: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    for row in daily_station_rows:
        municipio_id = str(row.get("municipio_id") or "").strip()
        nuts3_id = str(row.get("nuts3_id") or "").strip()
        if municipio_id:
            key = ("MUNICIPIO", municipio_id, str(row.get("pollutant") or ""))
            date_key = str(row.get("date") or "")
            group_key = (key[0], key[1], key[2] + "|" + date_key)
            daily_unit_grouped[group_key].append(float(row.get("daily_value") or 0.0))
            daily_unit_meta[group_key] = {"unit_level": "MUNICIPIO", "unit_id": municipio_id, "pollutant": row.get("pollutant", ""), "date": date_key}
        elif nuts3_id:
            key = ("NUTS3", nuts3_id, str(row.get("pollutant") or ""))
            date_key = str(row.get("date") or "")
            group_key = (key[0], key[1], key[2] + "|" + date_key)
            daily_unit_grouped[group_key].append(float(row.get("daily_value") or 0.0))
            daily_unit_meta[group_key] = {"unit_level": "NUTS3", "unit_id": nuts3_id, "pollutant": row.get("pollutant", ""), "date": date_key}

    daily_unit_rows: List[List[object]] = []
    for group_key, values in sorted(daily_unit_grouped.items()):
        meta = daily_unit_meta[group_key]
        daily_unit_rows.append(
            [
                meta["unit_level"],
                meta["unit_id"],
                meta["pollutant"],
                meta["date"],
                sum(values) / len(values),
                len(values),
            ]
        )
    write_csv(
        tables_dir / "portuguese_aq_daily_unit_2015_2024.csv",
        ["unit_level", "unit_id", "pollutant", "date", "daily_value", "station_count"],
        daily_unit_rows,
        delim=";",
    )

    smoke_nuts_lookup = _load_smoke_lookup(tables_dir / "smoke_day_score_nuts3_daily.csv", "NUTS3")
    smoke_muni_lookup = _load_smoke_lookup(tables_dir / "smoke_day_score_municipio_daily.csv", "MUNICIPIO")
    joined_rows, concordance_rows = build_concordance(daily_station_rows, smoke_muni_lookup, smoke_nuts_lookup)

    write_tsv(
        qa_dir / "gfas_era5_vs_portuguese_aq_concordance.tsv",
        [
            "pollutant",
            "scope",
            "matched_day_count",
            "high_gfas_day_count",
            "non_high_day_count",
            "median_pollutant_on_high_days",
            "median_pollutant_on_non_high_days",
            "delta_median",
            "spearman_correlation",
            "same_day_coincidence_count",
            "plusminus1_coincidence_count",
            "station_count",
            "unit_count",
            "concordance_signal",
        ],
        [
            [
                row.get("pollutant", ""),
                row.get("scope", ""),
                row.get("matched_day_count", 0),
                row.get("high_gfas_day_count", 0),
                row.get("non_high_day_count", 0),
                row.get("median_pollutant_on_high_days", ""),
                row.get("median_pollutant_on_non_high_days", ""),
                row.get("delta_median", ""),
                row.get("spearman_correlation", ""),
                row.get("same_day_coincidence_count", 0),
                row.get("plusminus1_coincidence_count", 0),
                row.get("station_count", 0),
                row.get("unit_count", 0),
                row.get("concordance_signal", ""),
            ]
            for row in concordance_rows
        ],
    )

    unit_concordance_rows: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    unit_concordance_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for row in joined_rows:
        pollutant = str(row.get("pollutant") or "")
        unit_id = str(row.get("municipio_id") or row.get("nuts3_id") or "").strip()
        value = safe_float(row.get("daily_value"))
        if not pollutant or not unit_id or value is None:
            continue
        unit_concordance_rows[(unit_id, pollutant)].append(value)
        unit_concordance_counts[(unit_id, pollutant)] += int(row.get("same_day_high_smoke_flag") or 0)
    write_csv(
        tables_dir / "smoke_proxy_aq_concordance_by_unit.csv",
        ["unit_id", "pollutant", "mean_daily_value", "same_day_high_smoke_hits"],
        [
            [unit_id, pollutant, sum(values) / len(values), unit_concordance_counts[(unit_id, pollutant)]]
            for (unit_id, pollutant), values in sorted(unit_concordance_rows.items())
            if values
        ],
        delim=";",
    )

    threshold_comparisons_present = False
    gate = determine_gate(
        discovered_files=len(discovered_files),
        timeseries_files_normalized=timeseries_files_normalized,
        daily_station_count=len(daily_station_rows),
        assigned_station_count=assigned_station_count,
        concordance_rows=concordance_rows,
        threshold_comparisons_present=threshold_comparisons_present,
    )

    pollutants_detected = sorted(
        {
            str(row.get("pollutant") or "").strip()
            for row in daily_station_rows
            if str(row.get("pollutant") or "").strip()
        }
    )
    matched_spatial_rows = [
        row for row in concordance_rows
        if str(row.get("scope")) == "SPATIAL_MATCHED"
    ]
    matched_gfas_aq_day_count = max([int(row.get("matched_day_count") or 0) for row in matched_spatial_rows] + [0])
    metadata_status = "INFO" if station_metadata_files else "HOLD"
    metadata_detail = "AQ-relevant station metadata files with usable records."
    if not station_metadata_files and (station_index or assigned_station_count or daily_station_rows or matched_gfas_aq_day_count):
        metadata_status = "WARN_METADATA_FORMAL_FILE_NOT_NORMALIZED"
        metadata_detail = "Formal station metadata files were not normalized, but station inventory/assignment/concordance evidence exists."
    normalization_audit_rows = [
        ["aq_root_resolved", str(aq_root or ""), "PASS" if aq_root else "HOLD", "Approved Portuguese AQ root resolution."],
        ["files_discovered", len(discovered_files), "PASS" if discovered_files else "HOLD", "Recursive inventory under approved root."],
        ["timeseries_files_normalized", timeseries_files_normalized, "PASS" if timeseries_files_normalized else "HOLD", "Timeseries files that produced observations."],
        ["station_metadata_files_normalized", len(station_metadata_files), metadata_status, metadata_detail],
        ["station_inventory_count", len(station_index), "PASS" if station_index else "HOLD", "Distinct station records."],
        ["daily_station_rows", len(daily_station_rows), "PASS" if daily_station_rows else "HOLD", "Daily pollutant observations by station."],
        ["assigned_station_count", assigned_station_count, "PASS" if assigned_station_count else "HOLD", "Stations with municipio/NUTS3 assignment."],
        ["matched_gfas_aq_day_count", matched_gfas_aq_day_count, "PASS" if matched_gfas_aq_day_count else "HOLD", "Best spatially matched concordance row count."],
        ["threshold_comparisons_present", int(threshold_comparisons_present), "INFO", "Official threshold comparison logic is not wired in OC-03C."],
        ["pollutants_detected", "|".join(pollutants_detected), "PASS" if pollutants_detected else "HOLD", "Canonical pollutants detected in normalized observations."],
    ]
    write_tsv(qa_dir / "portuguese_aq_normalization_audit.tsv", ["metric", "value", "status", "detail"], normalization_audit_rows)

    gate_rows = [
        ["portuguese_aq_validation_status", gate["portuguese_aq_validation_status"], "PASS", "OC-03C Portuguese AQ gate outcome."],
        ["final_proxy_tier", gate["final_proxy_tier"], "PASS", "Proxy tier after AQ validation."],
        ["aq_protocol_decision", gate["aq_protocol_decision"], "PASS", "Final AQ protocol language."],
        ["claim_disposition", gate["claim_disposition"], "PASS", "Allowed OC-03C claim language."],
        ["health_exposure_claim_status", gate["health_exposure_claim_status"], "PASS", "Health-exposure declaration remains blocked unless threshold logic is present."],
        ["allowed_claim", _status_specific_allowed_claim(gate), "PASS", "Status-specific allowed OC-03C language."],
        ["forbidden_claim", AQ_FORBIDDEN_CLAIM, "PASS", "Forbidden wording without full sanitary evidence."],
    ]
    write_tsv(qa_dir / "portuguese_aq_validation_gate.tsv", ["metric", "value", "status", "detail"], gate_rows)
    write_claim_disposition(qa_dir / "portuguese_aq_claim_disposition.md", gate)

    generated_paths = [
        qa_dir / "portuguese_aq_input_inventory.tsv",
        qa_dir / "portuguese_aq_file_format_audit.tsv",
        qa_dir / "portuguese_aq_station_inventory.tsv",
        qa_dir / "portuguese_aq_timeseries_inventory.tsv",
        qa_dir / "portuguese_aq_normalization_audit.tsv",
        qa_dir / "portuguese_aq_station_to_unit_assignment.tsv",
        qa_dir / "gfas_era5_vs_portuguese_aq_concordance.tsv",
        qa_dir / "portuguese_aq_validation_gate.tsv",
        qa_dir / "portuguese_aq_claim_disposition.md",
        tables_dir / "portuguese_aq_daily_station_2015_2024.csv",
        tables_dir / "portuguese_aq_daily_unit_2015_2024.csv",
        tables_dir / "smoke_proxy_aq_concordance_by_unit.csv",
    ]
    path_scope_decision = write_path_scope_preflight(
        qa_dir / "oc03c_path_scope_preflight.tsv",
        repo_root=repo_root,
        output_root=output_root,
        modulec_datos=modulec_datos,
        aq_root=aq_root,
        generated_paths=generated_paths,
    )

    result = {
        "portuguese_aq_root": str(aq_root or ""),
        "portuguese_aq_files_discovered": len(discovered_files),
        "portuguese_aq_station_files_normalized": len(station_metadata_files),
        "portuguese_aq_timeseries_files_normalized": timeseries_files_normalized,
        "portuguese_aq_pollutants_detected": pollutants_detected,
        "portuguese_aq_station_count": len(station_index),
        "portuguese_aq_daily_observation_count": len(daily_station_rows),
        "portuguese_aq_assigned_station_count": assigned_station_count,
        "portuguese_aq_matched_gfas_aq_day_count": matched_gfas_aq_day_count,
        "portuguese_aq_concordance_rows": len(concordance_rows),
        "portuguese_aq_path_scope_decision": path_scope_decision,
        **gate,
    }
    log(
        "Portuguese AQ validation completed: "
        f"status={gate['portuguese_aq_validation_status']} "
        f"timeseries_files={timeseries_files_normalized} "
        f"daily_rows={len(daily_station_rows)} "
        f"assigned_stations={assigned_station_count} "
        f"matched_days={matched_gfas_aq_day_count}"
    )
    return result
