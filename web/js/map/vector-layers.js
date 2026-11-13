// web/js/map/vector-layers.js

export async function loadJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to load ${url}`);
  return await response.json();
}

// Convert standard GeoJSON [lon, lat] to L.CRS.Simple [row, col]
export function projectGeoJSON(geojson, meta) {
  const copy = JSON.parse(JSON.stringify(geojson));
  const { bounds, width, height } = meta;

  function projectCoords(coords) {
    if (typeof coords[0] === 'number') {
      const lon = coords[0];
      const lat = coords[1];
      // Guide Formula: 
      // x = (lon - lonMin) / (lonMax - lonMin)
      // y = (latMax - lat) / (latMax - latMin)
      const col = ((lon - bounds.lon_min) / (bounds.lon_max - bounds.lon_min)) * width;
      const row = ((bounds.lat_max - lat) / (bounds.lat_max - bounds.lat_min)) * height;
      return [row, col];
    } else {
      return coords.map(c => projectCoords(c));
    }
  }

  copy.features.forEach(f => {
    if (f.geometry && f.geometry.coordinates) {
      f.geometry.coordinates = projectCoords(f.geometry.coordinates);
    }
  });
  return copy;
}

export function addRoverTrack(map, geojsonData) {
  return L.geoJSON(geojsonData, {
    style: {
      color: "#FF6B3D", // Mars accent
      weight: 3,
      opacity: 0.9,
      dashArray: "5, 5"
    },
    pointToLayer: function (feature, latlng) {
      return L.circleMarker(latlng, {
        radius: 2,
        fillColor: "#FF6B3D",
        color: "#fff",
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8
      });
    }
  }).addTo(map);
}

export function addScienceTargets(map, geojsonData) {
  return L.geoJSON(geojsonData, {
    pointToLayer: function (feature, latlng) {
      return L.circleMarker(latlng, {
        radius: 6,
        fillColor: "#3FB950", // Safe green
        color: "#fff",
        weight: 2,
        opacity: 1,
        fillOpacity: 0.9
      });
    },
    onEachFeature: function (feature, layer) {
      if (feature.properties && feature.properties.name) {
        let popupContent = `<b>${feature.properties.name}</b>`;
        if (feature.properties.description) popupContent += `<br>${feature.properties.description}`;
        layer.bindPopup(popupContent);
      }
    }
  }).addTo(map);
}