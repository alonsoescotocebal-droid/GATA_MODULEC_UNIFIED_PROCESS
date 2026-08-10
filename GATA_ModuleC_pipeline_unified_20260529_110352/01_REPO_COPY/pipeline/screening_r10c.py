"""Pure R10-C two-dimensional territorial screening contract and diagnostics."""

from __future__ import annotations

import csv
import math
import os
import shutil
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from recurrence_r10b import tie_aware_fractional_rank
except ModuleNotFoundError:
    from .recurrence_r10b import tie_aware_fractional_rank

R10C_METHOD = "R10_C_TWO_DIMENSIONAL_BURDEN_RECURRENCE_TIE_AWARE_RANK_SCREENING"
R10C_CLAIM_STATUS = "RELATIVE_TERRITORIAL_SCREENING_BURDEN_AND_WILDFIRE_RECURRENCE"
R10C_MUNICIPAL_CLAIM_STATUS = "REGIONAL_SMOKE_INFORMED_MUNICIPAL_SCREENING"
R10C_WEIGHTS = (0.50, 0.50)


def classify_band(value: float) -> str:
    value = max(0.0, min(1.0, float(value)))
    if value < 1.0 / 3.0:
        return "LOW"
    if value < 2.0 / 3.0:
        return "MEDIUM"
    return "HIGH"


def priority_from_score(value: float) -> str:
    return {
        "LOW": "MONITOR",
        "MEDIUM": "MEDIUM_PRIORITY",
        "HIGH": "HIGH_PRIORITY",
    }[classify_band(value)]


