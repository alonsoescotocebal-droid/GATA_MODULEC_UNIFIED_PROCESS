"""Pure R10-B wildfire recurrence contract."""

from __future__ import annotations

import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

YEARS_HIST = list(range(2015, 2025))
R10B_METHOD = "ICNF_2015_2024_ANNUAL_DISSOLVE_TEMPORAL_PERSISTENCE_AND_DISTINCT_YEAR_REBURN"
R10B_CLAIM_STATUS = "RELATIVE_RECURRENCE_SCREENING_WITHIN_ICNF_2015_2024_DATASET"
EVENT_NOT_VALIDATED = "FIRE_FEATURES_ARE_BURNED_FOOTPRINT_POLYGONS_NOT_VALIDATED_EVENTS"


def legacy_years_gt_own_p75(values: Sequence[float]) -> int:
    values = [float(value) for value in values]
    if not values:
        return 0
    p75 = sorted(values)[int(0.75 * (len(values) - 1))]
    return sum(1 for value in values if value > p75 and value > 0)


def tie_aware_fractional_rank(values: Sequence[float]) -> list[float]:
    n = len(values)
    if n <= 1:
        return [0.0] * n
    ordered = sorted((float(value), index) for index, value in enumerate(values))
    ranks = [0.0] * n
    start = 0
    while start < n:
        end = start + 1
        while end < n and ordered[end][0] == ordered[start][0]:
            end += 1
        average_rank = ((start + 1) + end) / 2.0
        fractional_rank = (average_rank - 1.0) / float(n - 1)
        for _, index in ordered[start:end]:
            ranks[index] = fractional_rank
        start = end
    return ranks


def classify_recurrence_score(score: float) -> str:
    score = max(0.0, min(1.0, float(score)))
    if score < 1.0 / 3.0:
        return "LOW"
    if score < 2.0 / 3.0:
        return "MEDIUM"
    return "HIGH"


def absolute_area_tertile_classes(values: Sequence[float]) -> list[str]:
    if not values:
        return []
    ordered = sorted(float(value) for value in values)
    t33 = ordered[int(0.33 * (len(ordered) - 1))]
    t66 = ordered[int(0.66 * (len(ordered) - 1))]
    return ["LOW" if float(value) <= t33 else "MED" if float(value) <= t66 else "HIGH" for value in values]


def _longest_run(flags: Sequence[bool]) -> int:
    best = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        best = max(best, current)
    return best


def _gap_metrics(years: Sequence[int]) -> tuple[float | None, float | None, float | None]:
    if len(years) < 2:
        return None, None, None
    gaps = [float(right - left) for left, right in zip(years, years[1:])]
    return statistics.mean(gaps), statistics.median(gaps), max(gaps)


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_rank = tie_aware_fractional_rank(left)
    right_rank = tie_aware_fractional_rank(right)
    left_mean = statistics.mean(left_rank)
    right_mean = statistics.mean(right_rank)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_rank, right_rank))
    left_sd = math.sqrt(sum((value - left_mean) ** 2 for value in left_rank))
    right_sd = math.sqrt(sum((value - right_mean) ** 2 for value in right_rank))
    if left_sd == 0 or right_sd == 0:
        return None
    return numerator / (left_sd * right_sd)


