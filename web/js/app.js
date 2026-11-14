import { loadGridMeta, loadElevation, loadSlope } from './data-loader.js';
import { createSlopeCanvas } from './map/raster-layers.js';
import { loadJSON, projectGeoJSON, addRoverTrack, addScienceTargets } from './map/vector-layers.js';
import { handleMapClick, calculateAndDrawRoute, clearRoute } from './routing/route-controller.js';
import { drawProfile } from './charts/elevation-profile.js';
import { drawValidationScatter } from './charts/validation-chart.js';
import { latLonToRowCol, rowColToLatLon } from './grid-utils.js';

const state = {
  meta: null, slope: null, elev: null, start: null, end: null,
  profile: { safe: 10, hard: 16, forbidden: 16 },
  thermal: null, roverTrack: null,
  speedKmh: 2,
  routeMode: 'safest',      // exposed via the map toolbar mode switch (safest | shortest)
  scenarioName: null,       // set when a canonical preset is used; null for manual map-click routes
};

const SUIT_PRESETS = {
  conservative: { safe: 6, hard: 10, forbidden: 10 },
  standard: { safe: 10, hard: 16, forbidden: 16 },
  extended: { safe: 14, hard: 20, forbidden: 20 },
};

const map = L.map("map", {
  zoomControl: true, attributionControl: false, crs: L.CRS.Simple, minZoom: -4, maxZoom: 4
});

const ui = { hint: document.getElementById("map-hint") };
let slopeOverlay = null, roverLayer = null, targetsLayer = null;

function setScenarioLabel(name) {
  const el = document.getElementById('mb-scenario');
  if (el) el.textContent = name || '—';
}
let currentMetrics = null;

let calcTimeout = null;
let currentRequestId = 0;

function debouncedCalculateRoute(map, state, ui, callback, mode) {
  clearTimeout(calcTimeout);
  calcTimeout = setTimeout(() => {
    ui.hint.textContent = "Calculating route...";
    ui.hint.style.color = "var(--accent)";
    currentRequestId++;
    const reqId = currentRequestId;
    setTimeout(() => {
      const res = calculateAndDrawRoute(map, state, ui, callback, mode);
      if (reqId !== currentRequestId) return;
      ui.hint.style.color = "var(--text)";
      if (res) callback(res.result, res.metrics);
      else { ui.hint.textContent = "No safe route found or invalid points."; callback(null, null); }
    }, 10);
  }, 150);
}

function testGridRoundtrip(meta) {
  const landingSite = { lat: 18.4446, lon: 77.4509 };
  const rc = latLonToRowCol(landingSite.lat, landingSite.lon, meta);
  const ll = rowColToLatLon(rc.row, rc.col, meta);
  if (Math.abs(ll.lat - landingSite.lat) > 0.0001 || Math.abs(ll.lon - landingSite.lon) > 0.0001) {
    console.error(`Grid roundtrip FAILED.`);
  } else {
    console.log(`Grid roundtrip SUCCESS. Landing site at row=${Math.round(rc.row)}, col=${Math.round(rc.col)}`);
  }
}

