#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple


OBJECTIVES: List[Dict[str, object]] = [
    {
        "objective_id": "OC-01",
        "objective_name": "Base territorial NUTS3 y municipio",
        "required_database": "NUTS 2024 + CAOP 2024.1",
        "required_output": ["maps/IECH_ModuleC_master.gpkg", "qa/territorial_units_validation.tsv", "tables/municipio_unit_map.csv"],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Outputs territoriales existen y no vacíos.",
    },
    {
        "objective_id": "OC-02",
        "objective_name": "Incendios y recurrencia 2015-2024",
        "required_database": "ardida_2015..2024_TM06.gpkg",
        "required_output": ["tables/recurrence_unit_2015_2024.csv", "tables/recurrence_municipio_2015_2024.csv", "qa/fire_ingestion_audit.tsv"],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Recurrence unit+municipio presentes y auditoría de ingestión presente.",
    },
    {
        "objective_id": "OC-03",
        "objective_name": "Humo v0/v1 declarado y limpio",
        "required_database": "ParquetFiles 2017.zip + ParquetFiles 2022.zip",
        "required_output": ["tables/smoke_days_unit_2015_2024.csv", "tables/smoke_days_municipio_2015_2024.csv", "qa/smoke_route_audit.tsv"],
        "producer_script": "moduleC_preflight.py + moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Fuente humo no contaminada por 03_outputs/tables; tablas no degeneradas.",
    },
    {
        "objective_id": "OC-04",
        "objective_name": "Población GHSL",
        "required_database": "GHSL POP 2015/2020/2025/2030",
        "required_output": ["tables/pop_unit_2015_2025_2030.csv", "tables/pop_municipio_2015_2025_2030.csv", "qa/population_zonal_audit.tsv"],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Pop outputs presentes y auditoría zonal presente.",
    },
    {
        "objective_id": "OC-05",
        "objective_name": "IECH histórico 2015-2024",
        "required_database": "Smoke + GHSL",
        "required_output": [
            "tables/IECH_unit_2015_2024.csv",
            "tables/IECH_unit_2015_2024_mean.csv",
            "tables/IECH_municipio_2015_2024.csv",
            "tables/IECH_municipio_2015_2024_mean.csv",
            "qa/iech_calculation_audit.tsv",
        ],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "IECH unit+municipio presentes y no degenerados.",
    },
    {
        "objective_id": "OC-06",
        "objective_name": "Recurrencia",
        "required_database": "Incendios 2015-2024",
        "required_output": ["tables/recurrence_unit_2015_2024.csv", "tables/recurrence_municipio_2015_2024.csv", "qa/recurrence_classification_audit.tsv"],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Recurrence outputs completos + clasificación auditada.",
    },
    {
        "objective_id": "OC-07",
        "objective_name": "WUI / territorio",
        "required_database": "GHSL built + proxies combustible",
        "required_output": ["tables/territorial_context_nuts3.csv", "tables/territorial_context_municipio.csv", "qa/territorial_variables_audit.tsv"],
        "producer_script": "step7_matriz_causal.py",
        "validation_rule": "Contexto territorial existe y WUI no está totalmente vacío.",
    },
    {
        "objective_id": "OC-08",
        "objective_name": "WRB integrado como contexto",
        "required_database": "WRB_MostProbable_TM06.tif (+ lookup)",
        "required_output": ["tables/wrb_context_nuts3.csv", "tables/wrb_context_municipio.csv", "qa/wrb_integration_audit.tsv", "brief/wrb_summary_for_policy_brief.md"],
        "producer_script": "step7_matriz_causal.py",
        "validation_rule": "WRB con clases dominantes y sin missing generalizado.",
    },
    {
        "objective_id": "OC-09",
        "objective_name": "Matriz causal sustantiva",
        "required_database": "Outputs IECH/smoke/pop/recurrence/WRB/WUI",
        "required_output": [
            "brief/causal_matrix/causal_matrix_IECH_NUTS3.csv",
            "brief/causal_matrix/causal_matrix_IECH_NUTS3.json",
            "brief/causal_matrix/causal_matrix_IECH_NUTS3.txt",
            "brief/causal_matrix/causal_matrix_IECH_municipio.csv",
            "brief/causal_matrix/causal_matrix_audit.tsv",
            "brief/causal_matrix/causal_matrix_sha256_checkpoints.txt",
        ],
        "producer_script": "step7_matriz_causal.py",
        "validation_rule": "No qa_flag=HOLD y missing_components vacío para cierre GO.",
    },
    {
        "objective_id": "OC-10",
        "objective_name": "Escenarios S0/S1 2026-2030",
        "required_database": "GHSL 2025/2030 + supuestos S1",
        "required_output": [
            "tables/IECH_scenarios_2026_2030.csv",
            "tables/IECH_scenarios_unit_2026_2030_mean.csv",
            "tables/IECH_scenarios_municipio_2026_2030.csv",
            "tables/IECH_scenarios_municipio_2026_2030_mean.csv",
            "qa/scenario_assumptions.md",
            "qa/scenario_audit.tsv",
        ],
        "producer_script": "moduleC_pipeline_v2.py + step7_matriz_causal.py",
        "validation_rule": "Escenarios completos + auditoría presente.",
    },
    {
        "objective_id": "OC-11",
        "objective_name": "Brief de política",
        "required_database": "Outputs científicos integrados",
        "required_output": ["brief/Brief_Politica_IECH_2030.md"],
        "producer_script": "step7_matriz_causal.py + step8",
        "validation_rule": "Brief sustantivo sin placeholders.",
    },
    {
        "objective_id": "OC-12",
        "objective_name": "Cierre técnico reproducible",
        "required_database": "Pipeline completo + Step8 + Step9",
        "required_output": [
            "qa/inputs_resolved.json",
            "qa/run_log.txt",
            "qa/QA_checks.csv",
            "qa/report_auditoria_v2.txt",
            "qa/preflight_report.txt",
            "qa/objectives_canon_alignment_report.tsv",
            "qa/objectives_canon_alignment_report.md",
            "deliverables_step9/final_manifest.json",
            "deliverables_step9/final_sha256_checkpoints.txt",
            "deliverables_step9/ModuleC_ALL_FINAL_deliverables.zip",
            "deliverables_step9/runtime_closure_decision.md",
        ],
        "producer_script": "wrapper + qa_gate_v2.py + step9",
        "validation_rule": "Artefactos de cierre frescos y paquete final completo.",
    },
]


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def sniff_delim(path: Path) -> str:
    data = path.read_bytes()[:65536]
    text = data.decode("utf-8-sig", errors="replace")
    counts = {";": text.count(";"), ",": text.count(","), "\t": text.count("\t")}
    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else ","


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    delim = sniff_delim(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delim))


