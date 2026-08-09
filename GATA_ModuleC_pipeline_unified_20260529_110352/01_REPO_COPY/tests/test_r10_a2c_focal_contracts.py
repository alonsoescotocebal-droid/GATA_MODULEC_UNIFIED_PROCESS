from pathlib import Path
import sys



REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "pipeline"))

import moduleC_pipeline_v2 as modulec  # type: ignore
from r10_a2_transport import (  # type: ignore
    _aggregate_receptor_transport,
    _recalculate_receptor_profiles,
    _r10_a2_smoke_score,
)


def test_multi_receptor_aggregation_preserves_mean_and_max():
    profile = _aggregate_receptor_transport([1.0, 3.0])

    assert profile["valid_receptor_count"] == 2
    assert profile["transport_proxy_mean"] == 2.0
    assert profile["transport_proxy_max"] == 3.0
    assert _r10_a2_smoke_score(profile["transport_proxy_mean"], profile["transport_proxy_max"]) == 2.25e11


def test_single_receptor_is_a_valid_non_degenerate_special_case():
    profile = _aggregate_receptor_transport([2.0])

    assert profile["valid_receptor_count"] == 1
    assert profile["transport_proxy_mean"] == profile["transport_proxy_max"] == 2.0


def test_source_level_sensitivity_recalculates_each_receptor():
    sources = [
        {"lon": -8.0, "lat": 40.0, "flux": 1.0},
        {"lon": -7.9, "lat": 40.0, "flux": 3.0},
    ]
    receptors = [
        {"sample_index": 1, "lon": -7.8, "lat": 40.0, "u10_mps": 5.0, "v10_mps": 0.0},
        {"sample_index": 2, "lon": -8.2, "lat": 40.0, "u10_mps": 5.0, "v10_mps": 0.0},
    ]

    profiles = _recalculate_receptor_profiles(sources, receptors, (12.0, 24.0, 48.0))

    assert profiles[24.0]["valid_receptor_count"] == 2
    assert profiles[12.0]["transport_proxy_mean"] != profiles[48.0]["transport_proxy_mean"]
    assert profiles[24.0]["transport_proxy_mean"] != profiles[24.0]["transport_proxy_max"]


def test_tie_aware_spearman_uses_average_ranks():
    value = modulec._spearman_correlation([1.0, 1.0, 3.0], [1.0, 2.0, 3.0])

    assert round(value, 12) == round(0.8660254037844387, 12)


def test_annual_audit_sums_daily_values_instead_of_overwriting():
    rows = [
        {"unit_id": "U1", "year": 2015, "smoke_day_proxy": 1},
        {"unit_id": "U1", "year": 2015, "smoke_day_proxy": 1},
        {"unit_id": "U1", "year": 2016, "smoke_day_proxy": 0},
    ]

    annual = modulec._aggregate_annual_smoke_days(rows, "smoke_day_proxy")

    assert annual["U1"][2015] == 2.0
    assert annual["U1"][2016] == 0.0


def test_canonical_sensitivity_reproduces_canonical_score():
    rows = [
        {
            "unit_id": "U1",
            "year": 2015,
            "smoke_day_score": 1.5e11,
            "smoke_day_proxy": 1,
            "transport_proxy_sensitivity": {
                "24.0": {"transport_proxy_mean": 1.0, "transport_proxy_max": 3.0}
            },
        },
        {
            "unit_id": "U2",
            "year": 2015,
            "smoke_day_score": 1.0e11,
            "smoke_day_proxy": 0,
            "transport_proxy_sensitivity": {
                "24.0": {"transport_proxy_mean": 0.5, "transport_proxy_max": 1.5}
            },
        },
    ]

    sensitivity = modulec._sensitivity_rows(rows, {"U1": 1.0})
    canonical = next(row for row in sensitivity if row[0] == 24.0 and row[1] == 0.75 and row[2] == 0.25)

    assert abs(canonical[3] - 1.0) < 1.0e-12
    assert abs(canonical[4] - 1.0) < 1.0e-12


def test_decoder_aggregates_two_valid_receptors_after_transport():
    class FakeArray:
        shape = (1, 4)

        def __getitem__(self, index):
            return [[1.0, 0.0, 0.0, 4.0]][index]

    class FakeBand:
        def GetMetadata(self):
            return {}

        def GetNoDataValue(self):
            return None

        def ReadAsArray(self, *_args):
            return FakeArray()

    class FakeDataset:
        RasterXSize = 4
        RasterYSize = 1

        def GetRasterBand(self, _index):
            return FakeBand()

        def GetGeoTransform(self, can_return_null=True):
            return (0.0, 1.0, 0.0, 1.0, 0.0, -1.0)

    samples = [
        {"unit_id": "U1", "unit_name": "Unit 1", "unit_level": "NUTS3", "lon": 0.5, "lat": 0.5, "sample_index": 1},
        {"unit_id": "U1", "unit_name": "Unit 1", "unit_level": "NUTS3", "lon": 3.5, "lat": 0.5, "sample_index": 2},
    ]
    wind = {"2020-01-01": {"U1": {1: {"u10_mps": 5.0, "v10_mps": 0.0}, 2: {"u10_mps": 5.0, "v10_mps": 0.0}}}}

    payload = modulec._decode_gfas_pm_dataset_to_unit_rows(
        FakeDataset(),
        "sample.grib",
        1,
        "2020-01-01",
        samples,
        payload_size=1,
        era5_wind_by_date_unit=wind,
    )
    row = payload["unit_rows"][0]

    assert row["receptor_count"] == 2
    assert row["valid_receptor_count"] == 2
    assert row["transport_proxy_mean"] != row["transport_proxy_max"]
    assert row["transport_proxy_sensitivity"]["24.0"]["valid_receptor_count"] == 2