function haversine(lat1, lon1, lat2, lon2) {
  const R = 3389500;
  const p1 = lat1 * Math.PI/180, p2 = lat2 * Math.PI/180;
  const dp = (lat2-lat1) * Math.PI/180, dl = (lon2-lon1) * Math.PI/180;
  const a = Math.sin(dp/2) * Math.sin(dp/2) + Math.cos(p1) * Math.cos(p2) * Math.sin(dl/2) * Math.sin(dl/2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}
function findClosestIndex(track, tLat, tLon) {
  let minDist = Infinity, bestIdx = 0;
  for (let i = 0; i < track.length; i++) {
    const d = haversine(tLat, tLon, track[i][1], track[i][0]);
    if (d < minDist) { minDist = d; bestIdx = i; }
  }
  return bestIdx;
}
function calcApproxRoverDistance(geojson, start, end) {
  if (!geojson || !geojson.features) return null;
  const trackFeature = geojson.features.find(f => f.geometry.type === 'LineString');
  if (!trackFeature) return null;
  const track = trackFeature.geometry.coordinates;
  const startIdx = findClosestIndex(track, start[0], start[1]);
  const endIdx = findClosestIndex(track, end[0], end[1]);
  let dist = 0;
  const minIdx = Math.min(startIdx, endIdx), maxIdx = Math.max(startIdx, endIdx);
  for (let i = minIdx; i < maxIdx; i++) dist += haversine(track[i][1], track[i][0], track[i+1][1], track[i+1][0]);
  return dist / 1000;
}

async function boot() {
  try {
    ui.hint.textContent = "Loading data...";
    state.meta = await loadGridMeta();
    const expectedCells = state.meta.width * state.meta.height;
    testGridRoundtrip(state.meta);
    state.elev = await loadElevation('./data/elev_dm_i16.bin', expectedCells);
    state.slope = await loadSlope('./data/slope_u8.bin', expectedCells);

    const mapBounds = [[0, 0], [state.meta.height, state.meta.width]];
    map.setView([state.meta.height / 2, state.meta.width / 2], 1);

    // Add CTX Basemap
    try {
      const ctxLayer = L.imageOverlay('./data/ctx_basemap.jpg', mapBounds, { opacity: 1.0, interactive: false }).addTo(map);
      document.getElementById('layer-ctx').addEventListener('change', (e) => e.target.checked ? ctxLayer.addTo(map) : map.removeLayer(ctxLayer));
      document.getElementById('opacity-ctx').addEventListener('input', (e) => ctxLayer.setOpacity(e.target.value / 100));
      ctxLayer.bringToBack();
    } catch(e) {}

    // Add Hillshade
    try {
      const hsLayer = L.imageOverlay('./data/hillshade.png', mapBounds, { opacity: 0.6, interactive: false }).addTo(map);
      document.getElementById('layer-hillshade').addEventListener('change', (e) => e.target.checked ? hsLayer.addTo(map) : map.removeLayer(hsLayer));
      document.getElementById('opacity-hillshade').addEventListener('input', (e) => hsLayer.setOpacity(e.target.value / 100));
      hsLayer.bringToBack();
    } catch(e) {}

    // Add Geologic Map (P2 Optional)
    try {
      const geoLayer = L.imageOverlay('./data/geologic_map.png', mapBounds, { opacity: 0.4, interactive: false });
      document.getElementById('layer-geologic').addEventListener('change', (e) => e.target.checked ? geoLayer.addTo(map) : map.removeLayer(geoLayer));
      document.getElementById('opacity-geologic').addEventListener('input', (e) => geoLayer.setOpacity(e.target.value / 100));
      geoLayer.bringToBack();
    } catch(e) {}

    updateSlopeOverlay(mapBounds);

    state.roverTrack = await loadJSON('./data/rover_track.geojson');
    roverLayer = addRoverTrack(map, projectGeoJSON(state.roverTrack, state.meta));

    const targetsGeoJSON = await loadJSON('./data/science_targets.geojson');
    targetsLayer = addScienceTargets(map, projectGeoJSON(targetsGeoJSON, state.meta));

    setupLayerControls();
    await setupPresets();
    await setupValidation();
    await setupThermal();
    setupMapToolbar();
    setupOpacityReadouts();
    setupHeroActions();
    setupMiniCards();
    
    document.getElementById('input-speed').addEventListener('input', (e) => {
      state.speedKmh = parseFloat(e.target.value) || 2;
      if (currentMetrics) {
        const newTime = (currentMetrics.length_km / state.speedKmh).toFixed(2);
        document.getElementById('mb-time').textContent = `${newTime} h`;
      }
    });

    ui.hint.textContent = "Click to set Start";
  } catch (error) {
    console.error("Boot failed:", error);
    ui.hint.textContent = "Error loading data. Please refresh.";
  }
}

async function setupPresets() {
  try {
    const presetsData = await loadJSON('./data/presets.json');
    const presetsMenu = document.getElementById('presets-dropdown');
    presetsData.forEach(p => {
      const btn = document.createElement('button');
      let roverDistText = "";
      if (p.rover_distance_km) roverDistText = ` (${p.rover_distance_km} km)`;
      else if (state.roverTrack) {
        const calcDist = calcApproxRoverDistance(state.roverTrack, p.start, p.end);
        if (calcDist !== null) roverDistText = ` (~${calcDist.toFixed(2)} km Approx)`;
      }
      
      btn.textContent = `${p.title || p.name || p.id}${roverDistText}`;
      btn.title = "Distance is approximate, calculated from the simplified rover path (~50m spacing).";
      
      btn.addEventListener('click', () => {
        presetsMenu.style.display = 'none';
        const startRC = latLonToRowCol(p.start[0], p.start[1], state.meta);
        const endRC = latLonToRowCol(p.end[0], p.end[1], state.meta);
        map.eachLayer(layer => {
          if (layer instanceof L.Polyline) map.removeLayer(layer);
          if (layer instanceof L.CircleMarker) map.removeLayer(layer);
        });
        // B9 (F1): canonical grid mapping per grid_meta.notes — floor-based over the
        // half-open domain [lon_min, lon_max) x (lat_min, lat_max], range-checked.
        // (Math.round could shift an exact endpoint by up to one ~20 m pixel and
        // produced route lengths inconsistent with the DS matrix, e.g. scenario_5.)
        const canonicalRC = (rc) => {
          const row = Math.floor(rc.row), col = Math.floor(rc.col);
          if (!Number.isInteger(row) || !Number.isInteger(col) ||
              row < 0 || row >= state.meta.height || col < 0 || col >= state.meta.width) {
            return null;
          }
          return [row, col];
        };
        state.start = canonicalRC(startRC);
        state.end = canonicalRC(endRC);
        if (!state.start || !state.end) {
          ui.hint.textContent = "Preset endpoint outside the grid.";
          return;
        }
        state.scenarioName = `${p.title || p.name || p.id} (preset)`;
        setScenarioLabel(state.scenarioName);
        L.circleMarker([state.start[0], state.start[1]], { radius: 7, color: '#fff', fillColor: '#3FB950', fillOpacity: 1, weight: 2 }).addTo(map);
        L.circleMarker([state.end[0], state.end[1]], { radius: 7, color: '#fff', fillColor: '#F85149', fillOpacity: 1, weight: 2 }).addTo(map);
        debouncedCalculateRoute(map, state, ui, updateMissionBrief, state.routeMode);
      });
      presetsMenu.appendChild(btn);

      // NOVA scenario card (bottom) reuses the exact same canonical handler
      const cardBtn = document.createElement('button');
      cardBtn.className = 'scenario-btn';
      cardBtn.type = 'button';
      cardBtn.innerHTML = `<span>${p.title || p.id}</span><span class="sdist">${p.rover_distance_km != null ? p.rover_distance_km.toFixed(3) + ' km' : ''}</span>`;
      cardBtn.title = 'Plan this scenario (safest/shortest follows the map toolbar mode)';
      cardBtn.addEventListener('click', () => btn.click());
      const scenarioList = document.getElementById('scenario-list');
      if (scenarioList) scenarioList.appendChild(cardBtn);
    });

    document.getElementById('btn-presets').addEventListener('click', (e) => {
      e.stopPropagation();
      presetsMenu.style.display = presetsMenu.style.display === 'none' ? 'flex' : 'none';
    });
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#btn-presets') && !e.target.closest('#btn-scenarios-hero')) presetsMenu.style.display = 'none';
    });
  } catch (err) { console.warn("Presets not loaded", err); }
}