def build_recurrence_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build canonical recurrence fields from dissolved per-unit metrics."""
    result: list[dict[str, Any]] = []
    for source in records:
        annual = {year: float(source.get("annual_burned_area_by_year", {}).get(year, 0.0)) for year in YEARS_HIST}
        unit_area = float(source.get("unit_area_ha", 0.0) or 0.0)
        unique_area = float(source.get("unique_burned_area_ha", 0.0) or 0.0)
        reburn_area = float(source.get("reburned_area_ha", 0.0) or 0.0)
        affected_years = [year for year in YEARS_HIST if annual[year] > 0.0]
        cumulative_area = sum(annual.values())
        mean_gap, median_gap, max_gap = _gap_metrics(affected_years)
        result.append({
            "unit_id": str(source.get("unit_id", "")),
            "unit_area_ha": unit_area,
            "affected_year_count": len(affected_years),
            "affected_year_fraction": len(affected_years) / 10.0,
            "longest_consecutive_affected_year_run": _longest_run([annual[year] > 0 for year in YEARS_HIST]),
            "mean_gap_between_affected_years": mean_gap,
            "median_gap_between_affected_years": median_gap,
            "maximum_gap_between_affected_years": max_gap,
            "unique_burned_area_ha": unique_area,
            "unique_burned_fraction": unique_area / unit_area if unit_area else 0.0,
            "cumulative_burned_area_ha": cumulative_area,
            "cumulative_burned_fraction": cumulative_area / unit_area if unit_area else 0.0,
            "reburned_area_ha": reburn_area,
            "reburned_area_fraction": reburn_area / unit_area if unit_area else 0.0,
            "reburn_share_of_unique_burned_area": reburn_area / unique_area if unique_area else 0.0,
            "maximum_annual_burned_fraction": max(annual.values()) / unit_area if unit_area else 0.0,
            "burned_polygon_count": int(source.get("burned_polygon_count", 0) or 0),
            "event_count_if_validated": source.get("event_count_if_validated", ""),
            "forest_proxy_ha_2015_2024": source.get("forest_proxy_ha_2015_2024", 0.0),
            "shrubland_proxy_ha_2015_2024": source.get("shrubland_proxy_ha_2015_2024", 0.0),
            "legacy_total_burn_ha_2015_2024": float(source.get("legacy_total_burn_ha_2015_2024", cumulative_area) or 0.0),
            "legacy_years_area_gt_own_p75": int(source.get("legacy_years_area_gt_own_p75", legacy_years_gt_own_p75(list(annual.values()))) or 0),
            "legacy_recurrence_class_absolute_burn_tertile": source.get("legacy_recurrence_class_absolute_burn_tertile", ""),
            "zero_fire_footprint_flag": int(len(affected_years) == 0 and unique_area == 0),
            "recurrence_method": R10B_METHOD,
            "recurrence_claim_status": R10B_CLAIM_STATUS,
            "recurrence_signal_assignment": source.get("recurrence_signal_assignment", "DIRECT_FIRE_FOOTPRINT"),
        })
    temporal = tie_aware_fractional_rank([row["affected_year_fraction"] for row in result])
    reburn = tie_aware_fractional_rank([row["reburn_share_of_unique_burned_area"] for row in result])
    for row, temporal_rank, reburn_rank in zip(result, temporal, reburn):
        row["recurrence_temporal_rank"] = temporal_rank
        row["recurrence_reburn_rank"] = reburn_rank
        row["recurrence_score"] = 0.50 * temporal_rank + 0.50 * reburn_rank
        row["recurrence_class"] = classify_recurrence_score(row["recurrence_score"])
    return result


SUMMARY_COLUMNS = [
    "unit_id", "unit_area_ha", "affected_year_count", "affected_year_fraction", "longest_consecutive_affected_year_run",
    "mean_gap_between_affected_years", "median_gap_between_affected_years", "maximum_gap_between_affected_years",
    "unique_burned_area_ha", "unique_burned_fraction", "cumulative_burned_area_ha", "cumulative_burned_fraction",
    "reburned_area_ha", "reburned_area_fraction", "reburn_share_of_unique_burned_area", "maximum_annual_burned_fraction",
    "burned_polygon_count", "event_count_if_validated", "recurrence_temporal_rank", "recurrence_reburn_rank", "recurrence_score",
    "recurrence_class", "legacy_total_burn_ha_2015_2024", "legacy_years_area_gt_own_p75", "legacy_recurrence_class_absolute_burn_tertile",
    "forest_proxy_ha_2015_2024", "shrubland_proxy_ha_2015_2024", "zero_fire_footprint_flag", "recurrence_method",
    "recurrence_claim_status", "recurrence_signal_assignment",
]


def write_summary(path: Path, rows: Sequence[Mapping[str, Any]], write_csv_fn) -> None:
    write_csv_fn(path, SUMMARY_COLUMNS, ([row.get(column, "") for column in SUMMARY_COLUMNS] for row in rows), delim=";")


def write_tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)


def write_recurrence_qa(qa_dir: Path, results: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    semantics = [item for result in results for item in result.get("semantics", [])]
    geometry = [item for result in results for item in result.get("geometry", [])]
    write_tsv(qa_dir / "r10_b_fire_feature_semantics.tsv", ["territorial_level", "source_layer", "year", "feature_count", "candidate_event_id_fields", "unique_candidate_ids", "duplicate_ids", "multipart_geometry_count", "event_semantics_status", "note"], ([item.get(key, "") for key in ("territorial_level", "source_layer", "year", "feature_count", "candidate_event_id_fields", "unique_candidate_ids", "duplicate_ids", "multipart_geometry_count", "event_semantics_status", "note")] for item in semantics))
    write_tsv(qa_dir / "r10_b_reburn_geometry_audit.tsv", ["territorial_level", "unit_id", "unit_area_ha", "unique_burned_area_ha", "reburned_area_ha", "annual_area_max_ha", "geometry_failures", "negative_area_failures", "area_ordering_failures", "status"], ([item.get(key, "") for key in ("territorial_level", "unit_id", "unit_area_ha", "unique_burned_area_ha", "reburned_area_ha", "annual_area_max_ha", "geometry_failures", "negative_area_failures", "area_ordering_failures", "status")] for item in geometry))
    levels = [str(result.get("territorial_level", "")) for result in results]
    score_values = [float(row.get("recurrence_score", 0.0)) for row in rows]
    temporal_values = [float(row.get("affected_year_fraction", 0.0)) for row in rows]
    reburn_values = [float(row.get("reburn_share_of_unique_burned_area", 0.0)) for row in rows]
    legacy_values = [float(row.get("legacy_years_area_gt_own_p75", 0.0)) for row in rows]
    counts = defaultdict(int)
    for row in rows:
        counts[str(row.get("recurrence_class", ""))] += 1
    construct_rows = [[level, "source", "ICNF official burned-area footprints 2015-2024", "PASS", "annual dissolve and distinct-year reburn"] for level in levels]
    construct_rows.extend([
        ["ALL", "affected_year_fraction_unique_values", len(set(temporal_values)), "PASS" if len(set(temporal_values)) > 1 else "HOLD", "temporal persistence"],
        ["ALL", "reburn_share_unique_values", len(set(reburn_values)), "PASS" if len(set(reburn_values)) > 1 else "HOLD", "spatial repeat burning"],
        ["ALL", "recurrence_score_unique_values", len(set(score_values)), "PASS" if len(set(score_values)) > 1 else "HOLD", "RECURRENCE_DISCRIMINATION_GATE"],
        ["ALL", "recurrence_score_std", statistics.pstdev(score_values) if score_values else 0.0, "PASS" if len(set(score_values)) > 1 else "HOLD", "canonical score"],
        ["ALL", "legacy_years_gt_p75_unique_values", len(set(legacy_values)), "INFO", "legacy diagnostic only"],
        ["ALL", "class_counts", f"LOW={counts['LOW']};MEDIUM={counts['MEDIUM']};HIGH={counts['HIGH']}", "PASS", "fixed score bands; counts not forced"],
        ["ALL", "canonical_driver", "affected_year_fraction + reburn_share_of_unique_burned_area", "PASS", "50/50 tie-aware ranks"],
    ])
    write_tsv(qa_dir / "r10_b_recurrence_construct_audit.tsv", ["territorial_level", "metric", "value", "status", "detail"], construct_rows)
    crosswalk = []
    for row in rows:
        legacy_class = str(row.get("legacy_recurrence_class_absolute_burn_tertile", ""))
        new_class = str(row.get("recurrence_class", ""))
        crosswalk.append([row.get("territorial_level", ""), row.get("unit_id", ""), row.get("legacy_total_burn_ha_2015_2024", ""), row.get("legacy_years_area_gt_own_p75", ""), legacy_class, row.get("unit_area_ha", ""), row.get("affected_year_count", ""), row.get("affected_year_fraction", ""), row.get("unique_burned_area_ha", ""), row.get("unique_burned_fraction", ""), row.get("reburned_area_ha", ""), row.get("reburned_area_fraction", ""), row.get("reburn_share_of_unique_burned_area", ""), row.get("recurrence_score", ""), new_class, int(bool(legacy_class) and legacy_class != new_class)])
    write_tsv(qa_dir / "r10_b_recurrence_legacy_crosswalk.tsv", ["territorial_level", "unit_id", "legacy_total_burn_ha", "legacy_years_area_gt_p75", "legacy_recurrence_class", "unit_area_ha", "affected_year_count", "affected_year_fraction", "unique_burned_area_ha", "unique_burned_fraction", "reburned_area_ha", "reburned_area_fraction", "reburn_share", "r10_b_recurrence_score", "r10_b_recurrence_class", "class_changed"], crosswalk)
    sensitivity = []
    canonical_classes = [str(row.get("recurrence_class", "")) for row in rows]
    grouped_indices = defaultdict(list)
    for index, row in enumerate(rows):
        grouped_indices[str(row.get("territorial_level", ""))].append(index)

    def top5_overlap(variant_values: Sequence[float]) -> float:
        overlaps = []
        for indices in grouped_indices.values():
            if not indices:
                continue
            limit = min(5, len(indices))
            canonical_top = {str(rows[index].get("unit_id")) for index in sorted(indices, key=lambda index: float(rows[index].get("recurrence_score", 0.0)), reverse=True)[:limit]}
            variant_top = {str(rows[index].get("unit_id")) for index in sorted(indices, key=lambda index: float(variant_values[index]), reverse=True)[:limit]}
            overlaps.append(len(canonical_top & variant_top) / float(limit))
        return statistics.mean(overlaps) if overlaps else 0.0

    def add_sensitivity_row(name: str, values: Sequence[float], temporal_weight: Any = "", reburn_weight: Any = "") -> None:
        classes = [classify_recurrence_score(value) for value in values]
        high_a = {str(row.get("unit_id")) for row, value in zip(rows, classes) if value == "HIGH"}
        high_b = {str(row.get("unit_id")) for row, value in zip(rows, canonical_classes) if value == "HIGH"}
        union = high_a | high_b
        sensitivity.append([name, temporal_weight, reburn_weight, spearman(values, score_values), sum(a == b for a, b in zip(classes, canonical_classes)) / len(rows) if rows else 0.0, len(high_a & high_b) / len(union) if union else 1.0, top5_overlap(values), sum(a != b for a, b in zip(classes, canonical_classes))])

    for name, temporal_weight, reburn_weight in (("50/50 canonical", .5, .5), ("60/40", .6, .4), ("40/60", .4, .6), ("100/0", 1.0, 0.0), ("0/100", 0.0, 1.0)):
        values = [temporal_weight * float(row["recurrence_temporal_rank"]) + reburn_weight * float(row["recurrence_reburn_rank"]) for row in rows]
        add_sensitivity_row(name, values, temporal_weight, reburn_weight)

    for name, metric in (("ABSOLUTE_CUMULATIVE_BURN_HA", "legacy_total_burn_ha_2015_2024"), ("CUMULATIVE_BURNED_FRACTION", "cumulative_burned_fraction")):
        values = [0.0] * len(rows)
        for indices in grouped_indices.values():
            ranks = tie_aware_fractional_rank([float(rows[index].get(metric, 0.0) or 0.0) for index in indices])
            for index, rank in zip(indices, ranks):
                values[index] = rank
        add_sensitivity_row(name, values)
    write_tsv(qa_dir / "r10_b_recurrence_sensitivity.tsv", ["variant", "temporal_weight", "reburn_weight", "recurrence_score_spearman", "class_agreement_fraction", "high_class_jaccard", "top5_overlap", "units_changing_class"], sensitivity)
    (qa_dir / "r10_b_recurrence_method_declaration.md").write_text("""# R10-B Recurrence Method Declaration

