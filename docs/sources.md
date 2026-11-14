# Sources and Licenses

## Data Sources
| File | Purpose | Source | Link | License/Terms |
|---|---|---|---|---|
| M20_JezeroCrater_CTXDEM_20m.tif | Base DEM for slope & routing | USGS / NASA | [USGS Astrogeology](https://astrogeology.usgs.gov/search/map/mars-2020-jezero-crater-landing-site-products) | Public Domain (NASA/USGS) |
| ctx_basemap.jpg | Base map imagery | NASA Mars Trek | [Mars Trek](https://trek.nasa.gov/mars/) | Public Domain (NASA) |
| hillshade.png | Terrain shading | Computed from DEM | - | Derived from USGS DEM |
| best_interp.csv (+ .xml) | Perseverance rover track | NASA PDS (PLACES) | [PDS Analyst's Notebook](https://an.rsl.wustl.edu/m20/) | Public Domain (NASA) |
| science_targets.geojson | Science targets locations | NASA Mars Trek / Mission Plan | - | Public Domain (NASA) |
| Thermal Data (cited) | Daily temperature curve | NASA M20 First Weather Report | - | Cited (Archival) |

## Libraries and Tools
| Library | Usage | Version | License |
|---|---|---|---|
| Leaflet.js | Interactive map | 1.9.4 | BSD-2-Clause |
| Inter (Font) | UI Typography | Google Fonts | SIL Open Font License 1.1 |

## AI Usage Disclosure
- **Code Generation:** The frontend (HTML, CSS, JavaScript) was developed with the assistance of AI tools (DeepSeek and Claude) to accelerate UI development, implement the Canvas charting logic, and integrate the A* algorithm. 
- **Data Science & Engineering:** The core algorithms (`astar.js`, `metrics.js`), data processing (DEM cropping, slope calculation), and validation metrics were developed by the team's Data Scientist and Data Engineers. AI was used for documentation review and formatting.