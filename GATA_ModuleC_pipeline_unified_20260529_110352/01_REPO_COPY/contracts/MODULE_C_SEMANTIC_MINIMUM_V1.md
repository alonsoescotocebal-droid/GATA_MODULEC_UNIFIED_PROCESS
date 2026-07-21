# Module C semantic minimum contract v1

Status: required before the canonical scientific runtime.

## OC-05 — population smoke burden proxy

- Primary indicator: `population_smoke_burden_proxy`.
- Unit: proxy person-hours, calculated from smoke-day signal multiplied by the declared population surface.
- This is an operational burden proxy, not a normalized IECH and not a measured pollutant concentration.
- No health-exposure, epidemiological, or causal claim is allowed from this proxy alone.
- A future normalized IECH may be added only with an explicit formula and independent exposure layer.

## OC-07 — territorial context

- The minimum accepted implementation is `built-up/fuel territorial proxy`.
- It must be labelled as territorial context unless a formal WUI definition and input layer are explicitly resolved.
- The proxy must not be renamed to formal WUI without a semantic gate update.

## OC-09 — integrated screening matrix

- The canonical interpretation is `integrated screening/association matrix`.
- It may rank or associate IECH, smoke, population, recurrence, WRB, and territorial context.
- It is not a causal identification design and must not claim causality without an independent causal methodology.

## Municipal resolution

- Municipal values are assigned under the resolved spatial signal and must record whether the atmospheric signal is direct municipal estimation or regional/NUTS3 allocation.
- Regional allocation must be labelled `MUNICIPAL_ALLOCATION_UNDER_REGIONAL_SIGNAL`.
- It must not be presented as direct municipal concentration measurement.

## Required machine-readable status

```text
OC05_SEMANTIC=POPULATION_SMOKE_BURDEN_PROXY
OC07_SEMANTIC=BUILT_UP_FUEL_TERRITORIAL_PROXY
OC09_SEMANTIC=INTEGRATED_SCREENING_ASSOCIATION
MUNICIPAL_SIGNAL=EXPLICIT_DIRECT_OR_REGIONAL_ALLOCATION
```
