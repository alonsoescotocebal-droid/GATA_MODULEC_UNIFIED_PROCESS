#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from smoke_route_selector import apply_route_meta, detect_smoke_sources, select_smoke_route


OBJECTIVE_IDS = ["OC-01", "OC-02", "OC-03", "OC-03C"] + [f"OC-{i:02d}" for i in range(4, 13)]


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_report(path: Path, lines: List[str]) -> None:
    ensure_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def _is_forbidden_smoke_output_source(path_value: Path) -> bool:
    p = str(path_value).replace("/", "\\").lower()
    return "\\03_outputs\\tables\\" in p


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    data = path.read_bytes()[:65536]
    text = data.decode("utf-8-sig", errors="replace")
    delim = ";" if text.count(";") >= text.count(",") else ","
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f, delimiter=delim)
        return list(rdr.fieldnames or []), list(rdr)


def build_inputs_from_catalog(repo_root: Path) -> Dict[str, object]:
    catalog = repo_root / "data_placeholders" / "master_inputs_for_pipeline.csv"
    if not catalog.exists():
        raise FileNotFoundError(f"Missing catalog: {catalog}")

    _header, rows = read_csv_rows(catalog)
    by_key: Dict[str, str] = {}
    for row in rows:
        key = (row.get("InputKey") or "").strip()
        value = (row.get("ResolvedPath") or "").strip()
        if key and value:
            by_key[key] = value

    fire_indexed: List[Tuple[int, str]] = []
    for k, v in by_key.items():
        if not k.startswith("paths.fire_gpkgs_tm06[") or not k.endswith("]"):
            continue
        try:
            idx = int(k[len("paths.fire_gpkgs_tm06[") : -1])
        except Exception:
            continue
        fire_indexed.append((idx, v))
    fire_gpkgs = [p for _, p in sorted(fire_indexed, key=lambda t: t[0])]

    return {
        "paths": {
            "nuts3": by_key.get("paths.nuts3", ""),
            "municipios_caop": by_key.get("paths.municipios_caop", ""),
            "smoke_csv": by_key.get("paths.smoke_csv", ""),
            "ghsl_pop": {
                "2015": by_key.get("paths.ghsl_pop.2015", ""),
                "2020": by_key.get("paths.ghsl_pop.2020", ""),
                "2025": by_key.get("paths.ghsl_pop.2025", ""),
                "2030": by_key.get("paths.ghsl_pop.2030", ""),
            },
            "fire_gpkgs_tm06": fire_gpkgs,
            "wrb_mostprobable_tm06": by_key.get("paths.wrb_mostprobable_tm06", ""),
        }
    }


def resolve_objectives_canon(repo_root: Path) -> Path:
    from_env = ""
    try:
        import os

        from_env = (os.environ.get("GATA_OBJECTIVES_CANON_PATH") or "").strip()
    except Exception:
        from_env = ""
    if from_env:
        p = Path(from_env)
        if p.exists():
            return p

    candidates = [
        repo_root / "PIPELINE_CANON_HANDOFF" / "12_OBJECTIVES_CANON_MODULEC_IECH.md",
        repo_root / "contracts" / "13_MODULEC_OBJECTIVES_CANON_IECH.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Missing objectives canon file. Expected PIPELINE_CANON_HANDOFF/12_OBJECTIVES_CANON_MODULEC_IECH.md "
        "or contracts/13_MODULEC_OBJECTIVES_CANON_IECH.md."
    )


