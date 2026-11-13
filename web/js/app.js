import { loadGridMeta, loadElevation, loadSlope } from './data-loader.js';
import { createSlopeCanvas } from './map/raster-layers.js';
import { loadJSON, projectGeoJSON, addRoverTrack, addScienceTargets } from './map/vector-layers.js';
import { handleMapClick, calculateAndDrawRoute } from './routing/route-controller.js';
import { drawProfile } from './charts/elevation-profile.js';
import { latLonToRowCol, rowColToLatLon } from './grid-utils.js';

const state = {
  meta: null, slope: null, elev: null, start: null, end: null,
  profile: { safe: 10, hard: 16, forbidden: 16 },
  thermal: null, roverTrack: null,
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
let currentMetrics = null;

// --- P0-4: Debounce Logic ---
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
      if (res) {
        callback(res.result, res.metrics);
      } else {
        ui.hint.textContent = "No safe route found or invalid points.";
        callback(null, null);
      }
    }, 10);
  }, 150);
}

// P0-6: Grid Alignment Test
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

// P0-2: Approximate Distance Calculation
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

    updateSlopeOverlay(mapBounds);
    setupMissingLayers();

    state.roverTrack = await loadJSON('./data/rover_track.geojson');
    roverLayer = addRoverTrack(map, projectGeoJSON(state.roverTrack, state.meta));

    const targetsGeoJSON = await loadJSON('./data/science_targets.geojson');
    targetsLayer = addScienceTargets(map, projectGeoJSON(targetsGeoJSON, state.meta));

    setupLayerControls();
    await setupPresets();
    await setupValidation();
    await setupThermal();

    ui.hint.textContent = "Click to set Start";
  } catch (error) {
    console.error("Boot failed:", error);
    ui.hint.textContent = "Error loading data. Please refresh.";
  }
}

function setupMissingLayers() {
  const ctxToggle = document.getElementById('layer-ctx');
  const hsToggle = document.getElementById('layer-hillshade');
  if(ctxToggle) { ctxToggle.disabled = true; ctxToggle.parentElement.title = "Layer not available yet"; ctxToggle.parentElement.style.opacity = 0.5; }
  if(hsToggle) { hsToggle.disabled = true; hsToggle.parentElement.title = "Layer not available yet"; hsToggle.parentElement.style.opacity = 0.5; }
}

async function setupPresets() {
  try {
    const presetsData = await loadJSON('./data/presets.json');
    const presetsMenu = document.getElementById('presets-dropdown');
    
    presetsData.forEach(p => {
      const btn = document.createElement('button');
      let roverDistText = "";
      if (p.rover_distance_km) {
        roverDistText = ` (${p.rover_distance_km} km)`;
      } else if (state.roverTrack) {
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

        state.start = [Math.round(startRC.row), Math.round(startRC.col)];
        state.end = [Math.round(endRC.row), Math.round(endRC.col)];

        L.circleMarker([state.start[0], state.start[1]], { radius: 7, color: '#fff', fillColor: '#3FB950', fillOpacity: 1, weight: 2 }).addTo(map);
        L.circleMarker([state.end[0], state.end[1]], { radius: 7, color: '#fff', fillColor: '#F85149', fillOpacity: 1, weight: 2 }).addTo(map);

        debouncedCalculateRoute(map, state, ui, updateMissionBrief, "safest");
      });
      presetsMenu.appendChild(btn);
    });

    document.getElementById('btn-presets').addEventListener('click', (e) => {
      e.stopPropagation();
      presetsMenu.style.display = presetsMenu.style.display === 'none' ? 'flex' : 'none';
    });
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#btn-presets')) presetsMenu.style.display = 'none';
    });
  } catch (err) {
    console.warn("Presets not loaded", err);
  }
}

