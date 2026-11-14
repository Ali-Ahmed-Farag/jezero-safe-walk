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
        const p = feature.properties;
        let popupContent = `<div style="max-width:280px;line-height:1.4;"><b>${p.name}</b>`;
        if (p.representative) popupContent += ` <span style="font-size:11px;background:#30363d;padding:1px 5px;border-radius:4px;">Representative${p.rover_sol ? ' (Sol ' + p.rover_sol + ')' : ''}</span>`;
        if (p.description) popupContent += `<div style="margin-top:4px;font-size:12px;">${p.description}</div>`;
        if (p.source) {
          const srcHtml = p.source_url ? `<a href="${p.source_url}" target="_blank" rel="noopener">${p.source}</a>` : p.source;
          popupContent += `<div style="margin-top:6px;padding-top:4px;border-top:1px solid #444;font-size:11px;color:#aaa;"><b>Source:</b> ${srcHtml}</div>`;
        }
        if (p.coordinate_source) popupContent += `<div style="margin-top:3px;font-size:11px;color:#aaa;"><b>Coords:</b> ${p.coordinate_source}</div>`;
        popupContent += `</div>`;
        layer.bindPopup(popupContent);
      }
    }
  }).addTo(map);
}