def safe_float(v: object):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "na", "none", "null"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def find_canon_path(repo_root: Path, inputs: Dict[str, object]) -> Path:
    meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
    if isinstance(meta, dict):
        p_raw = str(meta.get("objectives_canon_path", "")).strip()
        p = Path(p_raw) if p_raw else None
        if p is not None and p.exists():
            return p
    env_p = (os.environ.get("GATA_OBJECTIVES_CANON_PATH") or "").strip()
    if env_p:
        p = Path(env_p)
        if p.exists():
            return p
    for cand in [
        repo_root / "PIPELINE_CANON_HANDOFF" / "12_OBJECTIVES_CANON_MODULEC_IECH.md",
        repo_root / "contracts" / "13_MODULEC_OBJECTIVES_CANON_IECH.md",
    ]:
        if cand.exists():
            return cand
    raise FileNotFoundError("Objectives canon file not found.")


def validate_required_outputs(output_root: Path, required: List[str]) -> Tuple[bool, str]:
    missing: List[str] = []
    empty: List[str] = []
    for rel in required:
        p = output_root / rel
        if not p.exists():
            missing.append(rel)
            continue
        if p.is_file() and p.stat().st_size <= 0:
            empty.append(rel)
    if missing:
        return False, "Missing outputs: " + ", ".join(missing)
    if empty:
        return False, "Empty outputs: " + ", ".join(empty)
    return True, ""


