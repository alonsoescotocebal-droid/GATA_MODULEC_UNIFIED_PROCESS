from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

WRB_TILE_NAMES = ("193.tif", "235.tif", "236.tif")
WRB_LOOKUP_NAME = "MostProbable.rat.json"
WRB_OVERLAY_DIR_NAME = "outputs_qgis_WRB_overlay"
WRB_LEGACY_RASTER_NAME = "WRB_MostProbable_TM06.tif"
WRB_ASSEMBLED_VRT_NAME = "MostProbable_assembled.vrt"
WRB_REFERENCE_RELATIVE = Path("Resultados compilados") / "wrb_burned_2015_2024_long.csv"
WRB_ANNUAL_BURNED_AREA_MASKS = {
    2015: "mask_2015.gpkg",
    2016: "mask_2016.gpkg",
    2017: "mask_2017.gpkg",
    2018: "mask_2018.gpkg",
    2019: "mask_2019.gpkg",
    2020: "mask_2020.gpkg",
    2021: "mask_2021.gpkg",
    2022: "mask_2022_valid_NOHOLES.gpkg",
    2023: "mask_valid_NOHOLES_ardida_2023.gpkg",
    2024: "mask_valid_NOHOLES_ardida_2024.gpkg",
}


def norm_path(path: Path) -> str:
    try:
        resolved = path.resolve()
    except Exception:
        resolved = Path(os.path.abspath(str(path)))
    return os.path.normcase(os.path.normpath(str(resolved)))


def is_same_or_subpath(path: Path, prefix: Path) -> bool:
    n_path = norm_path(path)
    n_prefix = norm_path(prefix)
    return n_path == n_prefix or n_path.startswith(n_prefix + os.sep)


def _as_path(value: object) -> Optional[Path]:
    raw = str(value or "").strip()
    if not raw:
        return None
    return Path(raw)


def _append_candidate(candidates: List[Path], seen: set[str], candidate: Optional[Path]) -> None:
    if candidate is None:
        return
    key = norm_path(candidate)
    if key in seen:
        return
    seen.add(key)
    candidates.append(candidate)


def candidate_wrb_roots(paths: Mapping[str, object], inc_new_root: Optional[Path] = None) -> List[Path]:
    candidates: List[Path] = []
    seen: set[str] = set()

    legacy = _as_path(paths.get("wrb_mostprobable_tm06", ""))
    if legacy is not None:
        _append_candidate(candidates, seen, legacy.parent.parent)
        _append_candidate(candidates, seen, legacy.parent)

    fire_paths = paths.get("fire_gpkgs_tm06", [])
    if isinstance(fire_paths, list):
        for raw in fire_paths:
            fire_path = _as_path(raw)
            if fire_path is None:
                continue
            _append_candidate(candidates, seen, fire_path.parent.parent)
            _append_candidate(candidates, seen, fire_path.parent)

    if inc_new_root is not None:
        inc_root = Path(inc_new_root)
        if inc_root.name.lower() == "wrb":
            _append_candidate(candidates, seen, inc_root)
        else:
            _append_candidate(candidates, seen, inc_root / "WRB")

    return candidates


def find_wrb_source_bundle(paths: Mapping[str, object], inc_new_root: Optional[Path] = None) -> Dict[str, Path]:
    checked: List[str] = []
    for root in candidate_wrb_roots(paths, inc_new_root=inc_new_root):
        tiles = [root / tile_name for tile_name in WRB_TILE_NAMES]
        lookup = root / WRB_LOOKUP_NAME
        overlay_dir = root / WRB_OVERLAY_DIR_NAME
        legacy_raster = overlay_dir / WRB_LEGACY_RASTER_NAME
        assembled_vrt = overlay_dir / WRB_ASSEMBLED_VRT_NAME
        reference_csv = root / WRB_REFERENCE_RELATIVE

        missing = [str(p.name) for p in tiles if not p.exists()]
        if not lookup.exists():
            missing.append(lookup.name)
        if not missing:
            return {
                "wrb_root": root,
                "tile_193": tiles[0],
                "tile_235": tiles[1],
                "tile_236": tiles[2],
                "lookup_path": lookup,
                "overlay_dir": overlay_dir,
                "legacy_raster": legacy_raster,
                "assembled_vrt_template": assembled_vrt,
                "reference_csv": reference_csv,
            }
        checked.append(f"{root} missing {', '.join(missing)}")

    detail = " | ".join(checked) if checked else "no candidate WRB roots could be inferred from inputs"
    raise FileNotFoundError(f"WRB source route unavailable: {detail}")


def find_wrb_annual_burned_area_paths(paths: Mapping[str, object], inc_new_root: Optional[Path] = None) -> List[Path]:
    bundle = find_wrb_source_bundle(paths, inc_new_root=inc_new_root)
    overlay_dir = Path(bundle["overlay_dir"])
    annual_paths = [overlay_dir / WRB_ANNUAL_BURNED_AREA_MASKS[year] for year in sorted(WRB_ANNUAL_BURNED_AREA_MASKS)]
    missing = [str(path.name) for path in annual_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "WRB annual burned-area route unavailable: "
            f"{overlay_dir} missing {', '.join(missing)}"
        )
    return annual_paths


def catalog_resolved_paths(catalog_path: Path) -> List[Tuple[str, Path]]:
    if not catalog_path.exists():
        return []
    with catalog_path.open("r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        out: List[Tuple[str, Path]] = []
        for row in rdr:
            key = (row.get("InputKey") or "").strip()
            value = (row.get("ResolvedPath") or "").strip()
            if key and value:
                out.append((key, Path(value)))
        return out


def paths_outside_allowed_prefixes(
    paths: Iterable[Path],
    allowed_prefixes: Sequence[Path],
) -> List[Path]:
    outside: List[Path] = []
    for path in paths:
        if not any(is_same_or_subpath(path, prefix) for prefix in allowed_prefixes):
            outside.append(path)
    return outside
