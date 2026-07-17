from pathlib import Path
import sys


def test_write_source_runtime_provenance_uses_sha256_helper(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline'))
    import moduleC_pipeline_v2 as mod  # type: ignore

    output_root = tmp_path / '03_outputs'
    qa = output_root / 'qa'
    qa.mkdir(parents=True)
    (qa / 'run_log.txt').write_text('[2026-01-01T00:00:00] start\n[2026-01-01T01:00:00] end\n', encoding='utf-8')

    mod.write_source_runtime_provenance(output_root)
    rows = mod.read_csv_rows(qa / 'source_runtime_provenance.tsv')[1]
    assert len(rows) == 1
    row = rows[0]
    assert len(row['step9_script_sha256']) == 64
    assert len(row['r6k_script_sha256']) == 64
    assert row['output_root'] == str(output_root)


def test_write_source_runtime_provenance_uses_resolved_git_when_path_missing(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / 'pipeline'))
    import moduleC_pipeline_v2 as mod  # type: ignore

    output_root = tmp_path / '03_outputs'
    qa = output_root / 'qa'
    qa.mkdir(parents=True)
    (qa / 'run_log.txt').write_text('[2026-01-01T00:00:00] start\n[2026-01-01T01:00:00] end\n', encoding='utf-8')

    monkeypatch.setattr(mod.shutil, 'which', lambda name: None)

    real_exists = mod.Path.exists

    def fake_exists(self):
        if str(self) == r'C:\Program Files\Git\cmd\git.exe':
            return True
        return real_exists(self)

    real_run = mod.subprocess.run

    def fake_run(cmd, cwd=None, capture_output=False, text=False, encoding=None, errors=None):
        exe = cmd[0]
        args = tuple(cmd[1:])
        if str(exe) == r'C:\Program Files\Git\cmd\git.exe' and args == ('branch', '--show-current'):
            return mod.subprocess.CompletedProcess(cmd, 0, stdout='codex/test-branch\n', stderr='')
        if str(exe) == r'C:\Program Files\Git\cmd\git.exe' and args == ('rev-parse', 'HEAD'):
            return mod.subprocess.CompletedProcess(cmd, 0, stdout='abc123\n', stderr='')
        if str(exe) == r'C:\Program Files\Git\cmd\git.exe' and args == ('status', '--short'):
            return mod.subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
        return real_run(cmd, cwd=cwd, capture_output=capture_output, text=text, encoding=encoding, errors=errors)

    monkeypatch.setattr(mod.Path, 'exists', fake_exists)
    monkeypatch.setattr(mod.subprocess, 'run', fake_run)

    mod.write_source_runtime_provenance(output_root)
    rows = mod.read_csv_rows(qa / 'source_runtime_provenance.tsv')[1]
    row = rows[0]
    assert row['branch'] == 'codex/test-branch'
    assert row['HEAD_SHA'] == 'abc123'
    assert row['git_status_clean'] == '1'