function updateSlopeOverlay(bounds) {
  if (slopeOverlay) map.removeLayer(slopeOverlay);
  const canvas = createSlopeCanvas(state.slope, state.meta.width, state.meta.height, state.profile);
  const url = canvas.toDataURL("image/png");
  const currentOpacity = document.getElementById('opacity-slope') ? document.getElementById('opacity-slope').value / 100 : 0.7;
  slopeOverlay = L.imageOverlay(url, bounds, { opacity: currentOpacity, interactive: false }).addTo(map);
  slopeOverlay.bringToFront();
  updateLegend();
}

function updateLegend() {
  const legendDiv = document.getElementById('slope-legend');
  if (!legendDiv) return;
  legendDiv.innerHTML = `
    <div class="legend-item"><span class="legend-color" style="background: #3FB950;"></span> Safe (&lt; ${state.profile.safe}°)</div>
    <div class="legend-item"><span class="legend-color" style="background: #E3B341;"></span> Hard (&lt; ${state.profile.hard}°)</div>
    <div class="legend-item"><span class="legend-color" style="background: #F85149;"></span> Forbidden</div>
  `;
}

function setupLayerControls() {
  document.getElementById('layer-slope').addEventListener('change', (e) => e.target.checked ? slopeOverlay.addTo(map) : map.removeLayer(slopeOverlay));
  document.getElementById('opacity-slope').addEventListener('input', (e) => slopeOverlay.setOpacity(e.target.value / 100));
  document.getElementById('layer-rover').addEventListener('change', (e) => e.target.checked ? roverLayer.addTo(map) : map.removeLayer(roverLayer));
  document.getElementById('opacity-rover').addEventListener('input', (e) => roverLayer.setStyle({ opacity: e.target.value / 100, fillOpacity: e.target.value / 100 }));
  document.getElementById('layer-targets').addEventListener('change', (e) => e.target.checked ? targetsLayer.addTo(map) : map.removeLayer(targetsLayer));
  document.getElementById('opacity-targets').addEventListener('input', (e) => targetsLayer.setStyle({ opacity: e.target.value / 100, fillOpacity: e.target.value / 100 }));
}

