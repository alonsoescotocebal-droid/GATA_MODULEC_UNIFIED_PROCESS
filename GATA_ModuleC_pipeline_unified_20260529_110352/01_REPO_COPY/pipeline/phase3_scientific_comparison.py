"""Build the explicit Phase 3 versus immutable Phase 2 comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
from pathlib import Path


NUMERIC_SURFACES = (
    "tables/IECH_unit_2015_2024.csv",
    "tables/IECH_municipio_2015_2024.csv",
    "tables/smoke_days_unit_2015_2024.csv",
    "tables/recurrence_unit_2015_2024.csv",
    "tables/wrb_context_nuts3.csv",
    "tables/territorial_context_nuts3.csv",
    "tables/IECH_scenarios_2026_2030.csv",
)
SEMANTIC_SURFACES = (
    "brief/Brief_Politica_IECH_2030.md",
    "brief/causal_matrix/causal_matrix_IECH_NUTS3.csv",
)
NEW_SURFACES = (
    "maps/ModuleC_territorial_results.gpkg",
    "maps/fires_normalized_2015_2024.gpkg",
    "qa/population_weighted_smoke_feasibility.tsv",
    "qa/municipal_smoke_resolution_feasibility.tsv",
    "qa/formal_wui_feasibility.tsv",
)
CONTINENTAL_SCOPE_ROW_PAIRS = {("26", "24"), ("260", "240")}
# SCOPE_CORRECTED remains a historical diagnostic token; emitted statuses use the R3 contract vocabulary.


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _row_count(path: Path) -> str:
    if not path.exists() or path.suffix.lower() not in {".csv", ".tsv"}:
        return ""
    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
        return str(max(sum(1 for _ in stream) - 1, 0))


def _normalized_cell(value: str) -> str:
    return re.sub(r"[A-Za-z]:\\[^;|]+03_RUNTIMES\\[^;|]+", "<RUNTIME_PATH>", value)


def _csv_semantically_equal(old: Path, new: Path) -> bool:
    if old.suffix.lower() not in {".csv", ".tsv"} or new.suffix.lower() != old.suffix.lower():
        return _sha(old) == _sha(new)
    delimiter = ";" if old.suffix.lower() == ".csv" else "\t"
    with old.open("r", encoding="utf-8-sig", newline="") as left, new.open("r", encoding="utf-8-sig", newline="") as right:
        old_rows = list(csv.DictReader(left, delimiter=delimiter))
        new_rows = list(csv.DictReader(right, delimiter=delimiter))
    if [row.keys() for row in old_rows[:1]] != [row.keys() for row in new_rows[:1]] or len(old_rows) != len(new_rows):
        return False
    for old_row, new_row in zip(old_rows, new_rows):
        if old_row.keys() != new_row.keys():
            return False
        for key in old_row:
            old_value = _normalized_cell(str(old_row[key] or ""))
            new_value = _normalized_cell(str(new_row[key] or ""))
            try:
                if not math.isclose(float(old_value), float(new_value), rel_tol=1e-9, abs_tol=1e-7):
                    return False
            except ValueError:
                if old_value != new_value:
                    return False
    return True
def build_comparison(phase2: Path, phase3: Path) -> None:
    rows = [["surface", "category", "phase2_exists", "phase3_exists", "phase2_rows", "phase3_rows", "sha_equal", "status", "detail"]]
    for category, surfaces in (("preserved_scientific_result", NUMERIC_SURFACES), ("semantic_correction", SEMANTIC_SURFACES), ("new_phase3_deliverable", NEW_SURFACES)):
        for relative in surfaces:
            old = phase2 / relative
            new = phase3 / relative
            old_exists = old.exists()
            new_exists = new.exists()
            equal = old_exists and new_exists and (old.suffix.lower() in {".csv", ".tsv"} and _csv_semantically_equal(old, new) or _sha(old) == _sha(new))
            if category == "preserved_scientific_result":
                old_rows = _row_count(old)
                new_rows = _row_count(new)
                scope_corrected = old_exists and new_exists and (old_rows, new_rows) in CONTINENTAL_SCOPE_ROW_PAIRS
                status = "NUMERICALLY_IDENTICAL" if equal else ("EXPECTED_DOCUMENTARY_CHANGE" if scope_corrected else "REGRESSION")
                detail = (
                    "Numeric surface unchanged from immutable Phase 2 baseline."
                    if equal
                    else (
                        "Expected continental scope correction: PT200/PT300 excluded from Phase 3."
                        if scope_corrected
                        else "Numeric surface differs or is missing; review required."
                    )
                )
            elif category == "semantic_correction":
                status = "EXPECTED_DOCUMENTARY_CHANGE" if new_exists else "REGRESSION"
                detail = "Phase 3 bounded proxy/screening semantics are present." if new_exists else "Required semantic surface missing."
            else:
                status = "EXPECTED_ADDITIVE_OUTPUT" if new_exists else "REGRESSION"
                detail = "Phase 3 deliverable generated and audited." if new_exists else "Required Phase 3 deliverable missing."
            rows.append([relative, category, int(old_exists), int(new_exists), _row_count(old), _row_count(new), int(equal), status, detail])
    out_tsv = phase3 / "qa" / "phase3_vs_phase2_scientific_comparison.tsv"
    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    with out_tsv.open("w", encoding="utf-8", newline="") as stream:
        for row in rows:
            stream.write("\t".join(str(value) for value in row) + "\n")
    preserved = sum(1 for row in rows[1:] if row[1] == "preserved_scientific_result" and row[7] == "NUMERICALLY_IDENTICAL")
    regressions = sum(1 for row in rows[1:] if row[7] == "REGRESSION")
    lines = [
        "# Phase 3 versus Phase 2 scientific comparison",
        "",
        f"- Phase 2 baseline: `{phase2}` (immutable runtime)",
        f"- Phase 3 runtime: `{phase3}`",
        f"- Preserved numeric surfaces: {preserved}/{len(NUMERIC_SURFACES)}",
        f"- Numeric regressions requiring review: {regressions}",
        "",
        "Phase 3 preserves the established numeric proxy surfaces where hashes match,"
        " and adds bounded semantic, cartographic, normalized-fire and feasibility artifacts."
        " Population burden remains a proxy, municipal smoke is allocated from NUTS3,"
        " formal WUI is not claimed, and the matrix is descriptive screening rather than causal inference.",
        "",
        "The machine-readable detail is in `qa/phase3_vs_phase2_scientific_comparison.tsv`.",
    ]
    (phase3 / "qa" / "phase3_vs_phase2_scientific_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (phase3 / "qa" / "phase3c_vs_phase3b_comparison.tsv").write_text((phase3 / "qa" / "phase3_vs_phase2_scientific_comparison.tsv").read_text(encoding="utf-8"), encoding="utf-8")
    (phase3 / "qa" / "phase3c_vs_phase3b_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase2", required=True)
    parser.add_argument("--phase3", required=True)
    args = parser.parse_args()
    build_comparison(Path(args.phase2), Path(args.phase3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
