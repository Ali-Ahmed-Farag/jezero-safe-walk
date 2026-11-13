// web/js/map/raster-layers.js

export function createSlopeCanvas(slopeData, width, height, profile) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  
  const imageData = ctx.createImageData(width, height);
  const data = imageData.data;

  for (let i = 0; i < slopeData.length; i++) {
    const raw = slopeData[i];
    const deg = raw / 4; // slope_scale is 4
    const idx = i * 4;

    if (raw === 255) {
      // NoData or Border
      data[idx + 3] = 0; // transparent
      continue;
    }

    let r = 0, g = 0, b = 0, a = 180; // default alpha 180 (out of 255)

    if (deg < profile.safe) {
      // Safe (Green)
      r = 63; g = 185; b = 80; 
    } else if (deg < profile.hard) {
      // Hard (Yellow)
      r = 227; g = 179; b = 65;
    } else {
      // Forbidden (Red)
      r = 248; g = 81; b = 73;
    }

    data[idx] = r;
    data[idx + 1] = g;
    data[idx + 2] = b;
    data[idx + 3] = a;
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}