function updateSlopeOverlay(bounds) {
  if (slopeOverlay) map.removeLayer(slopeOverlay);
  const canvas = createSlopeCanvas(state.slope, state.meta.width, state.meta.height, state.profile);
  const url = canvas.toDataURL("image/png");
  const currentOpacity = document.getElementById('opacity-slope') ? document.getElementById('opacity-slope').value / 100 : 0.7;
  slopeOverlay = L.imageOverlay(url, bounds, { opacity: currentOpacity, interactive: false }).addTo(map);
  slopeOverlay.bringToBack();
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

function updateMissionBrief(route, metrics) {
  currentMetrics = metrics;
  if (!metrics) {
    ['mb-dist', 'mb-time', 'mb-max-slope', 'mb-ascent', 'mb-descent', 'mb-risk'].forEach(id => document.getElementById(id).textContent = '-');
    document.getElementById('mb-risk').className = 'value';
    drawProfile('profile-canvas', null);
    return;
  }
  document.getElementById('mb-dist').textContent = `${metrics.length_km} km`;
  document.getElementById('mb-time').textContent = `${metrics.time_h} h`;
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
  if (!state.start || !state.end) {
    alert("Please select a Start and Target first.");
    return;
  }
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
      document.getElementById('comp-safest-time').textContent = safestRes.metrics.time_h;
      document.getElementById('comp-shortest-time').textContent = shortestRes.metrics.time_h;
      document.getElementById('comp-safest-slope').textContent = safestRes.metrics.max_slope;
      document.getElementById('comp-shortest-slope').textContent = shortestRes.metrics.max_slope;
      document.getElementById('comp-safest-ascent').textContent = safestRes.metrics.ascent_m;
      document.getElementById('comp-shortest-ascent').textContent = shortestRes.metrics.ascent_m;

      updateMissionBrief(safestRes.result, safestRes.metrics);
      ui.hint.textContent = "Routes compared!";
      document.getElementById('compare-modal').style.display = 'flex';
    } else {
      ui.hint.textContent = "Comparison failed.";
    }
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
      ui.hint.textContent = "Profile changed. Click to set Start again.";
      updateMissionBrief(null, null);
    }
  });
});

map.on("click", (e) => {
  if (!state.meta || !state.slope) return;
  handleMapClick(map, e, state, ui, (res, metrics) => {
    if (state.end) {
      debouncedCalculateRoute(map, state, ui, updateMissionBrief, "safest");
    } else {
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
    if (state.thermal && document.getElementById('thermal-modal').style.display === 'flex') drawThermalChart(state.thermal);
  }, 200);
});

async function setupThermal() {
  try {
    state.thermal = await loadJSON('./data/thermal.json');
    document.getElementById('thermal-source').innerHTML = `<strong>Source:</strong> ${state.thermal.source} <br><em>Type: ${state.thermal.type.toUpperCase()} (Historical Archive)</em>`;
    document.getElementById('btn-thermal').addEventListener('click', () => {
      document.getElementById('thermal-modal').style.display = 'flex';
      setTimeout(() => drawThermalChart(state.thermal), 50); 
    });
  } catch (err) {}
}
function drawThermalChart(data) {
  const canvas = document.getElementById('thermal-canvas');
  if (!canvas) return;
  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = parent.clientWidth * dpr;
  canvas.height = parent.clientHeight * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const width = parent.clientWidth, height = parent.clientHeight;
  ctx.clearRect(0, 0, width, height);
  const curve = data.curve, padding = { top: 20, right: 20, bottom: 30, left: 40 };
  const w = width - padding.left - padding.right, h = height - padding.top - padding.bottom;
  let minTemp = Math.min(...curve.map(c => c.temp)), maxTemp = Math.max(...curve.map(c => c.temp));
  const scaleX = (hour) => padding.left + (hour / 24) * w;
  const scaleY = (temp) => padding.top + h - ((temp - minTemp) / (maxTemp - minTemp)) * h;
  ctx.beginPath(); ctx.strokeStyle = '#FF6B3D'; ctx.lineWidth = 2;
  curve.forEach((point, i) => { const x = scaleX(point.hour), y = scaleY(point.temp); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.stroke();
  curve.forEach(point => { const x = scaleX(point.hour), y = scaleY(point.temp); ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fillStyle = '#E6EAF2'; ctx.fill(); });
  ctx.fillStyle = '#8A93A8'; ctx.font = '10px sans-serif';
  ctx.fillText(`${maxTemp}°C`, 5, padding.top + 5); ctx.fillText(`${minTemp}°C`, 5, height - padding.bottom);
  ctx.fillText('0h', padding.left, height - 5); ctx.fillText('12h', padding.left + w/2 - 10, height - 5); ctx.fillText('24h', padding.left + w - 20, height - 5);
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
    document.getElementById('btn-validation').addEventListener('click', () => document.getElementById('validation-modal').style.display = 'flex');
  } catch (err) {}
}

boot();