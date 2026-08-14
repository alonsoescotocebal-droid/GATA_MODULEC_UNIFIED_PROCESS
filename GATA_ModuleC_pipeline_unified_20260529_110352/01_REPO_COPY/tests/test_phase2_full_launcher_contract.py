from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT.parent / "02_LAUNCHERS" / "run_modulec_canonical.ps1"


def test_full_requires_authorization_and_uses_scientific_producer() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "BLOCKED_FULL_RUNTIME_NOT_AUTHORIZED" in text
    assert "BLOCKED_FULL_RUNTIME_DEFERRED_PHASE1B" not in text
    assert "python-qgis-ltr.bat" in text
    assert "moduleC_pipeline_v2.py" in text
    assert "--modulec-data-root" in text
    assert "--incendios-root" in text
    assert "$scientificArgs = @(" in text
    assert "Invoke-NativeProcess" in text
    assert "Push-Location $RepoRoot" in text
    assert "Pop-Location" in text


def test_full_keeps_canonical_guards_and_disables_resume() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    for token in (
        "--git-toplevel",
        "--pipeline-code-root",
        "--expected-head-sha",
        "--enforce-clean-tree",
        "--allow-resume",
        "'0'",
        "BLOCKED_OUTPUT_ROOT_EXISTS",
    ):
        assert token in text
    assert "--resume" not in text
    assert "resume-post-smoke" not in text.lower()


def test_full_records_command_roots_and_process_logs() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    for token in (
        "launcher_command.txt",
        "launcher_roots.tsv",
        "scientific_stdout.txt",
        "scientific_stderr.txt",
    ):
        assert token in text
    assert "exit 0" in text


def test_full_does_not_rewrite_success_exit_after_scientific_packaging() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "$exitCodePath = Join-Path $provenanceDir 'launcher_exit_code.txt'" in text
    assert "if ($scientificExit -ne 0 -or -not (Test-Path -LiteralPath $exitCodePath))" in text
