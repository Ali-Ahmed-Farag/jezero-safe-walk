// web/js/data-loader.js

export async function loadGridMeta() {
  const response = await fetch('./data/grid_meta.json');
  if (!response.ok) {
    throw new Error(`Failed to load grid_meta.json: ${response.status}`);
  }
  return await response.json();
}

export async function loadElevation(url, expectedCellCount) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load elevation data: ${response.status}`);
  }

  const buffer = await response.arrayBuffer();
  if (buffer.byteLength !== expectedCellCount * 2) {
    throw new Error(`Elevation binary size mismatch. Expected ${expectedCellCount * 2} bytes, got ${buffer.byteLength}.`);
  }

  // Use DataView to ensure explicit Little-Endian decoding
  const view = new DataView(buffer);
  const values = new Int16Array(expectedCellCount);

  for (let i = 0; i < expectedCellCount; i++) {
    values[i] = view.getInt16(i * 2, true); // true for Little-Endian
  }

  return values;
}

export async function loadSlope(url, expectedCellCount) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load slope data: ${response.status}`);
  }

  const buffer = await response.arrayBuffer();
  if (buffer.byteLength !== expectedCellCount) {
    throw new Error(`Slope binary size mismatch. Expected ${expectedCellCount} bytes, got ${buffer.byteLength}.`);
  }

  return new Uint8Array(buffer);
}