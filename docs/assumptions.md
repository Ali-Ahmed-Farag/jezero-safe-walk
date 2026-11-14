# Scientific Assumptions, Methodology, and Limitations

## 1. Purpose & Operational Disclaimer
- **Preliminary Mission Planning Only:** Jezero Safe Walk is an exploratory mission-planning prototype designed to evaluate terrain traversability in Jezero Crater. It is **not** certified for real-time surface navigation or life-critical EVA operations.
- **Estimated Outputs:** All computed routes, slopes, distances, traversal durations, and safety indicators are model-based estimates derived from orbital elevation data.

## 2. Terrain Slope & Cost Modeling Assumptions
- **DEM Spatial Resolution (20 m/pixel):** Terrain slope is derived from the 20 m/pixel CTX Digital Elevation Model (`dem_20m_crop.tif`) using Horn's 3×3 finite-difference method with real metric pixel dimensions (`20.0 m × 20.0 m`).
- **Quantization & Encoding:** Computed slopes are quantized into `Uint8` (`slope_u8.bin`) using `slope_scale = 4` (`0.25°` resolution, capped at `63.75°`). Grid borders and `NoData` cells are assigned `63.75°` (`255`) so the pathfinder treats them as strictly impassable.
- **Heuristic Suit Mobility Profiles:** The suit profiles (`Conservative: 6°/10°`, `Standard: 10°/16°`, `Extended: 14°/20°`) are tunable planning thresholds anchored to Perseverance traverse statistics (>99% of rover driving occurs below `~16°`, with an observed peak near `21.7°`). They do **not** represent certified NASA spacesuit biomechanical limits.
- **Step Cost Formulation:**
  - `Safest` mode penalizes steeper terrain quadratically: $\text{cost} = d \times \left(1 + \left(\frac{s_{\text{avg}}}{s_{\text{safe}}}\right)^2\right)$, where $d$ is step distance (`20 m` orthogonal, `28.28 m` diagonal).
  - `Shortest` mode minimizes Euclidean distance ($d$) while still strictly rejecting any cell or edge exceeding `forbidden`.
- **Walking Speed Assumption:** Estimated traversal duration defaults to `2.0 km/h` (`~0.56 m/s`), adjustable by the user, without modeling metabolic fatigue, rest stops, or thermal/solar constraints.

## 3. Validation Findings & Scale Limitations (Orbital DEM vs. Rover Telemetry)
Validation across **32,003** localized Perseverance waypoints (`frame = ROVER`) demonstrates strong physical agreement between orbital DEM gradients and rover IMU orientation:
- **Directional Pitch:** $r = 0.8858$, $\text{RMSE} = 2.78^\circ$, $\text{Mean Bias} = -0.03^\circ$.
- **Directional Roll:** $r = 0.8612$, $\text{RMSE} = 2.94^\circ$, $\text{Mean Bias} = -0.04^\circ$.
- **Total Tilt ($\sqrt{\text{pitch}^2 + \text{roll}^2}$) vs. DEM Slope:** $r = 0.8428$, $\text{RMSE} = 2.73^\circ$.
- **Elevation Datum Agreement:** $\text{Mean Bias} = -0.58\text{ m}$, $\text{RMSE (bias-corrected)} = 3.11\text{ m}$.
- **Rover Replay (~4.0 km segment, Sols 537–719):** The `safest` A* planner computed a route in `6.12 ms` with a maximum DEM slope of `9.86°` (vs. `14.40°` along the actual traverse), with `73.77%` of planned waypoints lying within `100 m` of Perseverance's actual track.

### Key Physical Limitations
1. **Sub-Pixel Hazard Smoothing (20 m vs. 3 m Wheelbase):** A `20 m × 20 m` pixel averages elevation over `400 m²`, smoothing out meter-scale boulders, steep crater rims, sand ripples, and scarps that directly affect a `~3 m` rover wheelbase or a human astronaut.
2. **Active Hazard Avoidance Bias:** Perseverance uses autonomous hazard avoidance (AutoNav) and ground-in-the-loop planning to steer around local obstacles inside a 20 m pixel, which explains why actual rover tilt in steep DEM bins (`10–15°` DEM slope → `11.68°` mean rover tilt) is slightly lower than the macro-scale orbital slope.
3. **Surface Regolith & Thermal Constraints Not Modeled:** Slope alone does not capture wheel/boot sinkage in loose aeolian sand (e.g., mega-ripples), rock sharpness, dust hazards, or diurnal temperature windows.