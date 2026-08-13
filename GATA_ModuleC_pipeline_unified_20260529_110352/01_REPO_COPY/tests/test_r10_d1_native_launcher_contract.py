from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTAINER = ROOT.parent
LAUNCHER = CONTAINER / "02_LAUNCHERS" / "run_modulec_canonical.ps1"
RUNNER = CONTAINER / "02_LAUNCHERS" / "invoke_native_process.ps1"


def _powershell() -> str:
    return shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_runner(
    tmp_path: Path,
    *,
    stdout_text: str = "",
    stderr_text: str = "",
    exit_code: int = 0,
    extra_args: list[str] | None = None,
    working_directory: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    workdir = working_directory or (tmp_path / "working directory")
    workdir.mkdir(parents=True, exist_ok=True)
    child = tmp_path / "fake native child with spaces.ps1"
    marker = tmp_path / "working directory marker.txt"
    stdout_path = tmp_path / "scientific stdout.txt"
    stderr_path = tmp_path / "scientific stderr.txt"
    child.write_text(
        "param([string]$Out, [string]$Err, [int]$Code, [string]$Marker)\n"
        "[Console]::Out.Write($Out)\n"
        "[Console]::Error.Write($Err)\n"
        "if ($Marker) { [IO.File]::WriteAllText($Marker, (Get-Location).Path) }\n"
        "exit $Code\n",
        encoding="utf-8",
    )
    arguments = [
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(child),
        "-Out",
        stdout_text,
        "-Err",
        stderr_text,
        "-Code",
        str(exit_code),
        "-Marker",
        str(marker),
    ]
    if extra_args:
        arguments.extend(extra_args)
    powershell = _powershell()
    harness = tmp_path / "invoke runner harness.ps1"
    harness.write_text(
        ". " + _ps_literal(str(RUNNER)) + "\n"
        "$runnerArgs = ConvertFrom-Json @'\n"
        + json.dumps(arguments)
        + "\n'@\n"
        "$exitCode = Invoke-NativeProcess "
        "-FilePath "
        + _ps_literal(powershell)
        + " "
        "-ArgumentList @($runnerArgs) "
        "-WorkingDirectory "
        + _ps_literal(str(workdir))
        + " "
        "-StdoutPath "
        + _ps_literal(str(stdout_path))
        + " "
        "-StderrPath "
        + _ps_literal(str(stderr_path))
        + "\n"
        "exit $exitCode\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, stdout_path, stderr_path, marker


def test_launcher_contract_uses_exit_code_and_separate_native_streams() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")
    for token in (
        "invoke_native_process.ps1",
        "Invoke-NativeProcess",
        "scientific_stdout.txt",
        "scientific_stderr.txt",
        "launcher_command.txt",
    ):
        assert token in text
    runner_text = RUNNER.read_text(encoding="utf-8")
    for token in (
        "ProcessStartInfo",
        "RedirectStandardOutput",
        "RedirectStandardError",
        "ReadToEndAsync",
        "ExitCode",
    ):
        assert token in runner_text


def test_native_stdout_and_stderr_with_zero_exit_is_pass(tmp_path: Path) -> None:
    completed, stdout_path, stderr_path, _ = _run_runner(
        tmp_path, stdout_text="stdout text", stderr_text="stderr warning"
    )

    assert completed.returncode == 0, completed.stderr
    assert stdout_path.read_text(encoding="utf-8") == "stdout text"
    assert stderr_path.read_text(encoding="utf-8") == "stderr warning"


def test_native_stderr_with_nonzero_exit_fails_with_real_exit_code(tmp_path: Path) -> None:
    completed, stdout_path, stderr_path, _ = _run_runner(
        tmp_path, stderr_text="fatal native error", exit_code=17
    )

    assert completed.returncode == 17, completed.stderr
    assert stdout_path.read_text(encoding="utf-8") == ""
    assert stderr_path.read_text(encoding="utf-8") == "fatal native error"


def test_native_stdout_without_stderr_with_zero_exit_is_pass(tmp_path: Path) -> None:
    completed, stdout_path, stderr_path, _ = _run_runner(tmp_path, stdout_text="only stdout")

    assert completed.returncode == 0, completed.stderr
    assert stdout_path.read_text(encoding="utf-8") == "only stdout"
    assert stderr_path.read_text(encoding="utf-8") == ""


def test_native_paths_arguments_and_working_directory_with_spaces_are_preserved(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "controlled working directory with spaces"
    completed, _, _, marker = _run_runner(
        tmp_path,
        stdout_text="argument preserved",
        working_directory=workdir,
    )

    assert completed.returncode == 0, completed.stderr
    assert marker.read_text(encoding="utf-8") == str(workdir)


def test_native_stdout_log_preserves_raw_content(tmp_path: Path) -> None:
    payload = "raw stdout: [0] {1}"
    completed, stdout_path, _, _ = _run_runner(tmp_path, stdout_text=payload)

    assert completed.returncode == 0, completed.stderr
    assert stdout_path.read_text(encoding="utf-8") == payload


def test_native_stderr_log_preserves_raw_content(tmp_path: Path) -> None:
    payload = "raw stderr: warning\twith spaces"
    completed, _, stderr_path, _ = _run_runner(tmp_path, stderr_text=payload)

    assert completed.returncode == 0, completed.stderr
    assert stderr_path.read_text(encoding="utf-8") == payload


def test_qgis_application_path_warning_is_nonfatal_when_exit_is_zero(tmp_path: Path) -> None:
    warning = "Application path not initialized"
    completed, _, stderr_path, _ = _run_runner(tmp_path, stderr_text=warning)

    assert completed.returncode == 0, completed.stderr
    assert stderr_path.read_text(encoding="utf-8") == warning
