from __future__ import annotations

from pathlib import Path


def test_decoder_reads_era5_zip_members_instead_of_hard_coded_data_grib():
    repo_root = Path(__file__).resolve().parents[1]
    pipeline = (repo_root / "pipeline" / "moduleC_pipeline_v2.py").read_text(encoding="utf-8", errors="replace")

    assert 'with zipfile.ZipFile(era5_zip) as era5_archive' in pipeline
    assert 'era5_archive.namelist()' in pipeline
    assert 'era5_members = [name for name in era5_archive.namelist() if str(name).lower().endswith(".grib")]' in pipeline
    assert 'era5_vsi = f"/vsizip/{era5_zip.as_posix()}/{era5_member}"' in pipeline
    assert '/data.grib' not in pipeline