def _load_existing_inputs(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def ensure_inputs_json(
    repo_root: Path,
    qa_dir: Path,
    canon_path: Path,
    canon_sha: str,
    modulec_datos: Path,
    report_lines: List[str],
) -> Path:
    inputs_path = qa_dir / "inputs_resolved.json"
    catalog_inputs = build_inputs_from_catalog(repo_root)
    existing = _load_existing_inputs(inputs_path)

    merged: Dict[str, object] = dict(existing) if isinstance(existing, dict) else {}
    merged_paths: Dict[str, object] = dict(merged.get("paths", {})) if isinstance(merged.get("paths", {}), dict) else {}
    catalog_paths = catalog_inputs["paths"]

    rejected_sources: List[str] = []
    old_smoke = Path(str(merged_paths.get("smoke_csv", ""))) if merged_paths.get("smoke_csv") else None
    if old_smoke is not None and old_smoke.as_posix().strip():
        if _is_forbidden_smoke_output_source(old_smoke):
            rejected_sources.append(str(old_smoke))
            report_lines.append(f"[{now_iso()}] smoke_csv rejected from prior inputs (forbidden 03_outputs source): {old_smoke}")

    merged_paths.update(catalog_paths)  # canonical overwrite from catalog
    merged["paths"] = merged_paths

    meta = dict(merged.get("meta", {})) if isinstance(merged.get("meta", {}), dict) else {}
    meta.update(
        {
            "generated_at": now_iso(),
            "generated_by": "moduleC_preflight.py",
            "objectives_canon_path": str(canon_path),
            "objectives_canon_sha256": canon_sha,
            "objectives_recognized": OBJECTIVE_IDS,
            "rejected_smoke_sources": rejected_sources,
        }
    )
    merged["meta"] = meta

    try:
        sources = detect_smoke_sources(modulec_datos, merged)
        decision = select_smoke_route(sources, decoder_available=False)
        merged = apply_route_meta(merged, sources, decision)
        report_lines.append(
            f"[{now_iso()}] smoke route preflight selected={decision.get('route_selected')} decision={decision.get('smoke_route_decision')}"
        )
    except Exception as exc:
        report_lines.append(f"[{now_iso()}] WARN smoke route preflight detection failed: {exc}")

    ensure_dir(qa_dir)
    inputs_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    report_lines.append(f"[{now_iso()}] inputs_resolved.json refreshed from catalog: {inputs_path}")
    return inputs_path


def validate_inputs(paths: Dict[str, object], report_lines: List[str]) -> List[str]:
    missing: List[str] = []
    for key in ("nuts3", "municipios_caop", "wrb_mostprobable_tm06"):
        p = Path(str(paths.get(key, "")))
        if not p.exists():
            missing.append(f"{key} -> {p}")

    smoke_path = Path(str(paths.get("smoke_csv", "")))
    if not smoke_path.exists():
        missing.append(f"smoke_csv -> {smoke_path}")
    if _is_forbidden_smoke_output_source(smoke_path):
        missing.append(f"smoke_csv forbidden source under 03_outputs/tables -> {smoke_path}")

    ghsl = paths.get("ghsl_pop", {})
    for year in ("2015", "2020", "2025", "2030"):
        p = Path(str((ghsl or {}).get(year, "")))
        if not p.exists():
            missing.append(f"ghsl_pop[{year}] -> {p}")

    fire = paths.get("fire_gpkgs_tm06", [])
    if not fire:
        missing.append("fire_gpkgs_tm06 -> []")
    else:
        for fp in fire:
            p = Path(str(fp))
            if not p.exists():
                missing.append(f"fire_gpkgs_tm06 -> {p}")

    if missing:
        report_lines.append(f"[{now_iso()}] FAIL Missing/invalid inputs count={len(missing)}")
    else:
        report_lines.append(f"[{now_iso()}] PASS Input paths validated")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=True)
    ap.add_argument("--modulec-datos", required=True)
    ap.add_argument("--inc-new", required=True)
    ap.add_argument("--output-root", required=False, default=None)
    args = ap.parse_args()

    gata_root = Path(args.gata_root)
    modulec_datos = Path(args.modulec_datos)
    inc_new = Path(args.inc_new)
    if args.output_root:
        output_root = Path(args.output_root)
    else:
        output_root = modulec_datos.parent / "03_outputs"

    qa_dir = output_root / "qa"
    report_path = qa_dir / "preflight_report.txt"
    report_lines: List[str] = []
    report_lines.append(f"[{now_iso()}] START moduleC_preflight")
    report_lines.append(f"[{now_iso()}] GATA_ROOT={gata_root}")
    report_lines.append(f"[{now_iso()}] MODULEC_DATOS={modulec_datos}")
    report_lines.append(f"[{now_iso()}] INC_NEW={inc_new}")
    report_lines.append(f"[{now_iso()}] OUTPUT_ROOT={output_root}")

    missing_core: List[str] = []
    for label, p in (
        ("GATA_ROOT", gata_root),
        ("MODULEC_DATOS", modulec_datos),
        ("INC_NEW", inc_new),
    ):
        if not p.exists():
            missing_core.append(f"{label} -> {p}")

    if missing_core:
        report_lines.append(f"[{now_iso()}] FAIL Core path missing count={len(missing_core)}")
        for item in missing_core:
            report_lines.append(f"[{now_iso()}] MISSING {item}")
        write_report(report_path, report_lines)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    try:
        canon_path = resolve_objectives_canon(repo_root)
        canon_sha = sha256_file(canon_path)
        report_lines.append(f"[{now_iso()}] PASS canon found: {canon_path}")
        report_lines.append(f"[{now_iso()}] PASS canon sha256: {canon_sha}")
    except Exception as exc:
        report_lines.append(f"[{now_iso()}] FAIL canonical objectives missing: {exc}")
        write_report(report_path, report_lines)
        return 4

    inputs_path = ensure_inputs_json(repo_root, qa_dir, canon_path, canon_sha, modulec_datos, report_lines)
    inputs = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
    missing_inputs = validate_inputs(inputs.get("paths", {}), report_lines)

    # run_preflight_bootstrap already initialized QGIS + processing before calling this script.
    try:
        import qgis.core  # type: ignore # noqa: F401
        import processing  # type: ignore # noqa: F401

        report_lines.append(f"[{now_iso()}] PASS qgis.core + processing import")
    except Exception as exc:
        report_lines.append(f"[{now_iso()}] FAIL QGIS import: {exc}")
        write_report(report_path, report_lines)
        return 3

    if missing_inputs:
        for item in missing_inputs:
            report_lines.append(f"[{now_iso()}] MISSING {item}")
        report_lines.append(f"[{now_iso()}] END HOLD preflight (missing inputs)")
        write_report(report_path, report_lines)
        return 2

    report_lines.append(f"[{now_iso()}] END PASS preflight")
    write_report(report_path, report_lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
