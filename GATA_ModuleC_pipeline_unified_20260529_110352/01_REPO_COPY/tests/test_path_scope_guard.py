from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "pipeline" / "path_scope_guard.py"
    spec = importlib.util.spec_from_file_location("path_scope_guard", str(mod_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_path_scope_guard_pass(tmp_path, monkeypatch):
    mod = _load_module()
    repo = tmp_path / "repo"
    pipeline = repo / "pipeline"
    data_prefix = tmp_path / "iso" / "Complementariedad de analisis" / "Module C" / "Datos"
    output_prefix = tmp_path / "iso" / "Complementariedad de analisis" / "Module C" / "03_outputs"
    forbidden = tmp_path / "iso" / "_qa_catalogs" / "moduleC_local_pipeline"
    for p in (pipeline, data_prefix, output_prefix, forbidden):
        p.mkdir(parents=True, exist_ok=True)

    cfg = {
        "EXPECTED_REPO_ROOT": str(repo),
        "EXPECTED_BRANCH": "main",
        "EXPECTED_BASE_SHA": "ce7736d893a588ce85b21d725f1288d97c031bb6",
        "FORBIDDEN_CODE_ROOT": str(forbidden),
        "DATA_ROOT_ALLOWED_PREFIX": str(data_prefix),
        "OUTPUT_ROOT_ALLOWED_PREFIX": str(output_prefix),
    }

    def fake_run_git(_repo_root, args):
        if args[:2] == ["branch", "--show-current"]:
            return 0, "main", ""
        if args[:2] == ["rev-parse", "HEAD"]:
            return 0, "1111111111111111111111111111111111111111", ""
        if args[:2] == ["merge-base", "--is-ancestor"]:
            return 0, "", ""
        if args[:2] == ["status", "--short"]:
            return 0, "", ""
        raise AssertionError(f"Unexpected git args: {args}")

    monkeypatch.setattr(mod, "run_git", fake_run_git)

    overall, rows = mod.evaluate(
        repo_root=repo,
        pipeline_root=pipeline,
        data_root=data_prefix,
        output_root=output_prefix,
        cfg=cfg,
    )
    assert overall == "PATH_SCOPE_PASS"
    assert any(r["check_id"] == "SUMMARY_path_scope_decision" and r["status"] == "PATH_SCOPE_PASS" for r in rows)


def test_path_scope_guard_blocks_forbidden_code_root(tmp_path, monkeypatch):
    mod = _load_module()
    repo = tmp_path / "repo"
    forbidden = tmp_path / "iso" / "_qa_catalogs" / "moduleC_local_pipeline"
    pipeline = forbidden / "pipeline"
    data_prefix = tmp_path / "iso" / "Complementariedad de analisis" / "Module C" / "Datos"
    output_prefix = tmp_path / "iso" / "Complementariedad de analisis" / "Module C" / "03_outputs"
    for p in (repo, pipeline, data_prefix, output_prefix, forbidden):
        p.mkdir(parents=True, exist_ok=True)

    cfg = {
        "EXPECTED_REPO_ROOT": str(repo),
        "EXPECTED_BRANCH": "main",
        "EXPECTED_BASE_SHA": "ce7736d893a588ce85b21d725f1288d97c031bb6",
        "FORBIDDEN_CODE_ROOT": str(forbidden),
        "DATA_ROOT_ALLOWED_PREFIX": str(data_prefix),
        "OUTPUT_ROOT_ALLOWED_PREFIX": str(output_prefix),
    }

    def fake_run_git(_repo_root, args):
        if args[:2] == ["branch", "--show-current"]:
            return 0, "main", ""
        if args[:2] == ["rev-parse", "HEAD"]:
            return 0, "1111111111111111111111111111111111111111", ""
        if args[:2] == ["merge-base", "--is-ancestor"]:
            return 0, "", ""
        if args[:2] == ["status", "--short"]:
            return 0, "", ""
        raise AssertionError(f"Unexpected git args: {args}")

    monkeypatch.setattr(mod, "run_git", fake_run_git)

    overall, rows = mod.evaluate(
        repo_root=repo,
        pipeline_root=pipeline,
        data_root=data_prefix,
        output_root=output_prefix,
        cfg=cfg,
    )
    assert overall == "BLOCKED_PATH_DESYNC"
    assert any(r["status"] == "BLOCKED_FORBIDDEN_CODE_ROOT" for r in rows)

