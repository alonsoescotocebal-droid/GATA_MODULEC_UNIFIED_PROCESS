# SCIENTIFIC THRESHOLD DECLARATION REGISTER

Status: ACTIVE  
Date: 2026-05-26

This register is the compact machine/human layer for smoke-route v0 GFAS/ERA5 and claim gating.

| threshold_id | component | variable_required | accepted_data_source | threshold_value_or_rule | source_type | allowed_claim | forbidden_claim | gate_result_if_missing | implementation_status | notes |
|---|---|---|---|---|---|---|---|---|---|---|
| GFAS_PM2P5FIRE_PROXY_V0 | smoke_route_v0 | PM2P5FIRE | CAMS-GFAS read through GDAL | operational proxy only; not health concentration | internal_operational_proxy | proxy atmosférico operativo / smoke_day_score v0 | exposición sanitaria validada / PM2.5 superficial validado / claim epidemiológico directo | BLOCKED_HEALTH_EXPOSURE_CLAIM | implemented | GDAL-only backend, ecCodes forbidden for GFAS decode path |
| GFAS_PORTUGAL_NEGATIVE_LON_GDAL_WINDOW | spatial_crop | GDAL geotransform covering -180..180 | GDAL geotransform from GFAS | -projwin -10.0 43.0 -6.0 36.5 | methodological_gate | Portugal crop usable for GFAS GDAL grid | 0-360 longitude convention as main route for this GDAL grid | BLOCKED_PORTUGAL_CROP_CONVENTION | implemented | 350..354 route rejected for primary crop |
| GDAL_GFAS_PACKING_WARNING_CLASSIFICATION | runtime_warning_gate | GDAL stderr/stdout warning inventory | warning_inventory.tsv generated during runtime | no unexplained warning allowed | methodological_gate | warning classified only if values are directly verified and reproducible | silent warning suppression or GO with unexplained warning | BLOCKED_UNEXPLAINED_WARNING | implemented | packing warning is allowed only when evidence rows are reproducible |
