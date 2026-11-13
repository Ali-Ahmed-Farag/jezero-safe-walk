import { loadGridMeta, loadElevation, loadSlope } from './data-loader.js';
import { createSlopeCanvas } from './map/raster-layers.js';
import { loadJSON, projectGeoJSON, addRoverTrack, addScienceTargets } from './map/vector-layers.js';
import { handleMapClick, calculateAndDrawRoute } from './routing/route-controller.js';
import { drawProfile } from './charts/elevation-profile.js';

const state = {
  meta: null, slope: null, elev: null, start: null, end: null,
  profile: { safe: 10, hard: 16, forbidden: 16 },
  thermal: null
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

async function boot() {
  try {
    ui.hint.textContent = "Loading data...";
    state.meta = await loadGridMeta();
    const expectedCells = state.meta.width * state.meta.height;

    state.elev = await loadElevation('./data/elev_dm_i16.bin', expectedCells);
    state.slope = await loadSlope('./data/slope_u8.bin', expectedCells);

    const mapBounds = [[0, 0], [state.meta.height, state.meta.width]];
    
    // التعديل هنا: بنستخدم setView بـ Zoom 1 عشان نضمن إنها مالية الشاشة
    map.setView([state.meta.height / 2, state.meta.width / 2], 1);

    updateSlopeOverlay(mapBounds);

    const roverGeoJSON = await loadJSON('./data/rover_track.geojson');
    roverLayer = addRoverTrack(map, projectGeoJSON(roverGeoJSON, state.meta));

    const targetsGeoJSON = await loadJSON('./data/science_targets.geojson');
    targetsLayer = addScienceTargets(map, projectGeoJSON(targetsGeoJSON, state.meta));

    setupLayerControls();
    await setupPresets();
    await setupValidation();
    await setupThermal();

    ui.hint.textContent = "Click to set Start";
  } catch (error) {
    console.error("Boot failed:", error);
    ui.hint.textContent = "Error loading data.";
  }
}

window.addEventListener('resize', () => {
  setTimeout(() => {
    map.invalidateSize();
    if (currentMetrics && currentMetrics.arrays) drawProfile('profile-canvas', currentMetrics.arrays);
    if (state.thermal && document.getElementById('thermal-modal').style.display === 'flex') {
      drawThermalChart(state.thermal);
    }
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
  } catch (err) {
    console.warn("Thermal data not loaded", err);
  }
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
  
  const width = parent.clientWidth;
  const height = parent.clientHeight;
  ctx.clearRect(0, 0, width, height);

  const curve = data.curve;
  const padding = { top: 20, right: 20, bottom: 30, left: 40 };
  const w = width - padding.left - padding.right;
  const h = height - padding.top - padding.bottom;

  let minTemp = Math.min(...curve.map(c => c.temp));
  let maxTemp = Math.max(...curve.map(c => c.temp));

  const scaleX = (hour) => padding.left + (hour / 24) * w;
  const scaleY = (temp) => padding.top + h - ((temp - minTemp) / (maxTemp - minTemp)) * h;

  ctx.beginPath();
  ctx.strokeStyle = '#FF6B3D';
  ctx.lineWidth = 2;

  curve.forEach((point, i) => {
    const x = scaleX(point.hour);
    const y = scaleY(point.temp);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  curve.forEach(point => {
    const x = scaleX(point.hour);
    const y = scaleY(point.temp);
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fillStyle = '#E6EAF2';
    ctx.fill();
  });

  ctx.fillStyle = '#8A93A8';
  ctx.font = '10px sans-serif';
  ctx.fillText(`${maxTemp}°C`, 5, padding.top + 5);
  ctx.fillText(`${minTemp}°C`, 5, height - padding.bottom);
  
  ctx.fillText('0h', padding.left, height - 5);
  ctx.fillText('12h', padding.left + w/2 - 10, height - 5);
  ctx.fillText('24h', padding.left + w - 20, height - 5);
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

    document.getElementById('btn-validation').addEventListener('click', () => {
      document.getElementById('validation-modal').style.display = 'flex';
    });
  } catch (err) {
    console.warn("Validation data not loaded", err);
  }
}

async function setupPresets() {
  try {
    const presetsData = await loadJSON('./data/presets.json');
    const presetsMenu = document.getElementById('presets-dropdown');
    
    presetsData.forEach(p => {
      const btn = document.createElement('button');
      btn.textContent = p.title || p.id;
      btn.addEventListener('click', () => {
        presetsMenu.style.display = 'none';
        
        const startCol = ((p.start[1] - state.meta.bounds.lon_min) / (state.meta.bounds.lon_max - state.meta.bounds.lon_min)) * state.meta.width;
        const startRow = ((state.meta.bounds.lat_max - p.start[0]) / (state.meta.bounds.lat_max - state.meta.bounds.lat_min)) * state.meta.height;
        const endCol = ((p.end[1] - state.meta.bounds.lon_min) / (state.meta.bounds.lon_max - state.meta.bounds.lon_min)) * state.meta.width;
        const endRow = ((state.meta.bounds.lat_max - p.end[0]) / (state.meta.bounds.lat_max - state.meta.bounds.lat_min)) * state.meta.height;

        map.eachLayer(layer => {
          if (layer instanceof L.Polyline) map.removeLayer(layer);
          if (layer instanceof L.CircleMarker) map.removeLayer(layer);
        });

        state.start = [Math.round(startRow), Math.round(startCol)];
        state.end = [Math.round(endRow), Math.round(endCol)];

        L.circleMarker(state.start, { radius: 7, color: '#fff', fillColor: '#3FB950', fillOpacity: 1, weight: 2 }).addTo(map);
        L.circleMarker(state.end, { radius: 7, color: '#fff', fillColor: '#F85149', fillOpacity: 1, weight: 2 }).addTo(map);

        const res = calculateAndDrawRoute(map, state, ui, null, "safest");
        if (res) updateMissionBrief(res.result, res.metrics);
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

  const safestRes = calculateAndDrawRoute(map, state, ui, null, "safest");
  const shortestRes = calculateAndDrawRoute(map, state, ui, null, "shortest");

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
  handleMapClick(map, e, state, ui, updateMissionBrief);
});

const modals = [
  document.getElementById('about-modal'),
  document.getElementById('sources-modal'), 
  document.getElementById('validation-modal'), 
  document.getElementById('compare-modal'),
  document.getElementById('thermal-modal')
];

document.getElementById('btn-about').addEventListener('click', () => modals[0].style.display = 'flex');
document.getElementById('btn-sources').addEventListener('click', () => modals[1].style.display = 'flex');

document.getElementById('btn-print').addEventListener('click', () => {
  window.print();
});

document.querySelectorAll('.close-modal-btn').forEach(btn => {
  btn.addEventListener('click', () => modals.forEach(m => m.style.display = 'none'));
});
window.addEventListener('click', (e) => {
  modals.forEach(m => { if (e.target === m) m.style.display = 'none'; });
});

boot();