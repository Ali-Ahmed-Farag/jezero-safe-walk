// web/js/grid-utils.js
// Single source of truth for coordinate transformations.

export function latLonToRowCol(lat, lon, meta) {
  const { bounds, width, height } = meta;
  // x = (lon - lonMin) / (lonMax - lonMin)
  const col = ((lon - bounds.lon_min) / (bounds.lon_max - bounds.lon_min)) * width;
  // y = (latMax - lat) / (latMax - latMin)
  const row = ((bounds.lat_max - lat) / (bounds.lat_max - bounds.lat_min)) * height;
  return { row, col };
}

export function rowColToLatLon(row, col, meta) {
  const { bounds, width, height } = meta;
  const lon = bounds.lon_min + (col / width) * (bounds.lon_max - bounds.lon_min);
  const lat = bounds.lat_max - (row / height) * (bounds.lat_max - bounds.lat_min);
  return { lat, lon };
}

// Since we use L.CRS.Simple with [[0,0], [height, width]]
export function rowColToLeaflet(row, col) {
  return [row, col];
}

export function leafletToRowCol(latlng) {
  return { row: Math.round(latlng.lat), col: Math.round(latlng.lng) };
}