# Module C isolated pytest bootstrap contract v1

This contract defines the test-tooling boundary for Phase 2A/2B.

The bootstrap is a repository tool, not a scientific launcher. It may create
files only below a new `03_RUNTIMES\TEST_TOOLING_BOOTSTRAP_<timestamp>_<sha8>`
root. It must never create a virtual environment or site-packages directory in
`01_REPO_COPY`, install globally or for the user, modify `environment.toml`,
write external data, or invoke the Module C scientific runtime.

The initial phase is offline. `plan` performs only local inspection and plan
generation. `download` and `install` require the exact approval token emitted
by the plan and are not authorized by this contract until the user supplies it.

The canonical Python compatibility matrix is fixed:

| Python | pytest |
|---|---|
| >= 3.10 | 9.1.1 |
| 3.9 | 8.4.2 |
| 3.8 | 8.3.5 |
| 3.7 | 7.4.4 |
| < 3.7 | blocked |

Only binary wheels from the official PyPI simple index are permitted. Source
distributions, global/user installation, pip upgrade, external plugins,
bytecode and pytest cache are prohibited. The package allowlist and all
runtime gates are machine-readable in `config/test_tooling_policy.json`.

The checkpoint is authoritative for resume. It binds the repository HEAD,
branch, policy hash, target hash, plan hash, exact Python executable and
bootstrap root. Any mismatch blocks resume.

Phase 2A ends at `AWAITING_DOWNLOAD_APPROVAL`. It does not download, install,
collect or run pytest, and it does not run the scientific Full runtime.
