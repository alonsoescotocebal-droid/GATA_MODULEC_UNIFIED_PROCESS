# Spatial Collapse Root Cause Audit

- Timestamp: 2026-05-27
- Output root audited: `D:\Mestrado\GATA_2025_2026\Prueba_aislada\ISO_GATA_20260121_130505\Complementariedad de analisis\Module C\03_outputs`
- Decision: `COLLAPSE_ORIGIN_MULTIPLE`

## Direct evidence

- `smoke_day_score_nuts3_daily.csv` has 52 rows, 26 units, 2 dates, and one unique score per date/year.
- `smoke_days_nuts3_annual_2015_2024.csv` has one unique `smoke_days` value for each year 2015-2024 across all units.
- `gfas_pm2p5fire_portugal_daily_summary.csv` is Portugal-global (no `unit_id`; no per-unit lat/lon join in summary table).
- `IECH_unit_2015_2024.csv` collapses mathematically (`IECH == smoke_hours_equiv` in 260/260; `expo_person_hours == pop * smoke_hours_equiv` in 260/260).

## Causal interpretation

- Decoder GDAL-only is operational and traces GFAS/ERA5 correctly.
- The post-decoder route transforms global daily anchors into a yearly series and replicates it to every unit.
- The IECH stage then preserves that homogeneity and cancels population in the ratio definition.
- Therefore the collapse origin is multiple, dominated by global-summary-to-unit replication and IECH cancellation effects.
