function pathMetrics({path, slope, elev, width, pixelM, profile, speedKmh = 2}) {
    if (!path || path.length === 0) return null;
    
    let length_m = 0;
    let max_slope = 0;
    let sum_slope = 0;
    let safe_len = 0;
    let hard_len = 0;
    let forbidden_len = 0;
    
    let cum_dist = [0];
    let elev_arr = [];
    let slope_arr = [];
    
    for (let i = 0; i < path.length; i++) {
        const [r, c] = path[i];
        const idx = r * width + c;
        const s = slope[idx] / 4.0;
        const e = (elev && elev[idx] !== -32768) ? elev[idx] / 10.0 : null;
        
        slope_arr.push(s);
        elev_arr.push(e);
        sum_slope += s;
        if (s > max_slope) max_slope = s;
        
        if (i > 0) {
            const [pr, pc] = path[i - 1];
            const d = Math.hypot((c - pc) * pixelM, (r - pr) * pixelM);
            length_m += d;
            cum_dist.push(length_m);
            
            if (s <= profile.safe) safe_len += d;
            else if (s <= profile.hard) hard_len += d;
            else forbidden_len += d;
        }
    }
    
    const length_km = length_m / 1000;
    const mean_slope = sum_slope / path.length;
    const time_h = length_km / speedKmh;
    
    let smooth_elev = [];
    for (let i = 0; i < elev_arr.length; i++) {
        if (i === 0) smooth_elev.push((elev_arr[0] + elev_arr[1]) / 2);
        else if (i === elev_arr.length - 1) smooth_elev.push((elev_arr[i-1] + elev_arr[i]) / 2);
        else smooth_elev.push((elev_arr[i-1] + elev_arr[i] + elev_arr[i+1]) / 3);
    }
    
    let ascent = 0, descent = 0;
    for (let i = 1; i < smooth_elev.length; i++) {
        let diff = smooth_elev[i] - smooth_elev[i-1];
        if (diff > 0) ascent += diff;
        else descent -= diff;
    }
    
    let pct_safe = (safe_len / length_m) * 100;
    let pct_hard = (hard_len / length_m) * 100;
    let pct_forbidden = (forbidden_len / length_m) * 100;
    
    let risk = "medium";
    if (pct_forbidden > 0) risk = "high";
    else if (pct_safe >= 90 && max_slope <= 14) risk = "low";
    else if (pct_hard > 30 || max_slope > profile.hard) risk = "high";
    
    return {
        length_km: Number(length_km.toFixed(2)),
        mean_slope: Number(mean_slope.toFixed(2)),
        max_slope: Number(max_slope.toFixed(2)),
        pct_safe: Number(pct_safe.toFixed(2)),
        pct_hard: Number(pct_hard.toFixed(2)),
        ascent_m: Number(ascent.toFixed(1)),
        descent_m: Number(descent.toFixed(1)),
        time_h: Number(time_h.toFixed(2)),
        risk_level: risk,
        arrays: {
            cum_dist: cum_dist.map(d => Number((d/1000).toFixed(3))),
            elev: smooth_elev.map(e => Number(e.toFixed(1))),
            slope: slope_arr.map(s => Number(s.toFixed(1)))
        }
    };
}
export { pathMetrics };
