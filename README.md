# Jezero Safe Walk

NASA Space Apps Challenge 2026 — challenge "Interplanetary Survival Guide: Martian Map"

Jezero Safe Walk is a layered web map of Jezero Crater with a safe-route planner for a Mars EVA, a suggested time-of-day window, and validation of our slope computation against Perseverance's real traverse.

## Team

| Name | Role |
| --- | --- |
|  | Data Engineer 1 |
|  | Data Engineer 2 |
|  | Data Scientist |
|  | Full Stack |

## Repo structure

- `data/raw/` — original source data, kept local and never committed.
- `data/processed/` — derived layers and intermediate data products.
- `pipeline/` — processing code for terrain, slope, and route inputs.
- `analysis/` — notebooks and validation against Perseverance's traverse.
- `web/` — the layered web map and safe-route planner.
- `docs/` — project documentation and the data source register.

## Data

Raw data is not committed. See docs/sources.md for links.

## License

Apache 2.0 (see LICENSE).

Work in progress. Project is built during the hackathon, Nov 14-15, 2026.
