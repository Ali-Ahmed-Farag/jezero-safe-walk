// web/js/charts/elevation-profile.js

export function drawProfile(canvasId, arrays) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;

  // ضبط حجم الـ Canvas ليكون مطابق لحجم الأب (الـ Panel) بالظبط
  canvas.width = parent.clientWidth * dpr;
  canvas.height = parent.clientHeight * dpr;

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const width = parent.clientWidth;
  const height = parent.clientHeight;

  ctx.clearRect(0, 0, width, height);

  if (!arrays || arrays.cum_dist.length === 0) {
    ctx.fillStyle = '#5E739A';
    ctx.font = '12px sans-serif';
    ctx.fillText("No route data", 10, 20);
    return;
  }

  const { cum_dist, elev, slope } = arrays;
  const padding = { top: 30, right: 50, bottom: 30, left: 60 };
  const w = width - padding.left - padding.right;
  const h = height - padding.top - padding.bottom;

  let minElev = Infinity, maxElev = -Infinity, maxSlope = 0;
  let maxDist = cum_dist[cum_dist.length - 1];

  for (let i = 0; i < elev.length; i++) {
    if (elev[i] !== null) {
      if (elev[i] < minElev) minElev = elev[i];
      if (elev[i] > maxElev) maxElev = elev[i];
    }
    if (slope[i] > maxSlope) maxSlope = slope[i];
  }

  if (minElev === Infinity) { minElev = 0; maxElev = 1; }
  if (maxElev === minElev) maxElev = minElev + 1;
  if (maxSlope === 0) maxSlope = 1;

  const scaleX = (d) => padding.left + (d / maxDist) * w;
  const scaleYElev = (e) => padding.top + h - ((e - minElev) / (maxElev - minElev)) * h;
  const scaleYSlope = (s) => padding.top + h - (s / maxSlope) * h;

  // رسم خط الارتفاع (أبيض)
  ctx.beginPath();
  ctx.strokeStyle = '#27B9E8';
  ctx.lineWidth = 2;
  let drawing = false;

  for (let i = 0; i < cum_dist.length; i++) {
    if (elev[i] === null) { drawing = false; continue; }
    const x = scaleX(cum_dist[i]);
    const y = scaleYElev(elev[i]);
    if (!drawing) { ctx.moveTo(x, y); drawing = true; }
    else { ctx.lineTo(x, y); }
  }
  ctx.stroke();

  // رسم خط الميل (برتقالي شفاف)
  ctx.beginPath();
  ctx.strokeStyle = 'rgba(255, 107, 61, 0.7)';
  ctx.lineWidth = 1.5;
  drawing = false;

  for (let i = 0; i < cum_dist.length; i++) {
    if (slope[i] === null) { drawing = false; continue; }
    const x = scaleX(cum_dist[i]);
    const y = scaleYSlope(slope[i]);
    if (!drawing) { ctx.moveTo(x, y); drawing = true; }
    else { ctx.lineTo(x, y); }
  }
  ctx.stroke();

  // كتابة الأرقام (Legend)
  ctx.fillStyle = '#27B9E8';
  ctx.font = '11px sans-serif';
  ctx.fillText(`Elev: ${minElev.toFixed(0)}m to ${maxElev.toFixed(0)}m`, padding.left, 15);

  ctx.fillStyle = '#FF6B3D';
  ctx.fillText(`Slope (max: ${maxSlope.toFixed(1)}°)`, padding.left + 150, 15);

  ctx.fillStyle = '#5E739A';
  ctx.fillText(`${maxDist.toFixed(2)} km`, width - padding.right - 40, height - 5);
}