function updateThermalRec() {
  const recEl = document.getElementById('mb-thermal-rec');
  if (state.thermal && state.thermal.curve && state.thermal.data_kind === "extrema_only") {
    const dayT = state.thermal.curve.find(p => p.label === 'Day High')?.temp || -22;
    const nightT = state.thermal.curve.find(p => p.label === 'Night Low')?.temp || -83;
    recEl.innerHTML = `<strong>EVA Window:</strong> Suggested daytime EVA (Day: ${dayT}${state.thermal.unit}, Night: ${nightT}${state.thermal.unit}). ${state.thermal.note}`;
  }
}

function updateMissionBrief(route, metrics) {
  currentMetrics = metrics;
  updateThermalRec();

  if (!metrics) {
    ['mb-dist', 'mb-time', 'mb-max-slope', 'mb-ascent', 'mb-descent', 'mb-risk'].forEach(id => document.getElementById(id).textContent = '-');
    document.getElementById('mb-risk').className = 'value';
    drawProfile('profile-canvas', null);
    return;
  }

  const time = (metrics.length_km / state.speedKmh).toFixed(2);

  document.getElementById('mb-dist').textContent = `${metrics.length_km} km`;
  document.getElementById('mb-time').textContent = `${time} h`;
  document.getElementById('mb-max-slope').textContent = `${metrics.max_slope}°`;
  document.getElementById('mb-ascent').textContent = `${metrics.ascent_m} m`;
  document.getElementById('mb-descent').textContent = `${metrics.descent_m} m`;
  const riskEl = document.getElementById('mb-risk');
  riskEl.textContent = metrics.risk_level.toUpperCase();
  riskEl.className = 'value';
  if (metrics.risk_level === 'low') riskEl.classList.add('risk-low');
  if (metrics.risk_level === 'medium') riskEl.classList.add('risk-medium');
  if (metrics.risk_level === 'high') riskEl.classList.add('risk-high');
  if (metrics.arrays) setTimeout(() => drawProfile('profile-canvas', metrics.arrays), 50);
}

