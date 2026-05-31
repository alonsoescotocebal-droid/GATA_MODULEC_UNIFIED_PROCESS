from __future__ import annotations

from pathlib import Path


def test_step9_blocks_stale_bundle_payload():
    repo_root = Path(__file__).resolve().parents[1]
    step9 = repo_root / "pipeline" / "RUN_QGIS" / "STEP9_FINAL_MASTER_PACK" / "run_step9_final_master_pack.ps1"
    text = step9.read_text(encoding="utf-8", errors="replace")

    assert "BLOCKED_STALE_BUNDLE_PAYLOAD" in text
    assert "_bundle_payload" in text
    assert "final_bundle_staleness_audit.tsv" in text
    assert "qa\\gfas_pm2p5fire_message_inventory.tsv" in text
    assert "qa\\warning_inventory.tsv" in text
    assert "tables\\smoke_day_score_nuts3_daily.csv" in text
