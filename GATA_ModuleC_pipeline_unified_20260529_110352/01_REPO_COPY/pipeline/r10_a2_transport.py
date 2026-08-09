"""Pure geometry and weighting primitives for the R10-A2 smoke proxy."""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence, Tuple

EARTH_RADIUS_KM = 6371.0088
OPERATIONAL_DAILY_ADVECTION_TIMESCALE_HOURS = 24.0
CALM_WIND_EPSILON_MPS = 1.0e-9
SOURCE_RECEPTOR_EPSILON_KM = 1.0e-9


def _source_receptor_vector_km(
    source_lon: float,
    source_lat: float,
    receptor_lon: float,
    receptor_lat: float,
) -> Tuple[float, float, float]:
    """Return local east/north displacement and geodesic distance in km."""
    source_lat_rad = math.radians(float(source_lat))
    receptor_lat_rad = math.radians(float(receptor_lat))
    mean_lat_rad = (source_lat_rad + receptor_lat_rad) / 2.0
    dlon_rad = math.radians(float(receptor_lon) - float(source_lon))
    dlat_rad = receptor_lat_rad - source_lat_rad
    east_km = EARTH_RADIUS_KM * math.cos(mean_lat_rad) * dlon_rad
    north_km = EARTH_RADIUS_KM * dlat_rad
    distance_km = math.hypot(east_km, north_km)
    return east_km, north_km, distance_km


def _transport_components(
    source_lon: float,
    source_lat: float,
    receptor_lon: float,
    receptor_lat: float,
    u10_mps: float,
    v10_mps: float,
    timescale_hours: float = OPERATIONAL_DAILY_ADVECTION_TIMESCALE_HOURS,
) -> Dict[str, float]:
    east_km, north_km, distance_km = _source_receptor_vector_km(
        source_lon, source_lat, receptor_lon, receptor_lat
    )
    wind_speed_mps = math.hypot(float(u10_mps), float(v10_mps))
    if distance_km <= SOURCE_RECEPTOR_EPSILON_KM:
        alignment = 1.0
        transport_time_hours = 0.0
        distance_transport_weight = 1.0
        transport_kernel = 1.0
    elif wind_speed_mps <= CALM_WIND_EPSILON_MPS:
        alignment = 0.0
        transport_time_hours = math.inf
        distance_transport_weight = 0.0
        transport_kernel = 0.0
    else:
        source_receptor_norm = math.hypot(east_km, north_km)
        alignment = max(
            0.0,
            min(
                1.0,
                (
                    (float(u10_mps) * east_km)
                    + (float(v10_mps) * north_km)
                )
                / (wind_speed_mps * source_receptor_norm),
            ),
        )
        transport_time_hours = distance_km / (wind_speed_mps * 3.6)
        if float(timescale_hours) <= 0.0:
            raise ValueError("timescale_hours must be positive")
        distance_transport_weight = math.exp(-transport_time_hours / float(timescale_hours))
        transport_kernel = alignment * distance_transport_weight
    return {
        "distance_km": float(distance_km),
        "wind_speed_mps": float(wind_speed_mps),
        "alignment": float(alignment),
        "transport_time_hours": float(transport_time_hours),
        "distance_transport_weight": float(distance_transport_weight),
        "transport_kernel": float(transport_kernel),
    }


def _transport_kernel(
    source_lon: float,
    source_lat: float,
    receptor_lon: float,
    receptor_lat: float,
    u10_mps: float,
    v10_mps: float,
    timescale_hours: float = OPERATIONAL_DAILY_ADVECTION_TIMESCALE_HOURS,
) -> float:
    return _transport_components(
        source_lon,
        source_lat,
        receptor_lon,
        receptor_lat,
        u10_mps,
        v10_mps,
        timescale_hours,
    )["transport_kernel"]


def _transport_weighted_receptor_proxy(
    sources: Iterable[Dict[str, float]],
    receptor: Dict[str, float],
    u10_mps: float,
    v10_mps: float,
    timescale_hours: float = OPERATIONAL_DAILY_ADVECTION_TIMESCALE_HOURS,
) -> float:
    """Aggregate flux times kernel over valid source cells without weight renormalization."""
    total = 0.0
    valid_count = 0
    receptor_lon = float(receptor["lon"])
    receptor_lat = float(receptor["lat"])
    for source in sources:
        flux = source.get("flux")
        if flux is None:
            flux = source.get("gfas_flux")
        if flux is None or not math.isfinite(float(flux)):
            continue
        kernel = _transport_kernel(
            float(source["lon"]),
            float(source["lat"]),
            receptor_lon,
            receptor_lat,
            u10_mps,
            v10_mps,
            timescale_hours,
        )
        total += float(flux) * kernel
        valid_count += 1
    return total / float(valid_count) if valid_count else 0.0


