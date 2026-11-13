// ===== MinHeap: Typed-array backed, reusable =====
class MinHeap {
    constructor(capacity) {
        this.vals  = new Int32Array(capacity);
        this.prios = new Float64Array(capacity);
        this.ties  = new Float64Array(capacity); // secondary key (h)
        this.size  = 0;
    }
    reset() { this.size = 0; }
    isEmpty() { return this.size === 0; }

    push(val, priority, tie) {
        if (this.size >= this.vals.length) this._grow();
        const i = this.size++;
        this.vals[i]  = val;
        this.prios[i] = priority;
        this.ties[i]  = tie;
        this._up(i);
    }
    pop() {
        if (this.size === 0) return -1;
        const top = this.vals[0];
        this.size--;
        if (this.size > 0) {
            this.vals[0]  = this.vals[this.size];
            this.prios[0] = this.prios[this.size];
            this.ties[0]  = this.ties[this.size];
            this._down(0);
        }
        return top;
    }
    _grow() {
        const n = this.vals.length * 2;
        const nv = new Int32Array(n);   nv.set(this.vals);   this.vals  = nv;
        const np = new Float64Array(n); np.set(this.prios);  this.prios = np;
        const nt = new Float64Array(n); nt.set(this.ties);   this.ties  = nt;
    }
    _lt(a, b) {
        const pa = this.prios[a], pb = this.prios[b];
        if (pa < pb) return true;
        if (pa > pb) return false;
        return this.ties[a] < this.ties[b];
    }
    _swap(a, b) {
        let t;
        t = this.vals[a];  this.vals[a]  = this.vals[b];  this.vals[b]  = t;
        t = this.prios[a]; this.prios[a] = this.prios[b]; this.prios[b] = t;
        t = this.ties[a];  this.ties[a]  = this.ties[b];  this.ties[b]  = t;
    }
    _up(i) {
        while (i > 0) {
            const p = (i - 1) >> 1;
            if (!this._lt(i, p)) break;
            this._swap(i, p);
            i = p;
        }
    }
    _down(i) {
        const n = this.size;
        while (true) {
            const l = 2 * i + 1, r = 2 * i + 2;
            let m = i;
            if (l < n && this._lt(l, m)) m = l;
            if (r < n && this._lt(r, m)) m = r;
            if (m === i) break;
            this._swap(i, m);
            i = m;
        }
    }
}

// ===== Module-level reusable buffers (avoid per-call allocs) =====
let _gScore   = null;
let _cameFrom = null;
let _closed   = null;
let _buffersSize = 0;
let _heap     = null;

function _ensureBuffers(n) {
    if (_buffersSize !== n) {
        _gScore   = new Float32Array(n);
        _cameFrom = new Int32Array(n);
        _closed   = new Uint8Array(n);
        _buffersSize = n;
    }
}

function _ensureHeap() {
    if (!_heap) _heap = new MinHeap(65536);
    else _heap.reset();
    return _heap;
}

// ===== Main interface (unchanged signature + optional limits) =====
function findRoute({
    slope, width, height, pixelM, start, end, profile, mode,
    slopeScale = 4,          // default kept for backward compat
    maxExpansions = 2000000, // cap on expanded nodes → reason:'search_limit'
}) {
    const [sr, sc] = start;
    const [er, ec] = end;
    const N = width * height;

    const startSlope = slope[sr * width + sc] / slopeScale;
    const endSlope   = slope[er * width + ec] / slopeScale;

    // same forbidden check as before
    if (startSlope > profile.forbidden) {
        return { found: false, reason: 'start_forbidden', slope: startSlope, path: [] };
    }
    if (endSlope > profile.forbidden) {
        return { found: false, reason: 'end_forbidden', slope: endSlope, path: [] };
    }

    _ensureBuffers(N);
    const gScore   = _gScore;
    const cameFrom = _cameFrom;
    const closed   = _closed;

    gScore.fill(Infinity);
    cameFrom.fill(-1);
    closed.fill(0);

    const openSet = _ensureHeap();

    const startIdx = sr * width + sc;
    const endIdx   = er * width + ec;

    gScore[startIdx] = 0;
    openSet.push(startIdx, 0, 0);

    const dirs = [
        [-1, 0, 1], [1, 0, 1], [0, -1, 1], [0, 1, 1],
        [-1, -1, 1.4142], [-1, 1, 1.4142], [1, -1, 1.4142], [1, 1, 1.4142]
    ];

    let expansions = 0;

    while (!openSet.isEmpty()) {
        const currentIdx = openSet.pop();

        // closed set: skip if already expanded
        if (closed[currentIdx]) continue;
        closed[currentIdx] = 1;

        if (currentIdx === endIdx) {
            const path = [];
            let curr = currentIdx;
            while (curr !== -1) {
                path.push([Math.floor(curr / width), curr % width]);
                curr = cameFrom[curr];
            }
            return { found: true, path: path.reverse() };
        }

        expansions++;
        if (expansions > maxExpansions) {
            return { found: false, reason: 'search_limit', path: [] };
        }

        const r = Math.floor(currentIdx / width);
        const c = currentIdx % width;
        const currentSlope = slope[currentIdx] / slopeScale;

        for (let i = 0; i < dirs.length; i++) {
            const nr = r + dirs[i][0];
            const nc = c + dirs[i][1];
            if (nr < 0 || nr >= height || nc < 0 || nc >= width) continue;

            const nIdx = nr * width + nc;
            if (closed[nIdx]) continue; // don't revisit closed nodes

            const neighborSlope = slope[nIdx] / slopeScale;
            const s_avg = (currentSlope + neighborSlope) / 2.0;

            if (s_avg > profile.forbidden) continue;

            const dist = dirs[i][2] * pixelM;

            // same cost equation as before
            const cost = mode === 'shortest'
                ? dist
                : dist * (1 + Math.pow(s_avg / profile.safe, 2));

            const tentativeG = gScore[currentIdx] + cost;

            if (tentativeG < gScore[nIdx]) {
                cameFrom[nIdx] = currentIdx;
                gScore[nIdx]   = tentativeG;
                const h = Math.hypot((nr - er) * pixelM, (nc - ec) * pixelM);
                // push with tie-breaker = h, so ties go to closer-to-goal nodes first
                openSet.push(nIdx, tentativeG + h, h);
            }
        }
    }

    return { found: false, reason: 'no_path', path: [] };
}

if (typeof module !== 'undefined') module.exports = { findRoute };