import { findRoute } from '../../data/astar.js?v=2';
import { pathMetrics } from '../../data/metrics.js';

let routeLayer = null;
let startMarker = null;
let endMarker = null;
let shortestLayer = null;

export function clearRoute(map) {
  if (routeLayer) map.removeLayer(routeLayer);
  if (shortestLayer) map.removeLayer(shortestLayer);
  if (startMarker) map.removeLayer(startMarker);
  if (endMarker) map.removeLayer(endMarker);
  routeLayer = null;
  shortestLayer = null;
  startMarker = null;
  endMarker = null;
}

export function handleMapClick(map, e, state, ui, updateBriefCallback) {
  const row = Math.round(e.latlng.lat);
  const col = Math.round(e.latlng.lng);

  if (row < 0 || row >= state.meta.height || col < 0 || col >= state.meta.width) return;

  if (!state.start) {
    state.start = [row, col];
    startMarker = L.circleMarker([row, col], { radius: 7, color: '#fff', fillColor: '#3FB950', fillOpacity: 1, weight: 2 }).addTo(map);
    ui.hint.textContent = "Click to set Target";
  } else if (!state.end) {
    state.end = [row, col];
    endMarker = L.circleMarker([row, col], { radius: 7, color: '#fff', fillColor: '#F85149', fillOpacity: 1, weight: 2 }).addTo(map);
    calculateAndDrawRoute(map, state, ui, updateBriefCallback, "safest");
  } else {
    clearRoute(map);
    state.start = null;
    state.end = null;
    ui.hint.textContent = "Click to set Start";
    if (updateBriefCallback) updateBriefCallback(null, null);
  }
}

export function calculateAndDrawRoute(map, state, ui, updateBriefCallback, mode = "safest") {
  ui.hint.textContent = "Calculating route...";
  try {
    const result = findRoute({
      slope: state.slope,
      width: state.meta.width,
      height: state.meta.height,
      pixelM: state.meta.pixel_size_m.x,
      start: state.start,
      end: state.end,
      profile: state.profile,
      mode: mode
    });

    if (!result || !result.found || !result.path || result.path.length === 0) {
      console.warn("Routing failed. Reason:", result ? result.reason : "Unknown");
      if (mode === "safest") ui.hint.textContent = "No safe route found!";
      return null;
    }

    const latlngs = result.path.map(pt => [pt[0], pt[1]]);
    
    if (mode === "safest") {
      if (routeLayer) map.removeLayer(routeLayer);
      routeLayer = L.polyline(latlngs, { color: '#3FB950', weight: 4 }).addTo(map);
      // شلنا الـ maxZoom السالب عشان منجبرش الخريطة إنها تصغر
      map.fitBounds(routeLayer.getBounds(), { padding: [50, 50] });
      ui.hint.textContent = "Safest route found!";
    } else if (mode === "shortest") {
      if (shortestLayer) map.removeLayer(shortestLayer);
      shortestLayer = L.polyline(latlngs, { color: '#8A93A8', weight: 3, dashArray: '5, 5' }).addTo(map);
    }

    const metrics = pathMetrics({
      path: result.path, slope: state.slope, elev: state.elev,
      width: state.meta.width, pixelM: state.meta.pixel_size_m.x, profile: state.profile
    });

    return { result, metrics };

  } catch (err) {
    console.error("Routing error:", err);
    ui.hint.textContent = "Error calculating route.";
    return null;
  }
}