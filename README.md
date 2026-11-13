# ◈ Jezero Safe Walk — Mission Planner

**NASA Space Apps Cairo 2026** | **Challenge:** Interplanetary Survival Guide: Martian Map

Jezero Safe Walk is a web-based Extravehicular Activity (EVA) mission planning tool designed for the first human astronauts on Mars. Unlike static map layers, this tool acts as a dynamic **Mission Planner** that calculates and compares the **Safest** and **Shortest** routes across Jezero Crater based on the astronaut's suit profile.

## 🚀 Key Features

* **Safest vs. Shortest Route Comparison:** Visualizes both routes simultaneously to show the trade-off between distance and terrain safety.
* **Suit Profiles:** Adjustable threshold sliders (Conservative, Standard, Extended) that instantly recalculate the route based on the astronaut's capabilities.
* **Mission Brief:** Calculates distance, estimated walking time, total ascent/descent, max slope, and overall risk level for the selected path.
* **Scientific Validation:** Proves its accuracy by correlating the computed DEM slope with actual Perseverance rover telemetry over 32,003 points (Pitch correlation: 0.886).
* **Interactive Map:** Features a 20m/pixel DEM, colored slope overlays, the actual Perseverance rover track, and labeled science targets.
* **Thermal Window:** Displays a daily temperature curve to help plan the best time for an EVA (Source: NASA M20 First Weather Report).
* **Data Provenance & Limitations:** Built-in modals that clearly document data sources, assumptions, and the limitations of using a 20m DEM for human navigation.

## 🛠️ Tech Stack

* **Frontend:** HTML5, CSS3, Vanilla JavaScript (ES Modules)
* **Mapping:** Leaflet.js (using `L.CRS.Simple` for image overlays)
* **Routing:** Custom A* (A-Star) algorithm running entirely in the browser (delivered by Data Scientist).
* **Charts:** Custom HTML5 Canvas API (for elevation, slope, and thermal profiles).

## 📊 Data Sources

* **Terrain Elevation:** USGS / NASA (M20 Jezero Crater CTXDEM 20m)
* **Rover Telemetry & Path:** NASA PDS (Perseverance PLACES dataset)
* **Science Targets:** NASA Mars Trek
* **Slope Calculation:** Horn 3x3 finite-difference method.

## 💻 How to Run Locally

1. Clone the repository:
   ```bash
   git clone https://github.com/Ali-Ahmed-Farag/jezero-safe-walk.git
   cd jezero-safe-walk