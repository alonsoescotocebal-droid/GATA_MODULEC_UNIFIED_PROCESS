import json
import sys
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "pipeline"))
    import path_scope_guard as mod  # type: ignore

    return mod


def _fake_run_git(_repo_root, args):
    if args[:2] == ["branch", "--show-current"]:
        return 0, "main", ""
    if args[:2] == ["rev-parse", "HEAD"]:
        return 0, "1111111111111111111111111111111111111111", ""
    if args[:2] == ["merge-base", "--is-ancestor"]:
        return 0, "", ""
    if args[:2] == ["status", "--short"]:
        return 0, "", ""
    raise AssertionError(f"Unexpected git args: {args}")


def test_path_scope_guard_blocks_catalog_entries_outside_allowed_prefix(tmp_path, monkeypatch):
    mod = _load_module()
    repo = tmp_path / "repo"
    pipeline = repo / "pipeline"
    catalog_dir = repo / "data_placeholders"
    data_prefix = tmp_path / "iso" / "Module C" / "Datos"
    output_prefix = tmp_path / "iso" / "Module C" / "03_outputs"
    forbidden = tmp_path / "iso" / "_qa_catalogs" / "moduleC_local_pipeline"
    outside_root = tmp_path / "outside"
    for p in (pipeline, catalog_dir, data_prefix, output_prefix, forbidden, outside_root):
        p.mkdir(parents=True, exist_ok=True)

    bad_file = outside_root / "bad.tif"
    bad_file.write_text("x", encoding="utf-8")
    (catalog_dir / "master_inputs_for_pipeline.csv").write_text(
        "InputKey,ResolvedPath\nwrb_tile_193," + str(bad_file) + "\n",
        encoding="utf-8",
    )

    cfg = {
        "EXPECTED_REPO_ROOT": str(repo),
        "EXPECTED_BRANCH": "main",
        "EXPECTED_BASE_SHA": "ce7736d893a588ce85b21d725f1288d97c031bb6",
        "FORBIDDEN_CODE_ROOT": str(forbidden),
        "DATA_ROOT_ALLOWED_PREFIX": str(data_prefix),
        "DATA_ROOT_ALLOWED_PREFIXES": json.dumps([str(data_prefix)]),
        "OUTPUT_ROOT_ALLOWED_PREFIX": str(output_prefix),
    }
    monkeypatch.setattr(mod, "run_git", _fake_run_git)

    overall, rows = mod.evaluate(
        repo_root=repo,
        pipeline_root=pipeline,
        data_root=data_prefix,
        output_root=output_prefix / "run_01",
        cfg=cfg,
    )

    assert overall == mod.STATE_BLOCKED_PATH_DESYNC
    assert any(
        r["check_id"] == "P001B_catalog_scope"
        and r["status"] == mod.STATE_BLOCKED_INPUT_PATH_OUTSIDE_ALLOWED_ROOT
        for r in rows
    )


def test_path_scope_guard_accepts_incendios_nueva_version_catalog_entries(tmp_path, monkeypatch):
    mod = _load_module()
    repo = tmp_path / "repo"
    pipeline = repo / "pipeline"
    catalog_dir = repo / "data_placeholders"
    data_prefix = tmp_path / "iso" / "Module C" / "Datos"
    inc_new_prefix = tmp_path / "iso" / "Incendios_Nueva version"
    output_prefix = tmp_path / "iso" / "Module C" / "03_outputs"
    forbidden = tmp_path / "iso" / "_qa_catalogs" / "moduleC_local_pipeline"
    for p in (pipeline, catalog_dir, data_prefix, inc_new_prefix, output_prefix, forbidden):
        p.mkdir(parents=True, exist_ok=True)

    wrb_tile = inc_new_prefix / "WRB" / "193.tif"
    wrb_tile.parent.mkdir(parents=True, exist_ok=True)
    wrb_tile.write_text("x", encoding="utf-8")
    (catalog_dir / "master_inputs_for_pipeline.csv").write_text(
        "InputKey,ResolvedPath\nwrb_tile_193," + str(wrb_tile) + "\n",
        encoding="utf-8",
    )

    cfg = {
        "EXPECTED_REPO_ROOT": str(repo),
        "EXPECTED_BRANCH": "main",
        "EXPECTED_BASE_SHA": "ce7736d893a588ce85b21d725f1288d97c031bb6",
        "FORBIDDEN_CODE_ROOT": str(forbidden),
        "DATA_ROOT_ALLOWED_PREFIX": str(data_prefix),
        "DATA_ROOT_ALLOWED_PREFIXES": json.dumps([str(data_prefix), str(inc_new_prefix)]),
        "OUTPUT_ROOT_ALLOWED_PREFIX": str(output_prefix),
    }
    monkeypatch.setattr(mod, "run_git", _fake_run_git)

    overall, rows = mod.evaluate(
        repo_root=repo,
        pipeline_root=pipeline,
        data_root=data_prefix,
        output_root=output_prefix / "run_01",
        cfg=cfg,
    )

    assert overall == mod.STATE_PATH_SCOPE_PASS
    assert any(r["check_id"] == "P001B_catalog_scope" and r["status"] == "PASS" for r in rows)