def _aggregate_receptor_transport(proxies: Sequence[float]) -> Dict[str, float]:
    """Aggregate valid receptor-level proxies only after source-level transport."""
    values = [float(value) for value in proxies if math.isfinite(float(value))]
    if not values:
        return {
            "receptor_count": 0.0,
            "valid_receptor_count": 0.0,
            "transport_proxy_mean": 0.0,
            "transport_proxy_max": 0.0,
        }
    return {
        "receptor_count": float(len(proxies)),
        "valid_receptor_count": float(len(values)),
        "transport_proxy_mean": sum(values) / float(len(values)),
        "transport_proxy_max": max(values),
    }


def _recalculate_receptor_profiles(
    sources: Iterable[Dict[str, float]],
    receptors: Sequence[Dict[str, float]],
    timescales: Sequence[float] = (12.0, 24.0, 48.0),
) -> Dict[float, Dict[str, float]]:
    """Recalculate every source-to-receptor kernel for each requested timescale."""
    source_rows = list(sources)
    try:
        import numpy as np  # type: ignore
    except Exception:
        np = None

    if np is not None and source_rows and receptors:
        valid_sources = [
            source
            for source in source_rows
            if source.get("flux") is not None and math.isfinite(float(source["flux"]))
        ]
        if valid_sources:
            source_lon = np.asarray([float(source["lon"]) for source in valid_sources], dtype=float)
            source_lat = np.asarray([float(source["lat"]) for source in valid_sources], dtype=float)
            source_flux = np.asarray([float(source["flux"]) for source in valid_sources], dtype=float)
            source_lat_rad = np.radians(source_lat)
            profiles: Dict[float, Dict[str, float]] = {}
            for timescale in timescales:
                values: List[float] = []
                for receptor in receptors:
                    receptor_lon = float(receptor["lon"])
                    receptor_lat_rad = math.radians(float(receptor["lat"]))
                    mean_lat_rad = (source_lat_rad + receptor_lat_rad) / 2.0
                    east_km = EARTH_RADIUS_KM * np.cos(mean_lat_rad) * np.radians(receptor_lon - source_lon)
                    north_km = EARTH_RADIUS_KM * (receptor_lat_rad - source_lat_rad)
                    distance_km = np.hypot(east_km, north_km)
                    wind_u = float(receptor["u10_mps"])
                    wind_v = float(receptor["v10_mps"])
                    wind_speed = math.hypot(wind_u, wind_v)
                    local = distance_km <= SOURCE_RECEPTOR_EPSILON_KM
                    active = (~local) & (wind_speed > CALM_WIND_EPSILON_MPS)
                    alignment = np.zeros_like(distance_km)
                    if bool(np.any(active)):
                        if float(timescale) <= 0.0:
                            raise ValueError("timescale_hours must be positive")
                        alignment[active] = np.clip(
                            ((wind_u * east_km[active]) + (wind_v * north_km[active]))
                            / (wind_speed * distance_km[active]),
                            0.0,
                            1.0,
                        )
                    transport_time = np.full_like(distance_km, np.inf)
                    transport_time[local] = 0.0
                    if bool(np.any(active)):
                        transport_time[active] = distance_km[active] / (wind_speed * 3.6)
                    distance_weight = np.zeros_like(distance_km)
                    distance_weight[local] = 1.0
                    if bool(np.any(active)):
                        distance_weight[active] = np.exp(-transport_time[active] / float(timescale))
                    kernel = alignment * distance_weight
                    kernel[local] = 1.0
                    values.append(float(np.sum(source_flux * kernel) / float(len(valid_sources))))
                profiles[float(timescale)] = _aggregate_receptor_transport(values)
            return profiles

    profiles: Dict[float, Dict[str, float]] = {}
    for timescale in timescales:
        values: List[float] = []
        for receptor in receptors:
            values.append(
                _transport_weighted_receptor_proxy(
                    source_rows,
                    receptor,
                    float(receptor["u10_mps"]),
                    float(receptor["v10_mps"]),
                    float(timescale),
                )
            )
        aggregate = _aggregate_receptor_transport(values)
        profiles[float(timescale)] = aggregate
    return profiles


