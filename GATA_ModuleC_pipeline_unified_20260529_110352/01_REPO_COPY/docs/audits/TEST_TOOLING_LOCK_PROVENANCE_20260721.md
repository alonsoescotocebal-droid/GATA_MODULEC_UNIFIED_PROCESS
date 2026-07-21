# TEST_TOOLING_LOCK_PROVENANCE — 2026-07-21

## Baseline

- initial SHA: `bc113aa9039321ac5cf407fa646edab996d73c35`
- branch: `codex/wrb-source-route-repair-b9cb373d`
- Git top-level: `D:\GATA_MODULEC_UNIFIED_PROCESS`
- Python: `C:\Python314\python.exe`, CPython `3.14.2`
- pip: `pip 26.1.2`
- runtime scientific: `false`

## Resolution scope

The wheels were resolved with the project Python using the official PyPI
simple index only:

```text
C:\Python314\python.exe -B -m pip --isolated --disable-pip-version-check download --no-input --no-cache-dir --only-binary=:all: --index-url https://pypi.org/simple --dest <STAGING>\wheelhouse pytest==9.1.1
```

No extra index, source distribution, global install, user install, pip
upgrade, scientific data URL, or scientific runtime was used.

## Wheels and hashes

| package | version | wheel | size | SHA256 | Requires-Python |
|---|---:|---|---:|---|---|
| colorama | 0.4.6 | `colorama-0.4.6-py2.py3-none-any.whl` | 25335 | `4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6` | `!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,!=3.4.*,!=3.5.*,!=3.6.*,>=2.7` |
| iniconfig | 2.3.0 | `iniconfig-2.3.0-py3-none-any.whl` | 7484 | `f631c04d2c48c52b84d0d0549c99ff3859c98df65b3101406327ecc7d53fbf12` | `>=3.10` |
| packaging | 26.2 | `packaging-26.2-py3-none-any.whl` | 100195 | `5fc45236b9446107ff2415ce77c807cee2862cb6fac22b8a73826d0693b0980e` | `>=3.8` |
| pluggy | 1.6.0 | `pluggy-1.6.0-py3-none-any.whl` | 20538 | `e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746` | `>=3.9` |
| pygments | 2.20.0 | `pygments-2.20.0-py3-none-any.whl` | 1231151 | `81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176` | `>=3.9` |
| pytest | 9.1.1 | `pytest-9.1.1-py3-none-any.whl` | 386536 | `37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c` | `>=3.10` |

All six wheels are allowlisted, compatible with Windows/CPython 3.14 and
contain no source distribution. Effective dependencies are the six packages
listed in the lock; optional extras and Python <3.11 dependencies were not
selected.

## Lock and isolated installation

- repository lock: `01_REPO_COPY\config\requirements-test.lock`
- lock SHA256: `6d371e7615b22e2e34802525fd71985fec3f00f2a7b4d1206973de9b97439eda`
- staging: `03_RUNTIMES\TEST_TOOLING_LOCK_BUILD_20260721_154500_BC113AA`
- installation: staging `install_test\venv` only
- pytest: `9.1.1`
- pytest import: under `install_test\venv\Lib\site-packages\pytest`
- `pip check`: PASS
- repository test suite: not executed in this phase

## Integrity boundary

The Git tree, Codex configuration, Codex environment, launcher, pipeline,
and external data were not intentionally modified during resolution or the
isolated install. Wheels, venv, logs and metadata remain only in the staging
runtime. The old `TEST_TOOLING_BOOTSTRAP_20260721_1761D4` runtime was not
reused and was treated as historical revoked approval plan.