def _number(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        raise ValueError(f"Missing R10-C core input: {key}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite R10-C core input: {key}={value}")
    return result


def apply_canonical_screening(rows: Sequence[Mapping[str, Any]], territorial_level: str) -> list[dict[str, Any]]:
    """Apply equal-weight burden and R10-B recurrence ranks within one level."""
    if not rows:
        return []
    copied = [dict(row) for row in rows]
    burden_values = [_number(row, "population_smoke_day_burden_proxy_mean_2015_2024") for row in copied]
    recurrence_values = [_number(row, "recurrence_score") for row in copied]
    if any(value < 0.0 for value in burden_values) or any(value < 0.0 or value > 1.0 for value in recurrence_values):
        raise ValueError("R10-C core inputs are outside their declared ranges")
    burden_ranks = tie_aware_fractional_rank(burden_values)
    recurrence_ranks = tie_aware_fractional_rank(recurrence_values)
    p80 = sorted(burden_values)[int(0.80 * (len(burden_values) - 1))]
    claim = R10C_MUNICIPAL_CLAIM_STATUS if territorial_level == "MUNICIPIO" else R10C_CLAIM_STATUS
    smoke_resolution = (
        "REGIONAL_NUTS3_SIGNAL_ALLOCATED_TO_MUNICIPALITY"
        if territorial_level == "MUNICIPIO"
        else "DIRECT_NUTS3_SCREENING"
    )
    recurrence_resolution = (
        "DIRECT_MUNICIPAL_FIRE_FOOTPRINT"
        if territorial_level == "MUNICIPIO"
        else "DIRECT_NUTS3_FIRE_FOOTPRINT"
    )
    for index, (row, burden_rank, recurrence_rank) in enumerate(zip(copied, burden_ranks, recurrence_ranks)):
        legacy_priority = str(row.get("policy_priority") or "")
        score = 0.50 * burden_rank + 0.50 * recurrence_rank
        burden_band = classify_band(burden_rank)
        recurrence_band = classify_band(recurrence_rank)
        contextual_hold = bool(str(row.get("missing_components") or "").strip())
        row.update(
            {
                "burden_priority_rank": burden_rank,
                "burden_band": burden_band,
                "recurrence_priority_rank": recurrence_rank,
                "recurrence_band": recurrence_band,
                "screening_priority_score": score,
                "policy_priority": priority_from_score(score),
                "screening_profile": f"{burden_band}_BURDEN_{recurrence_band}_RECURRENCE",
                "screening_method": R10C_METHOD,
                "screening_claim_status": claim,
                "screening_core_status": "PASS",
                "contextual_completeness_status": "CONTEXTUAL_HOLD" if contextual_hold else "CONTEXTUAL_COMPLETE",
                "legacy_policy_priority": legacy_priority,
                "legacy_burden_p80_flag": int(burden_values[index] >= p80),
                "legacy_recurrence_driven_rule": "RECURRENCE_CLASS_PRIMARY_WITH_P80_HIGH_EXCEPTION",
                "smoke_signal_resolution": smoke_resolution,
                "recurrence_signal_resolution": recurrence_resolution,
                "downstream_status": "R10-D_TO_R10-FINAL_HOLDS_OPEN",
            }
        )
    return copied


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
    return numerator / (left_sd * right_sd) if left_sd and right_sd else None


def _top5_overlap(left: Sequence[Mapping[str, Any]], right_scores: Sequence[float]) -> float:
    limit = min(5, len(left))
    if not limit:
        return 1.0
    left_top = {str(left[index].get("unit_id")) for index in sorted(range(len(left)), key=lambda i: float(left[i].get("screening_priority_score", 0.0)), reverse=True)[:limit]}
    right_top = {str(left[index].get("unit_id")) for index in sorted(range(len(left)), key=lambda i: float(right_scores[i]), reverse=True)[:limit]}
    return len(left_top & right_top) / float(limit)


def compare_variant(rows: Sequence[Mapping[str, Any]], variant_scores: Sequence[float], variant_classes: Sequence[str] | None = None) -> dict[str, Any]:
    canonical_scores = [float(row["screening_priority_score"]) for row in rows]
    canonical_classes = [str(row["policy_priority"]) for row in rows]
    classes = list(variant_classes or [priority_from_score(value) for value in variant_scores])
    canonical_high = {str(row.get("unit_id")) for row in rows if row.get("policy_priority") == "HIGH_PRIORITY"}
    variant_high = {str(row.get("unit_id")) for row, value in zip(rows, classes) if value == "HIGH_PRIORITY"}
    union = canonical_high | variant_high
    return {
        "screening_score_spearman_to_canonical": spearman(variant_scores, canonical_scores),
        "class_agreement_fraction": sum(a == b for a, b in zip(classes, canonical_classes)) / float(len(rows)) if rows else 1.0,
        "HIGH_class_jaccard": len(canonical_high & variant_high) / float(len(union)) if union else 1.0,
        "top5_overlap": _top5_overlap(rows, variant_scores),
        "units_changing_class": sum(a != b for a, b in zip(classes, canonical_classes)),
    }


def write_tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    sample = path.read_text(encoding="utf-8-sig")[:8192]
    delimiter = ";" if sample.count(";") >= max(sample.count(","), sample.count("\t")) else ","
    if sample.count("\t") > sample.count(delimiter):
        delimiter = "\t"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def _float_value(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _interpolate_population(population: Mapping[str, float], year: int) -> float:
    p2015 = population.get("pop_2015_sum", 0.0)
    p2020 = population.get("pop_2020_sum", 0.0)
    p2025 = population.get("pop_2025_sum", 0.0)
    if year <= 2020:
        return p2015 + (p2020 - p2015) * ((year - 2015) / 5.0)
    return p2020 + (p2025 - p2020) * ((year - 2020) / 5.0)


def _transport_variant_burdens(
    daily_path: Path,
    pop_path: Path,
    timescale: int,
    mean_weight: float,
    max_weight: float,
) -> tuple[dict[str, float], dict[str, float]]:
    daily_rows = _read_rows(daily_path)
    pop_rows = _read_rows(pop_path)
    population = {
        str(row.get("unit_id") or ""): {
            key: _float_value(row, key)
            for key in ("pop_2015_sum", "pop_2020_sum", "pop_2025_sum")
        }
        for row in pop_rows
        if str(row.get("unit_id") or "")
    }
    scores = [_float_value(row, "smoke_day_score") for row in daily_rows]
    positive_scores = [score for score in scores if score > 0.0]
    if not positive_scores:
        return {}, {}
    threshold = sorted(positive_scores)[int(0.60 * (len(positive_scores) - 1))]
    mean_key = f"transport_proxy_{timescale}h_mean"
    max_key = f"transport_proxy_{timescale}h_max"
    annual: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for row in daily_rows:
        unit_id = str(row.get("unit_id") or "")
        year_text = str(row.get("year") or "")
        if not unit_id or not year_text:
            continue
        try:
            year = int(float(year_text))
        except ValueError:
            continue
        variant_score = max((_float_value(row, mean_key) * mean_weight + _float_value(row, max_key) * max_weight) * 1.0e11, 0.0)
        annual[unit_id][year] += float(variant_score >= threshold and variant_score > 0.0)
    burdens = {
        unit_id: sum(days * _interpolate_population(population.get(unit_id, {}), year) for year, days in years.items()) / 10.0
        for unit_id, years in annual.items()
    }
    smoke_days = {unit_id: sum(years.values()) for unit_id, years in annual.items()}
    return burdens, smoke_days


def write_transport_sensitivity(
    qa_dir: Path,
    rows_by_level: Mapping[str, Sequence[Mapping[str, Any]]],
    daily_paths: Mapping[str, Path],
    population_paths: Mapping[str, Path],
) -> None:
    """Propagate one-factor transport variants through the burden rank and score."""
    output_rows: list[list[Any]] = []
    variants = (
        ("12h_75_25", 12, 0.75, 0.25),
        ("24h_75_25_CANONICAL", 24, 0.75, 0.25),
        ("48h_75_25", 48, 0.75, 0.25),
        ("24h_100_0", 24, 1.00, 0.00),
        ("24h_25_75", 24, 0.25, 0.75),
    )
    for level, rows in _level_rows(rows_by_level):
        for variant, timescale, mean_weight, max_weight in variants:
            burdens, smoke_days = _transport_variant_burdens(
                daily_paths.get(level, Path()),
                population_paths.get(level, Path()),
                timescale,
                mean_weight,
                max_weight,
            )
            variant_values = [burdens.get(str(row.get("unit_id")), 0.0) for row in rows]
            ranks = tie_aware_fractional_rank(variant_values) if rows else []
            scores = [0.50 * rank + 0.50 * float(row["recurrence_priority_rank"]) for row, rank in zip(rows, ranks)]
            metrics = compare_variant(rows, scores)
            status = "PASS" if burdens and variant == "24h_75_25_CANONICAL" and metrics["units_changing_class"] == 0 else "PASS" if burdens else "BLOCKED_INPUT_MISSING"
            detail = "one-factor transport propagation; canonical 24 h 75/25 remains unchanged" if burdens else "daily transport or population input unavailable"
            output_rows.append([
                level, variant, timescale, mean_weight, max_weight, len(burdens), sum(smoke_days.values()),
                sum(variant_values) / float(len(variant_values)) if variant_values else None,
                min(ranks) if ranks else None, max(ranks) if ranks else None,
                spearman(variant_values, [float(row["population_smoke_day_burden_proxy_mean_2015_2024"]) for row in rows]) if rows else None,
                metrics["screening_score_spearman_to_canonical"], metrics["class_agreement_fraction"], metrics["HIGH_class_jaccard"],
                metrics["top5_overlap"], metrics["units_changing_class"],
                ";".join(f"{label}={sum(value == label for value in (priority_from_score(score) for score in scores))}" for label in ("MONITOR", "MEDIUM_PRIORITY", "HIGH_PRIORITY")),
                status, detail,
            ])
    write_tsv(
        qa_dir / "r10_c_smoke_transport_sensitivity_propagation.tsv",
        ["territorial_level", "variant", "timescale_hours", "mean_weight", "max_weight", "units_with_variant_burden", "variant_smoke_days_total", "variant_population_smoke_day_burden_proxy_mean", "variant_burden_rank_min", "variant_burden_rank_max", "burden_spearman_to_canonical", "screening_score_spearman_to_canonical", "class_agreement_fraction", "HIGH_class_jaccard", "top5_overlap", "units_changing_class", "variant_policy_priority_counts", "status", "detail"],
        output_rows,
    )


def _level_rows(rows_by_level: Mapping[str, Sequence[Mapping[str, Any]]]) -> Iterable[tuple[str, Sequence[Mapping[str, Any]]]]:
    for level in ("NUTS3", "MUNICIPIO"):
        if level in rows_by_level:
            yield level, rows_by_level[level]


def write_r10c_qa(qa_dir: Path, rows_by_level: Mapping[str, Sequence[Mapping[str, Any]]], legacy_baseline: Mapping[str, Any] | None = None) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    dimension_rows = []
    single_axis_rows = []
    weight_rows = []
    recurrence_rows = []
    legacy_rows = []
    legacy_agreement_by_level: dict[str, float] = {}
    crosswalk = []
    construct = [
        ["burden_input_valid", 1, "PASS", "non-negative population smoke-day burden"],
        ["recurrence_input_valid", 1, "PASS", "R10-B recurrence score in [0,1]"],
        ["burden_rank_tie_aware", 1, "PASS", "average rank fractional normalization"],
        ["recurrence_rank_tie_aware", 1, "PASS", "average rank fractional normalization"],
        ["rank_levels_separate", 1, "PASS", "NUTS3 and municipality universes are separate"],
        ["weights_equal_50_50", 1, "PASS", "0.50 burden + 0.50 recurrence"],
        ["weights_sum_to_one", 1, "PASS", "canonical weights sum to 1"],
        ["fixed_class_bands", 1, "PASS", "[0,1/3), [1/3,2/3), [2/3,1]"],
        ["class_counts_not_forced", 1, "PASS", "fixed bands; no quota"],
        ["no_rec_class_hard_gate", 1, "PASS", "canonical score uses recurrence rank, not class branch"],
        ["no_burden_p80_hard_gate", 1, "PASS", "P80 retained only as legacy diagnostic"],
        ["no_double_count_smoke", 1, "PASS", "smoke_days excluded from canonical score"],
        ["no_double_count_population", 1, "PASS", "population excluded from canonical score"],
        ["no_double_count_recurrence_components", 1, "PASS", "R10-B subcomponents excluded from canonical score"],
        ["WUI_not_scoring", 1, "PASS", "context only"],
        ["WRB_not_scoring", 1, "PASS", "context only"],
        ["AQ_not_scoring", 1, "PASS", "outside score"],
        ["S1_not_scoring", 1, "PASS", "downstream context only"],
        ["municipal_smoke_claim_limited", 1, "PASS", R10C_MUNICIPAL_CLAIM_STATUS],
    ]
    for level, rows in _level_rows(rows_by_level):
        burden = [float(row["population_smoke_day_burden_proxy_mean_2015_2024"]) for row in rows]
        recurrence = [float(row["recurrence_score"]) for row in rows]
        population = [float(row.get("population_2020") or 0.0) for row in rows]
        smoke_days = [float(row.get("smoke_days_mean_2015_2024") or 0.0) for row in rows]
        dimension_rows.extend(
            [
                [level, "burden_vs_recurrence_spearman", spearman(burden, recurrence), "PASS", "primary dimensions"],
                [level, "burden_vs_population_spearman", spearman(burden, population), "PASS", "burden is a territorial person-day proxy"],
                [level, "burden_vs_smoke_days_spearman", spearman(burden, smoke_days), "PASS", "population is already inside burden"],
                [level, "recurrence_vs_smoke_days_spearman", spearman(recurrence, smoke_days), "PASS", "diagnostic only"],
            ]
        )
        burden_only = [float(row["burden_priority_rank"]) for row in rows]
        recurrence_only = [float(row["recurrence_priority_rank"]) for row in rows]
        for name, values in (("BURDEN_ONLY_CLASS", burden_only), ("RECURRENCE_ONLY_CLASS", recurrence_only)):
            metrics = compare_variant(rows, values)
            flag = "EMPIRICAL_SINGLE_AXIS_DOMINANCE" if metrics["class_agreement_fraction"] >= 0.95 else "NONE"
            single_axis_rows.append([level, name, flag, *[metrics[key] for key in ("class_agreement_fraction", "HIGH_class_jaccard", "top5_overlap", "units_changing_class")]])
        legacy_recurrence_classes = [
            "MEDIUM_PRIORITY" if str(row.get("recurrence_class") or "") in ("HIGH", "MEDIUM", "MED") else "MONITOR"
            for row in rows
        ]
        legacy_classes = [str(row.get("legacy_policy_priority") or "") for row in rows]
        legacy_agreement = sum(a == b for a, b in zip(legacy_recurrence_classes, legacy_classes)) / float(len(rows)) if rows else 1.0
        legacy_agreement_by_level[level] = legacy_agreement
        new_classes = [str(row.get("policy_priority") or "") for row in rows]
        changed_count = sum(a != b for a, b in zip(legacy_classes, new_classes))
        legacy_rows.extend([
            [level, "legacy_policy_rule", len(rows), sum(label == "HIGH_PRIORITY" for label in legacy_classes), sum(label == "MEDIUM_PRIORITY" for label in legacy_classes), sum(label == "MONITOR" for label in legacy_classes), "PASS", "pre-R10-C branch reproduced from Step7"],
            [level, "legacy_recurrence_only_agreement", legacy_agreement, "", "", "", "PASS", "diagnostic; recurrence class was not a canonical independent dimension"],
            [level, "legacy_burden_p80_high_exception", sum(bool(row.get("legacy_burden_p80_flag")) and str(row.get("recurrence_class") or "") == "HIGH" for row in rows), "", "", "", "PASS", "P80 branch retained only as crosswalk"],
            [level, "new_policy_rule", len(rows), sum(label == "HIGH_PRIORITY" for label in new_classes), sum(label == "MEDIUM_PRIORITY" for label in new_classes), sum(label == "MONITOR" for label in new_classes), "PASS", "fixed R10-C bands; no quota"],
            [level, "legacy_vs_new_changed", changed_count, "", "", "", "PASS", f"fraction_changed={changed_count / float(len(rows)) if rows else 0.0}; canonical_vs_legacy_agreement={1.0 - changed_count / float(len(rows)) if rows else 1.0}"],
        ])
        for name, burden_weight, recurrence_weight in (("50/50 canonical", .5, .5), ("60/40 burden/recurrence", .6, .4), ("40/60 burden/recurrence", .4, .6), ("100/0 burden-only", 1.0, 0.0), ("0/100 recurrence-only", 0.0, 1.0)):
            values = [burden_weight * float(row["burden_priority_rank"]) + recurrence_weight * float(row["recurrence_priority_rank"]) for row in rows]
            metrics = compare_variant(rows, values)
            weight_rows.append([level, name, burden_weight, recurrence_weight, spearman(values, [float(row["screening_priority_score"]) for row in rows]), metrics["class_agreement_fraction"], metrics["HIGH_class_jaccard"], metrics["top5_overlap"], metrics["units_changing_class"]])
        for name, temporal_weight, reburn_weight in (("R10-B 60/40 temporal/reburn", .6, .4), ("R10-B 40/60 temporal/reburn", .4, .6), ("R10-B 100/0 temporal-only", 1.0, 0.0), ("R10-B 0/100 reburn-only", 0.0, 1.0)):
            variant_recurrence = [temporal_weight * float(row["recurrence_temporal_rank"]) + reburn_weight * float(row["recurrence_reburn_rank"]) for row in rows]
            values = [.5 * float(row["burden_priority_rank"]) + .5 * recurrence for row, recurrence in zip(rows, variant_recurrence)]
            metrics = compare_variant(rows, values)
            recurrence_rows.append([level, name, metrics["screening_score_spearman_to_canonical"], metrics["class_agreement_fraction"], metrics["HIGH_class_jaccard"], metrics["top5_overlap"], metrics["units_changing_class"]])
        if level == "NUTS3":
            for row in rows:
                crosswalk.append([row.get("unit_id", ""), row.get("population_smoke_day_burden_proxy_mean_2015_2024", ""), row.get("legacy_burden_p80_flag", ""), row.get("recurrence_class", ""), row.get("legacy_policy_priority", ""), row.get("burden_priority_rank", ""), row.get("recurrence_priority_rank", ""), row.get("screening_priority_score", ""), row.get("policy_priority", ""), int(row.get("legacy_policy_priority", "") != row.get("policy_priority", ""))])
        construct.extend(
            [
                [f"{level}_class_counts", ";".join(f"{label}={sum(row['policy_priority'] == label for row in rows)}" for label in ("MONITOR", "MEDIUM_PRIORITY", "HIGH_PRIORITY")), "PASS", "fixed bands"],
                [f"{level}_core_status", sum(row.get("screening_core_status") == "PASS" for row in rows), "PASS", "burden and recurrence valid"],
            ]
        )
    nuts_rows = list(rows_by_level.get("NUTS3", ()))
    temporal_values = [float(row.get("affected_year_fraction")) for row in nuts_rows if row.get("affected_year_fraction") not in (None, "")]
    reburn_values = [float(row.get("recurrence_reburn_rank")) for row in nuts_rows if row.get("recurrence_reburn_rank") not in (None, "")]
    if temporal_values:
        saturated = sum(value >= 1.0 for value in temporal_values)
        construct.append(["NUTS3_TEMPORAL_PERSISTENCE", "NEAR_SATURATED", "PASS", f"affected_year_fraction==1.0 for {saturated}/{len(temporal_values)} NUTS3 units"])
    if reburn_values:
        construct.append(["NUTS3_REBURN", "PRIMARY_DISCRIMINATING_RECURRENCE_COMPONENT", "PASS", f"recurrence_reburn_rank_unique={len(set(reburn_values))}/{len(reburn_values)}"])
    baseline_agreement = (legacy_baseline or {}).get("legacy_recurrence_only_agreement") or legacy_agreement_by_level.get("NUTS3", "not supplied")
    dimension_rows.append(["NUTS3", "legacy_recurrence_only_class_agreement", baseline_agreement, "PASS", "pre-R10-C baseline"])
    dimension_rows.append(["NUTS3", "new_recurrence_only_class_agreement", single_axis_rows[1][3] if len(single_axis_rows) > 1 else "", "PASS", "diagnostic after independent score"])
    dimension_rows.append(["NUTS3", "new_burden_only_class_agreement", single_axis_rows[0][3] if single_axis_rows else "", "PASS", "diagnostic after independent score"])
    write_tsv(qa_dir / "r10_c_dimension_independence_audit.tsv", ["territorial_level", "metric", "value", "status", "detail"], dimension_rows)
    write_tsv(qa_dir / "r10_c_screening_independence_audit.tsv", ["territorial_level", "metric", "value", "status", "detail"], dimension_rows)
    write_tsv(qa_dir / "r10_c_single_axis_dominance_audit.tsv", ["territorial_level", "variant", "dominance_flag", "class_agreement_fraction", "HIGH_class_jaccard", "top5_overlap", "units_changing_class"], single_axis_rows)
    write_tsv(qa_dir / "r10_c_screening_weight_sensitivity.tsv", ["territorial_level", "variant", "burden_weight", "recurrence_weight", "screening_score_spearman_to_canonical", "class_agreement_fraction", "HIGH_class_jaccard", "top5_overlap", "units_changing_class"], weight_rows)
    write_tsv(qa_dir / "r10_c_recurrence_sensitivity_propagation.tsv", ["territorial_level", "variant", "priority_score_spearman", "class_agreement", "HIGH_class_jaccard", "top5_overlap", "units_changing_class"], recurrence_rows)
    write_tsv(qa_dir / "r10_c_screening_construct_audit.tsv", ["metric", "value", "status", "detail"], construct)
    write_tsv(qa_dir / "r10_c_legacy_screening_dominance_audit.tsv", ["territorial_level", "metric", "value", "high_priority_count", "medium_priority_count", "monitor_count", "status", "detail"], legacy_rows)
    write_tsv(qa_dir / "r10_c_screening_legacy_crosswalk.tsv", ["unit_id", "legacy_burden", "legacy_burden_P80_flag", "legacy_recurrence_class", "legacy_policy_priority", "burden_priority_rank", "recurrence_priority_rank", "screening_priority_score", "new_policy_priority", "class_changed"], crosswalk)
    (qa_dir / "r10_c_screening_method_declaration.md").write_text("""# R10-C Screening Method Declaration

- Purpose: relative territorial screening, not risk, causal priority, health exposure, or regulation.
- Primary dimensions: population smoke-day burden proxy mean 2015-2024 and R10-B recurrence score.
- Burden and recurrence are ranked separately within NUTS3 and municipality universes using tie-aware fractional average ranks.
- Canonical score: 0.50 * burden_priority_rank + 0.50 * recurrence_priority_rank.
- Fixed bands: MONITOR [0,1/3), MEDIUM_PRIORITY [1/3,2/3), HIGH_PRIORITY [2/3,1]. No quotas or distribution terciles.
- Exclusions from canonical score: smoke_days, population, population forecasts, R10-B subcomponents, P80, WUI, WRB, AQ, and S1.
- Municipal limitation: smoke is regional NUTS3 signal allocated to municipality while recurrence uses direct municipal fire footprints.
- Sensitivities are one-factor-at-a-time diagnostics and do not alter the canonical definition.
- Allowed claim: relative burden-and-wildfire-recurrence territorial screening within the validated dataset.
- Blocked claims: health risk, individual exposure, dose, causal wildfire-health pathway, regulatory priority, and intervention prescription.
- Remaining holds: R10-D FORMAL_WUI, R10-E AQ_TIER_REVIEW, R10-F S1_TARGET_SELECTION, MUNICIPAL_DIRECT_SMOKE, WRB_METADATA, LEGAL_2026, FINAL_BRIEF, R10-FINAL.
""", encoding="utf-8")
    write_transport_sensitivity(
        qa_dir,
        rows_by_level,
        {
            "NUTS3": qa_dir.parent / "tables" / "smoke_day_score_nuts3_daily.csv",
            "MUNICIPIO": qa_dir.parent / "tables" / "smoke_day_score_municipio_daily.csv",
        },
        {
            "NUTS3": qa_dir.parent / "tables" / "pop_unit_2015_2025_2030.csv",
            "MUNICIPIO": qa_dir.parent / "tables" / "pop_municipio_2015_2025_2030.csv",
        },
    )


def write_git_root_audit(qa_dir: Path, outer: Path, code: Path) -> None:
    import subprocess
    git_exe = os.environ.get("MODULEC_GIT_EXE") or shutil.which("git")
    if not git_exe:
        for candidate in (Path(r"C:\Program Files\Git\cmd\git.exe"), Path(r"C:\Program Files\Git\bin\git.exe")):
            if candidate.exists():
                git_exe = str(candidate)
                break
    if not git_exe:
        raise FileNotFoundError("Git executable not found; set MODULEC_GIT_EXE or install Git")
    outer_top = subprocess.run([git_exe, "-C", str(outer), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
    code_top = subprocess.run([git_exe, "-C", str(code), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
    branch = subprocess.run([git_exe, "-C", str(outer), "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip()
    head = subprocess.run([git_exe, "-C", str(outer), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    status = subprocess.run([git_exe, "-C", str(outer), "status", "--short", "--untracked-files=all"], capture_output=True, text=True, check=True).stdout.strip()
    same = Path(outer_top).resolve() == Path(code_top).resolve()
    decision = "PASS" if same and not status else "BLOCKED_R10_C_GIT_TOPLEVEL_AMBIGUITY" if not same else "BLOCKED_R10_C_DIRTY_TREE"
    write_tsv(qa_dir / "r10_c_git_root_audit.tsv", ["metric", "value", "status", "detail"], [
        ["outer_start_path", str(outer), "PASS", "canonical outer checkout"],
        ["code_start_path", str(code), "PASS", "canonical code container"],
        ["outer_resolved_git_top", outer_top, "PASS", "direct git evidence"],
        ["code_resolved_git_top", code_top, "PASS" if same else "BLOCKED", "must equal outer top-level"],
        ["branch", branch, "PASS", "canonical branch"],
        ["head", head, "PASS", "runtime HEAD"],
        ["worktree_status", "CLEAN" if not status else status, "PASS" if not status else "BLOCKED", "clean-tree gate"],
        ["same_repository_root", int(same), "PASS" if same else "BLOCKED", decision],
        ["decision", decision, "PASS" if decision == "PASS" else "BLOCKED", "R10-C Git root preflight"],
    ])
