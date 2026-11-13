// Jezero Safe Walk - A* Pathfinding Module (Browser & Node compatible)
// Uses Binary Min-Heap and Typed Arrays for <1s execution on ~1M pixels

class MinHeap {
  constructor(capacity) {
    this.nodes = new Int32Array(capacity);
    this.scores = new Float64Array(capacity);
    this.size = 0;
  }

  push(node, score) {
    let i = this.size++;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (this.scores[parent] <= score) break;
      this.nodes[i] = this.nodes[parent];
      this.scores[i] = this.scores[parent];
      i = parent;
    }
    this.nodes[i] = node;
    this.scores[i] = score;
  }

  pop() {
    if (this.size === 0) return -1;
    const topNode = this.nodes[0];
    this.size--;
    if (this.size > 0) {
      const lastNode = this.nodes[this.size];
      const lastScore = this.scores[this.size];
      let i = 0;
      const half = this.size >> 1;
      while (i < half) {
        let child = (i << 1) + 1;
        const right = child + 1;
        if (right < this.size && this.scores[right] < this.scores[child]) {
          child = right;
        }
        if (lastScore <= this.scores[child]) break;
        this.nodes[i] = this.nodes[child];
        this.scores[i] = this.scores[child];
        i = child;
      }
      this.nodes[i] = lastNode;
      this.scores[i] = lastScore;
    }
    return topNode;
  }
}

/**
 * Find safest or shortest route on terrain slope grid.
 * @param {Object} params
 * @param {Uint8Array} params.slope - Row-major array of slope * slopeScale
 * @param {number} params.width - Grid width in pixels
 * @param {number} params.height - Grid height in pixels
 * @param {number|{x:number, y:number}} params.pixelM - Pixel size in meters
 * @param {[number, number]} params.start - [row, col]
 * @param {[number, number]} params.end - [row, col]
 * @param {{safe: number, hard?: number, forbidden: number}} [params.profile] - Thresholds in degrees
 * @param {"safest"|"shortest"} [params.mode] - Routing mode
 * @param {number} [params.slopeScale=4] - Scale factor in slope_u8.bin
 * @returns {{path: Array<[number, number]>, found: boolean}}
 */
function findRoute({
  slope,
  width,
  height,
  pixelM,
  start,
  end,
  profile = { safe: 10, hard: 16, forbidden: 16 },
  mode = "safest",
  slopeScale = 4,
}) {
  const [startR, startC] = start;
  const [endR, endC] = end;

  if (
    startR < 0 || startR >= height || startC < 0 || startC >= width ||
    endR < 0 || endR >= height || endC < 0 || endC >= width
  ) {
    return { path: [], found: false };
  }

  const pxX = typeof pixelM === "number" ? pixelM : pixelM.x;
  const pxY = typeof pixelM === "number" ? pixelM : pixelM.y;
  const pxDiag = Math.hypot(pxX, pxY);

  const total = width * height;
  const startIdx = startR * width + startC;
  const endIdx = endR * width + endC;

  const invScale = 1.0 / slopeScale;
  const safeDeg = profile.safe;
  const forbiddenDeg = profile.forbidden;

  // Check if start or end itself exceeds forbidden slope
  if (slope[startIdx] * invScale > forbiddenDeg || slope[endIdx] * invScale > forbiddenDeg) {
    return { path: [], found: false };
  }

  if (startIdx === endIdx) {
    return { path: [[startR, startC]], found: true };
  }

  const gScore = new Float64Array(total);
  gScore.fill(Infinity);
  const cameFrom = new Int32Array(total);
  cameFrom.fill(-1);
  const closed = new Uint8Array(total);

  const openHeap = new MinHeap(total);

  const hStart = Math.hypot((endC - startC) * pxX, (endR - startR) * pxY);
  gScore[startIdx] = 0;
  openHeap.push(startIdx, hStart);

  // 8-connected neighbors: [dRow, dCol, stepMeters]
  const dirs = [
    [-1,  0, pxY],
    [ 1,  0, pxY],
    [ 0, -1, pxX],
    [ 0,  1, pxX],
    [-1, -1, pxDiag],
    [-1,  1, pxDiag],
    [ 1, -1, pxDiag],
    [ 1,  1, pxDiag],
  ];

  const isSafest = mode !== "shortest";

  while (openHeap.size > 0) {
    const currIdx = openHeap.pop();
    if (currIdx === endIdx) {
      const path = [];
      let trace = endIdx;
      while (trace !== -1) {
        const r = Math.floor(trace / width);
        const c = trace % width;
        path.push([r, c]);
        trace = cameFrom[trace];
      }
      path.reverse();
      return { path, found: true };
    }

    if (closed[currIdx]) continue;
    closed[currIdx] = 1;

    const currR = Math.floor(currIdx / width);
    const currC = currIdx % width;
    const currSlopeDeg = slope[currIdx] * invScale;
    const currG = gScore[currIdx];

    for (let i = 0; i < 8; i++) {
      const nR = currR + dirs[i][0];
      const nC = currC + dirs[i][1];
      if (nR < 0 || nR >= height || nC < 0 || nC >= width) continue;

      const nIdx = nR * width + nC;
      if (closed[nIdx]) continue;

      const nSlopeDeg = slope[nIdx] * invScale;
      if (nSlopeDeg > forbiddenDeg) continue;

      const avgSlope = 0.5 * (currSlopeDeg + nSlopeDeg);
      if (avgSlope > forbiddenDeg) continue;

      const d = dirs[i][2];
      let stepCost = d;
      if (isSafest) {
        const ratio = avgSlope / safeDeg;
        stepCost = d * (1.0 + ratio * ratio);
      }

      const tentativeG = currG + stepCost;
      if (tentativeG < gScore[nIdx]) {
        cameFrom[nIdx] = currIdx;
        gScore[nIdx] = tentativeG;
        const h = Math.hypot((endC - nC) * pxX, (endR - nR) * pxY);
        openHeap.push(nIdx, tentativeG + h);
      }
    }
  }

  return { path: [], found: false };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { findRoute };
}
if (typeof window !== "undefined") {
  window.findRoute = findRoute;
}