document.getElementById('btn-compare').addEventListener('click', () => {
  if (!state.start || !state.end) { alert("Please select a Start and Target first."); return; }
  ui.hint.textContent = "Comparing routes...";
  currentRequestId++;
  const reqId = currentRequestId;
  setTimeout(() => {
    const safestRes = calculateAndDrawRoute(map, state, ui, null, "safest");
    const shortestRes = calculateAndDrawRoute(map, state, ui, null, "shortest");
    if (reqId !== currentRequestId) return;

    if (safestRes && shortestRes) {
      document.getElementById('comp-safest-dist').textContent = safestRes.metrics.length_km;
      document.getElementById('comp-shortest-dist').textContent = shortestRes.metrics.length_km;
      document.getElementById('comp-safest-time').textContent = (safestRes.metrics.length_km / state.speedKmh).toFixed(2);
      document.getElementById('comp-shortest-time').textContent = (shortestRes.metrics.length_km / state.speedKmh).toFixed(2);
      document.getElementById('comp-safest-slope').textContent = safestRes.metrics.max_slope;
      document.getElementById('comp-shortest-slope').textContent = shortestRes.metrics.max_slope;
      document.getElementById('comp-safest-ascent').textContent = safestRes.metrics.ascent_m;
      document.getElementById('comp-shortest-ascent').textContent = shortestRes.metrics.ascent_m;

      updateMissionBrief(safestRes.result, safestRes.metrics);
      ui.hint.textContent = "Routes compared!";
      document.getElementById('compare-modal').style.display = 'flex';
    } else ui.hint.textContent = "Comparison failed.";
  }, 10);
});

document.querySelectorAll('input[name="suit"]').forEach(radio => {
  radio.addEventListener('change', (e) => {
    state.profile = { ...SUIT_PRESETS[e.target.value] };
    updateSlopeOverlay([[0, 0], [state.meta.height, state.meta.width]]);
    if (state.start && state.end) {
      map.eachLayer(layer => {
        if (layer instanceof L.Polyline) map.removeLayer(layer);
        if (layer instanceof L.CircleMarker) map.removeLayer(layer);
      });
      state.start = null; state.end = null;
      state.scenarioName = null;
      setScenarioLabel('—');
      ui.hint.textContent = "Profile changed. Click to set Start again.";
      updateMissionBrief(null, null);
    }
  });
});

map.on("click", (e) => {
  if (!state.meta || !state.slope) return;
  handleMapClick(map, e, state, ui, (res, metrics) => {
    if (state.end) {
      if (!state.scenarioName) setScenarioLabel('Custom (map clicks)');
      debouncedCalculateRoute(map, state, ui, updateMissionBrief, state.routeMode);
    } else {
      setScenarioLabel('—');
      updateMissionBrief(null, null);
    }
  });
});

const modals = [
  document.getElementById('about-modal'), document.getElementById('sources-modal'), 
  document.getElementById('validation-modal'), document.getElementById('compare-modal'),
  document.getElementById('thermal-modal')
];
document.getElementById('btn-about').addEventListener('click', () => modals[0].style.display = 'flex');
document.getElementById('btn-sources').addEventListener('click', () => modals[1].style.display = 'flex');
document.getElementById('btn-print').addEventListener('click', () => window.print());
document.querySelectorAll('.close-modal-btn').forEach(btn => btn.addEventListener('click', () => modals.forEach(m => m.style.display = 'none')));
window.addEventListener('click', (e) => modals.forEach(m => { if (e.target === m) m.style.display = 'none'; }));

window.addEventListener('resize', () => {
  setTimeout(() => {
    map.invalidateSize();
    if (currentMetrics && currentMetrics.arrays) drawProfile('profile-canvas', currentMetrics.arrays);
    if (document.getElementById('validation-modal').style.display === 'flex' && state.validationSample) drawValidationScatter('val-scatter-canvas', state.validationSample);
  }, 200);
});