def _check_smoke_inputs_clean(inputs: Dict[str, object]) -> Tuple[bool, str]:
    paths = inputs.get("paths", {}) if isinstance(inputs, dict) else {}
    smoke = Path(str((paths or {}).get("smoke_csv", "")))
    if not smoke.exists():
        return False, f"smoke_csv missing: {smoke}"
    smoke_norm = str(smoke).replace("/", "\\").lower()
    if "\\03_outputs\\tables\\" in smoke_norm:
        return False, f"smoke_csv contaminated: {smoke}"
    if "parquetfiles" not in smoke.name.lower() and smoke.suffix.lower() not in (".zip", ".parquet"):
        return True, f"smoke_csv unusual source (accepted with warning): {smoke}"
    return True, f"smoke_csv source OK: {smoke}"


def _check_wrb_quality(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "tables" / "wrb_context_nuts3.csv"
    if not p.exists():
        return False, "wrb_context_nuts3.csv missing."
    rows = read_csv_rows(p)
    if not rows:
        return False, "wrb_context_nuts3.csv empty."
    n_total = len(rows)
    n_missing = 0
    n_dom = 0
    for r in rows:
        miss = safe_float(r.get("wrb_missing_flag"))
        if miss is not None and miss >= 1:
            n_missing += 1
        if (r.get("dominant_wrb_class") or "").strip() != "":
            n_dom += 1
    if n_missing >= n_total:
        return False, f"WRB missing generalized: {n_missing}/{n_total} with wrb_missing_flag=1"
    if n_dom <= 0:
        return False, "No dominant_wrb_class populated."
    return True, f"WRB quality OK: dominant classes={n_dom}/{n_total}, missing={n_missing}/{n_total}"


def _check_wui_quality(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "tables" / "territorial_context_nuts3.csv"
    if not p.exists():
        return False, "territorial_context_nuts3.csv missing."
    rows = read_csv_rows(p)
    if not rows:
        return False, "territorial_context_nuts3.csv empty."
    n_total = len(rows)
    n_nonempty = 0
    for r in rows:
        if safe_float(r.get("wui_proxy")) is not None:
            n_nonempty += 1
    if n_nonempty <= 0:
        return False, "WUI proxy empty for all units."
    return True, f"WUI coverage OK: non-empty={n_nonempty}/{n_total}"


def _check_causal_quality(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "brief" / "causal_matrix" / "causal_matrix_IECH_NUTS3.csv"
    if not p.exists():
        return False, "causal_matrix_IECH_NUTS3.csv missing."
    rows = read_csv_rows(p)
    if not rows:
        return False, "causal_matrix_IECH_NUTS3.csv empty."
    n_hold = 0
    n_missing_comp = 0
    for r in rows:
        if (r.get("qa_flag") or "").strip().upper() == "HOLD":
            n_hold += 1
        if (r.get("missing_components") or "").strip() != "":
            n_missing_comp += 1
    if n_hold > 0 or n_missing_comp > 0:
        return False, f"Causal matrix unresolved: qa_flag=HOLD {n_hold}, missing_components non-empty {n_missing_comp}"
    return True, "Causal matrix has no HOLD/missing_components."


def _check_brief_quality(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "brief" / "Brief_Politica_IECH_2030.md"
    if not p.exists():
        return False, "Brief missing."
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    if re.search(r"Line\s+\d{3}:\s+IECH pipeline v2 audit detail line", text, flags=re.IGNORECASE):
        return False, "Brief contains placeholder lines."
    if len(text.strip()) < 1200:
        return False, "Brief too short."
    return True, "Brief quality checks passed."


def _check_step9_zip_contents(output_root: Path) -> Tuple[bool, str]:
    p = output_root / "deliverables_step9" / "ModuleC_ALL_FINAL_deliverables.zip"
    if not p.exists():
        return False, "Final ZIP missing."
    required_member_tokens = [
        "qa/inputs_resolved.json",
        "qa/run_log.txt",
        "tables/IECH_unit_2015_2024.csv",
        "tables/IECH_municipio_2015_2024.csv",
        "tables/wrb_context_nuts3.csv",
        "tables/territorial_context_nuts3.csv",
        "brief/Brief_Politica_IECH_2030.md",
        "brief/causal_matrix/causal_matrix_IECH_NUTS3.csv",
        "maps/IECH_ModuleC_master.gpkg",
    ]
    with zipfile.ZipFile(p, "r") as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
    missing = [tok for tok in required_member_tokens if not any(n.endswith(tok) for n in names)]
    if missing:
        return False, "Final ZIP missing direct members: " + ", ".join(missing)
    return True, "Final ZIP contains direct scientific outputs."


def objective_specific_check(obj_id: str, output_root: Path, inputs: Dict[str, object]) -> Tuple[bool, str]:
    if obj_id == "OC-03":
        ok, reason = _check_smoke_inputs_clean(inputs)
        if not ok:
            return ok, reason
        meta = inputs.get("meta", {}) if isinstance(inputs, dict) else {}
        if isinstance(meta, dict):
            route_selected = str(meta.get("smoke_route_selected") or meta.get("smoke_route_mode") or "").strip()
            route_decision = str(meta.get("smoke_route_decision") or "").strip()
            if route_selected in ("BLOCKED_DECODER_REQUIRED", "v0_parquet_proxy_degraded", "NO-GO_SMOKE_ROUTE"):
                return False, f"smoke route blocked/degraded: route_selected={route_selected}; route_decision={route_decision}"
        smoke_unit = output_root / "tables" / "smoke_days_unit_2015_2024.csv"
        rows = read_csv_rows(smoke_unit) if smoke_unit.exists() else []
        vals = [safe_float(r.get("smoke_days")) for r in rows]
        vals = [v for v in vals if v is not None]
        if not vals:
            return False, "smoke_days table has no numeric values."
        if max(vals) <= 0:
            return False, "smoke_days table degenerate (max <= 0)."
        return True, reason
    if obj_id == "OC-07":
        return _check_wui_quality(output_root)
    if obj_id == "OC-08":
        return _check_wrb_quality(output_root)
    if obj_id == "OC-09":
        return _check_causal_quality(output_root)
    if obj_id == "OC-11":
        return _check_brief_quality(output_root)
    if obj_id == "OC-12":
        return _check_step9_zip_contents(output_root)
    return True, ""


def write_reports(qa_dir: Path, rows: List[Dict[str, str]], canon_path: Path, canon_sha: str) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = qa_dir / "objectives_canon_alignment_report.tsv"
    md_path = qa_dir / "objectives_canon_alignment_report.md"
    sha_path = qa_dir / "objectives_canon_sha256.txt"

    header = [
        "objective_id",
        "objective_name",
        "required_database",
        "required_output",
        "producer_script",
        "validation_rule",
        "status",
        "evidence_path",
        "failure_reason",
    ]
    with tsv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    md_lines = [
        "# Objectives Canon Alignment Report",
        "",
        f"- Generated: {now_iso()}",
        f"- Canon path: `{canon_path}`",
        f"- Canon SHA256: `{canon_sha}`",
        "",
        "| objective_id | objective_name | status | failure_reason | evidence_path |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        md_lines.append(
            f"| {r['objective_id']} | {r['objective_name']} | {r['status']} | {r['failure_reason']} | {r['evidence_path']} |"
        )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    sha_path.write_text(
        "OBJECTIVES_CANON_SHA256\n"
        f"timestamp={now_iso()}\n"
        f"path={canon_path}\n"
        f"sha256={canon_sha}\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--repo-root", required=False, default=None)
    ap.add_argument("--mode", required=False, choices=["pre", "post"], default="post")
    args = ap.parse_args()

    output_root = Path(args.output_root)
    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[1]
    qa_dir = output_root / "qa"
    inputs_path = qa_dir / "inputs_resolved.json"
    inputs: Dict[str, object] = {}
    if inputs_path.exists():
        try:
            inputs = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
        except Exception:
            inputs = {}

    try:
        canon_path = find_canon_path(repo_root, inputs)
    except Exception as exc:
        canon_path = Path("MISSING_CANON")
        canon_sha = ""
        rows = []
        for o in OBJECTIVES:
            rows.append(
                {
                    "objective_id": str(o["objective_id"]),
                    "objective_name": str(o["objective_name"]),
                    "required_database": str(o["required_database"]),
                    "required_output": "|".join(list(o["required_output"])),
                    "producer_script": str(o["producer_script"]),
                    "validation_rule": str(o["validation_rule"]),
                    "status": "HOLD",
                    "evidence_path": str(output_root / "qa"),
                    "failure_reason": f"Missing canon: {exc}",
                }
            )
        write_reports(qa_dir, rows, canon_path, canon_sha)
        print("HOLD objectives canon missing.")
        return 3

    canon_sha = sha256_file(canon_path)

    rows: List[Dict[str, str]] = []
    for obj in OBJECTIVES:
        obj_id = str(obj["objective_id"])
        required = list(obj["required_output"])
        req_ok, req_reason = validate_required_outputs(output_root, required) if args.mode == "post" else (True, "")

        status = "PASS"
        failure = ""
        spec_ok = True
        spec_reason = ""
        if args.mode == "post":
            if not req_ok:
                status = "HOLD"
                failure = req_reason
            else:
                spec_ok, spec_reason = objective_specific_check(obj_id, output_root, inputs)
                if not spec_ok:
                    status = "HOLD"
                    failure = spec_reason
        else:
            # pre-run gate: assert canon availability and input registration readiness only
            if obj_id in ("OC-03",):
                has_smoke = False
                try:
                    has_smoke = bool(((inputs.get("paths", {}) if isinstance(inputs, dict) else {}) or {}).get("smoke_csv"))
                except Exception:
                    has_smoke = False
                if has_smoke:
                    spec_ok, spec_reason = _check_smoke_inputs_clean(inputs)
                    if not spec_ok:
                        status = "HOLD"
                        failure = spec_reason
                else:
                    spec_reason = "inputs_resolved pending preflight refresh"

        if status == "PASS" and args.mode == "pre":
            status = "PRECHECK_PASS"
            failure = spec_reason or "Canon + preconditions checked."
        elif status == "PASS":
            failure = spec_reason or "Validated."

        rows.append(
            {
                "objective_id": obj_id,
                "objective_name": str(obj["objective_name"]),
                "required_database": str(obj["required_database"]),
                "required_output": "|".join(required),
                "producer_script": str(obj["producer_script"]),
                "validation_rule": str(obj["validation_rule"]),
                "status": status,
                "evidence_path": str(output_root),
                "failure_reason": failure,
            }
        )

    write_reports(qa_dir, rows, canon_path, canon_sha)

    hold_rows = [r for r in rows if r["status"] == "HOLD"]
    if hold_rows:
        print(f"HOLD objectives alignment. count={len(hold_rows)} mode={args.mode}")
        for r in hold_rows:
            print(f"{r['objective_id']}: {r['failure_reason']}")
        return 2

    print(f"PASS objectives alignment. mode={args.mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