def _transport_receptor_diagnostics(
    sources: Sequence[Dict[str, float]],
    receptors: Sequence[Dict[str, float]],
) -> Dict[str, float]:
    """Summarize diagnostic transport terms without repeating scalar source loops."""
    try:
        import numpy as np  # type: ignore
    except Exception:
        return {}
    valid_sources = [
        source
        for source in sources
        if source.get("flux") is not None and math.isfinite(float(source["flux"]))
    ]
    if not valid_sources or not receptors:
        return {}
    source_lon = np.asarray([float(source["lon"]) for source in valid_sources], dtype=float)
    source_lat = np.asarray([float(source["lat"]) for source in valid_sources], dtype=float)
    source_flux = np.asarray([float(source["flux"]) for source in valid_sources], dtype=float)
    source_lat_rad = np.radians(source_lat)
    pair_count = 0
    upwind_source_count = 0
    calm_wind_count = 0
    alignment_total = 0.0
    transport_weight_total = 0.0
    alignment_flux_total = 0.0
    transport_time_total = 0.0
    wind_speed_total = 0.0
    for receptor in receptors:
        receptor_lon = float(receptor["lon"])
        receptor_lat_rad = math.radians(float(receptor["lat"]))
        mean_lat_rad = (source_lat_rad + receptor_lat_rad) / 2.0
        east_km = EARTH_RADIUS_KM * np.cos(mean_lat_rad) * np.radians(receptor_lon - source_lon)
        north_km = EARTH_RADIUS_KM * (receptor_lat_rad - source_lat_rad)
        distance_km = np.hypot(east_km, north_km)
        wind_u = float(receptor["u10_mps"])
        wind_v = float(receptor["v10_mps"])
        wind_speed = math.hypot(wind_u, wind_v)
        local = distance_km <= SOURCE_RECEPTOR_EPSILON_KM
        calm = (~local) & (wind_speed <= CALM_WIND_EPSILON_MPS)
        active = (~local) & (~calm)
        alignment = np.zeros_like(distance_km)
        alignment[local] = 1.0
        if bool(np.any(active)):
            alignment[active] = np.clip(
                ((wind_u * east_km[active]) + (wind_v * north_km[active]))
                / (wind_speed * distance_km[active]),
                0.0,
                1.0,
            )
        transport_time = np.full_like(distance_km, np.inf)
        transport_time[local] = 0.0
        if bool(np.any(active)):
            transport_time[active] = distance_km[active] / (wind_speed * 3.6)
        distance_weight = np.zeros_like(distance_km)
        distance_weight[local] = 1.0
        if bool(np.any(active)):
            distance_weight[active] = np.exp(
                -transport_time[active] / OPERATIONAL_DAILY_ADVECTION_TIMESCALE_HOURS
            )
        pair_count += len(valid_sources)
        upwind_source_count += int(np.count_nonzero(alignment > 0.0))
        calm_wind_count += int(np.count_nonzero(calm))
        alignment_total += float(np.sum(alignment))
        transport_weight_total += float(np.sum(distance_weight))
        alignment_flux_total += float(np.sum(source_flux * alignment))
        transport_time_total += float(np.sum(transport_time[np.isfinite(transport_time)]))
        wind_speed_total += wind_speed
    return {
        "mean_wind_speed_mps": wind_speed_total / float(len(receptors)),
        "mean_upwind_alignment": alignment_total / float(pair_count),
        "mean_transport_weight": transport_weight_total / float(pair_count),
        "transport_proxy_alignment_mean": alignment_flux_total / float(pair_count),
        "mean_transport_time_hours": transport_time_total / float(pair_count),
        "valid_source_count": float(len(valid_sources)),
        "upwind_source_count": float(upwind_source_count),
        "calm_wind_count": float(calm_wind_count),
    }


def _r10_a2_route_claim(era5_used_in_score: bool) -> str:
    if bool(era5_used_in_score):
        return "ADVECTION_INFORMED_OPERATIONAL_SMOKE_PROXY"
    return "BLOCKED_ERA5_MECHANISTIC_CLAIM"


def _r10_a2_smoke_score(transport_proxy_mean: float, transport_proxy_max: float) -> float:
    return max(
        (
            0.75 * float(transport_proxy_mean)
            + 0.25 * float(transport_proxy_max)
        )
        * 1.0e11,
        0.0,
    )