async function setupThermal() {
  try {
    state.thermal = await loadJSON('./data/thermal.json');
    
    document.getElementById('thermal-source').innerHTML = `
      <strong>Source:</strong> ${state.thermal.source} <br>
      <em>Type: ${state.thermal.type.toUpperCase()} (Archival)</em><br>
      <small>Period: ${state.thermal.note || 'N/A'}</small>
    `;

    const container = document.getElementById('thermal-cards-container');
    if (container) {
      container.innerHTML = ''; 
      if (state.thermal.data_kind === 'extrema_only' && state.thermal.curve) {
        state.thermal.curve.forEach(pt => {
          const card = document.createElement('div');
          card.style.cssText = "background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 16px; text-align: center; flex: 1;";
          card.innerHTML = `
            <div style="font-size: 12px; color: var(--text-dim); text-transform: uppercase; margin-bottom: 8px;">${pt.label}</div>
            <div style="font-size: 24px; font-weight: bold; color: var(--accent);">${pt.temp}${state.thermal.unit}</div>
          `;
          container.appendChild(card);
        });
      }
    }

    document.getElementById('btn-thermal').addEventListener('click', () => {
      document.getElementById('thermal-modal').style.display = 'flex';
    });
    
    updateThermalRec();
  } catch (err) {
    console.warn("Thermal data not loaded", err);
  }
}