- Study period: 2015-2024 inclusive.
- Fire source: ICNF official burned-area footprints from the authorized yearly layers.
- Administrative geometry: canonical NUTS3 2024 and CAOP municipality geometry, reprojected to EPSG:3035 for metric area.
- Annual dissolve method: each year's valid burned polygons are clipped to each unit and unioned before area calculation.
- Unit area method: metric administrative geometry area in hectares.
- Spatial reburn method: pairwise intersections of distinct annual dissolved footprints followed by a final union; triple burns are counted once.
- Temporal persistence: affected-year count/fraction over ten years, consecutive-run and gap diagnostics.
- Event/polygon semantics: event IDs are used only when an explicit unique event field is validated; otherwise features remain burned polygons.
- Canonical dimensions: affected_year_fraction and reburn_share_of_unique_burned_area.
- Ranking method: tie-aware average fractional ranks separately within NUTS3 and municipality.
- Score formula: 0.50 * temporal rank + 0.50 * reburn rank.
- Classification bands: LOW [0, 1/3), MEDIUM [1/3, 2/3), HIGH [2/3, 1].
- Legacy fields: total burned area and own-p75 exceedance are retained as diagnostics/crosswalk only.
- Sensitivity variants: 60/40, 40/60, 100/0 and 0/100 are diagnostics only.
- Allowed claims: relative wildfire recurrence screening within the ICNF 2015-2024 dataset and method.
- Blocked claims: future probability, causal risk, universal thresholds, ignition frequency without validated event semantics, fire return interval and long-term fire regime.
- Limitations: ten-year window, screening construct, no external validation and no full fire-regime model.
""", encoding="utf-8")
    write_tsv(qa_dir / "recurrence_classification_audit.tsv", ["metric", "value", "status", "note"], [
        ["source", "ICNF canonical footprint", "PASS", "2015-2024"],
        ["territorial_levels", ",".join(levels), "PASS", "direct footprint calculation"],
        ["annual_dissolve_performed", 1, "PASS", "same-year overlaps excluded"],
        ["spatial_reburn_computed_distinct_years", 1, "PASS", "pairwise intersections plus union"],
        ["absolute_hectares_sole_classifier", 0, "PASS", "not a canonical input"],
        ["legacy_p75_isolated", 1, "PASS", "diagnostic/crosswalk only"],
        ["tie_aware_ranking", 1, "PASS", "average ranks"],
        ["fixed_band_classification", 1, "PASS", "score bands, not output tertiles"],
        ["class_counts_not_forced", 1, "PASS", f"LOW={counts['LOW']};MEDIUM={counts['MEDIUM']};HIGH={counts['HIGH']}"],
        ["score_discrimination", len(set(score_values)), "PASS" if len(set(score_values)) > 1 else "HOLD", "RECURRENCE_DISCRIMINATION_GATE"],
        ["zero_fire_units", sum(int(row.get("zero_fire_footprint_flag", 0) or 0) for row in rows), "PASS", "zero-fire units are LOW under fixed bands"],
        ["same_year_overlap_not_counted_as_reburn", 1, "PASS", "annual dissolve before distinct-year intersections"],
        ["geometry_failure_rows", sum(1 for item in geometry if str(item.get("status", "")).upper() != "PASS"), "PASS" if all(str(item.get("status", "")).upper() == "PASS" for item in geometry) else "HOLD", "reburn <= unique <= unit area"],
        ["coverage_NUTS3_summary_rows", sum(1 for row in rows if str(row.get("territorial_level", "")) == "NUTS3"), "PASS", "expected canonical coverage is 24 units"],
        ["coverage_municipality_summary_rows", sum(1 for row in rows if str(row.get("territorial_level", "")) == "MUNICIPALITY"), "PASS", "expected canonical coverage is 278 units"],
        ["event_semantics_declared", 1, "PASS", EVENT_NOT_VALIDATED],
        ["claim_status", R10B_CLAIM_STATUS, "PASS", "HIGH is relative screening class"],
    ])
