"""Pure geometry and weighting primitives for the R10-A2 smoke proxy."""

from __future__ import annotations

import math
from typing import Dict, Iterable, Tuple

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
        distance_transport_weight = math.exp(
            -transport_time_hours / OPERATIONAL_DAILY_ADVECTION_TIMESCALE_HOURS
        )
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
) -> float:
    return _transport_components(
        source_lon,
        source_lat,
        receptor_lon,
        receptor_lat,
        u10_mps,
        v10_mps,
    )["transport_kernel"]


def _transport_weighted_receptor_proxy(
    sources: Iterable[Dict[str, float]],
    receptor: Dict[str, float],
    u10_mps: float,
    v10_mps: float,
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
        )
        total += float(flux) * kernel
        valid_count += 1
    return total / float(valid_count) if valid_count else 0.0


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