async function setupValidation() {
  try {
    const valData = await loadJSON('./data/validation_results.json');
    const m = valData.metrics;
    
    document.getElementById('val-pitch-r').textContent = m.pitch.correlation_r.toFixed(3);
    document.getElementById('val-pitch-rmse').textContent = m.pitch.rmse_deg.toFixed(2);
    document.getElementById('val-roll-r').textContent = m.roll.correlation_r.toFixed(3);
    document.getElementById('val-roll-rmse').textContent = m.roll.rmse_deg.toFixed(2);
    document.getElementById('val-elev-bias').textContent = m.elevation.mean_bias_m.toFixed(2);
    document.getElementById('val-interpretation').textContent = valData.summary.scientific_interpretation;

    const rr = valData.rover_replay;
    if (rr) {
      document.getElementById('rr-actual-dist').textContent = rr.actual_rover_distance_m.toFixed(1);
      document.getElementById('rr-actual-mean').textContent = rr.actual_mean_dem_slope_deg.toFixed(2);
      document.getElementById('rr-actual-max').textContent = rr.actual_max_dem_slope_deg.toFixed(2);

      document.getElementById('rr-safest-dist').textContent = rr.safest_astar.distance_m.toFixed(1);
      document.getElementById('rr-safest-mean').textContent = rr.safest_astar.mean_dem_slope_deg.toFixed(2);
      document.getElementById('rr-safest-max').textContent = rr.safest_astar.max_dem_slope_deg.toFixed(2);
      document.getElementById('rr-safest-pct').textContent = rr.safest_astar.pct_within_100m.toFixed(1) + '%';

      document.getElementById('rr-shortest-dist').textContent = rr.baseline_shortest.distance_m.toFixed(1);
      document.getElementById('rr-shortest-mean').textContent = rr.baseline_shortest.mean_dem_slope_deg.toFixed(2);
      document.getElementById('rr-shortest-max').textContent = rr.baseline_shortest.max_dem_slope_deg.toFixed(2);
      document.getElementById('rr-shortest-pct').textContent = rr.baseline_shortest.pct_within_100m.toFixed(1) + '%';
    }

    const tbody = document.getElementById('val-bins-body');
    if (valData.slope_bins && tbody) {
      tbody.innerHTML = '';
      valData.slope_bins.forEach(b => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${b.bin}</td>
          <td>${b.count}</td>
          <td>${b.mean_dem_slope_deg.toFixed(2)}°</td>
          <td>${b.mean_abs_pitch_deg.toFixed(2)}°</td>
          <td>${b.mean_abs_roll_deg.toFixed(2)}°</td>
        `;
        tbody.appendChild(tr);
      });
    }

    if (valData.samples) state.validationSample = valData.samples;

    document.getElementById('btn-validation').addEventListener('click', () => {
      document.getElementById('validation-modal').style.display = 'flex';
      setTimeout(() => {
        if (state.validationSample) drawValidationScatter('val-scatter-canvas', state.validationSample);
      }, 50);
    });
  } catch (err) {
    console.warn("Validation data not loaded", err);
  }
}

/* ===== NOVA additions: map toolbar, opacity readouts, hero CTAs, mini cards ===== */

function setupMapToolbar() {
  // Reset Route — clears layers, state, brief, and hint (audit V-07)
  document.getElementById('btn-reset-route').addEventListener('click', () => {
    clearRoute(map);
    state.start = null;
    state.end = null;
    state.scenarioName = null;
    setScenarioLabel('—');
    updateMissionBrief(null, null);
    ui.hint.textContent = 'Click on the map to set Start';
  });

  // Center on Landing — landing cell from the canonical contract (audit V-07)
  document.getElementById('btn-center-landing').addEventListener('click', () => {
    if (!state.meta) return;
    const rc = latLonToRowCol(18.444627, 77.450886, state.meta); // Octavia E. Butler Landing
    map.setView([Math.floor(rc.row), Math.floor(rc.col)], Math.max(map.getZoom(), 1));
  });

  // Route mode switch — exposes the two modes the router already supports (no algorithm change)
  const modeButtons = [['mode-safest', 'safest'], ['mode-shortest', 'shortest']];
  modeButtons.forEach(([id, mode]) => {
    document.getElementById(id).addEventListener('click', () => {
      if (state.routeMode === mode) return;
      state.routeMode = mode;
      modeButtons.forEach(([bid, m]) => {
        document.getElementById(bid).classList.toggle('active', m === mode);
      });
      if (state.start && state.end) {
        clearRoute(map);
        debouncedCalculateRoute(map, state, ui, updateMissionBrief, mode);
      }
    });
  });
}

function setupOpacityReadouts() {
  document.querySelectorAll('.layer-item input[type="range"]').forEach(range => {
    const out = range.closest('.layer-item')?.querySelector('.opacity-value');
    const upd = () => { if (out) out.textContent = range.value + '%'; };
    range.addEventListener('input', upd);
    upd();
  });
}

function setupHeroActions() {
  const heroScenarios = document.getElementById('btn-scenarios-hero');
  if (heroScenarios) heroScenarios.addEventListener('click', () => {
    document.getElementById('btn-presets').click();
  });
  const startPlanning = document.getElementById('btn-start-planning');
  if (startPlanning) startPlanning.addEventListener('click', () => {
    document.getElementById('btn-center-landing').click();
    document.getElementById('map').scrollIntoView({ behavior: 'smooth', block: 'start' });
    ui.hint.textContent = 'Click on the map to set Start';
  });
  const btnNavMap = document.getElementById('btn-nav-map');
  if (btnNavMap) btnNavMap.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

function setupMiniCards() {
  // Thermal mini chips (same data as the modal, no new values invented)
  if (state.thermal && state.thermal.data_kind === 'extrema_only' && state.thermal.curve) {
    const mini = document.getElementById('thermal-mini');
    if (mini) {
      mini.innerHTML = '';
      state.thermal.curve.forEach(pt => {
        const chip = document.createElement('div');
        chip.className = 'thermal-chip';
        const cls = pt.label === 'Night Low' ? 'cold' : 'hot';
        chip.innerHTML = `<span class="t-label">${pt.label}</span><span class="t-value ${cls}">${pt.temp}${state.thermal.unit}</span>`;
        mini.appendChild(chip);
      });
    }
    const open = document.getElementById('btn-thermal-open');
    if (open) open.addEventListener('click', () => document.getElementById('btn-thermal').click());
  }
  // Validation mini stats + link to the full modal
  const pitch = document.getElementById('val-pitch-r')?.textContent;
  const roll = document.getElementById('val-roll-r')?.textContent;
  const pct = document.getElementById('rr-safest-pct')?.textContent;
  if (pitch) document.getElementById('val-mini-pitch').textContent = pitch;
  if (roll) document.getElementById('val-mini-roll').textContent = roll;
  if (pct) document.getElementById('val-mini-replay').textContent = pct;
  const openVal = document.getElementById('btn-validation-open');
  if (openVal) openVal.addEventListener('click', () => document.getElementById('btn-validation').click());
}

boot();