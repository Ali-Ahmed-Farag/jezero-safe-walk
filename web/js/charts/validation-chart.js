// web/js/charts/validation-chart.js

export function drawValidationScatter(canvasId, sampleData) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !sampleData || sampleData.length === 0) return;
  
  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  
  canvas.width = parent.clientWidth * dpr;
  canvas.height = parent.clientHeight * dpr;
  
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  
  const width = parent.clientWidth;
  const height = parent.clientHeight;
  ctx.clearRect(0, 0, width, height);

  const padding = { top: 20, right: 20, bottom: 40, left: 40 };
  const w = width - padding.left - padding.right;
  const h = height - padding.top - padding.bottom;

  // Limits for X and Y (Pitch)
  let minVal = -25, maxVal = 25;
  
  const scaleX = (v) => padding.left + ((v - minVal) / (maxVal - minVal)) * w;
  const scaleY = (v) => padding.top + h - ((v - minVal) / (maxVal - minVal)) * h;

  // Draw Axes
  ctx.beginPath();
  ctx.strokeStyle = '#8A93A8';
  ctx.lineWidth = 1;
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, height - padding.bottom);
  ctx.lineTo(width - padding.right, height - padding.bottom);
  ctx.stroke();

  // Draw 1:1 Line (y = x)
  ctx.beginPath();
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
  ctx.setLineDash([5, 5]);
  ctx.moveTo(scaleX(minVal), scaleY(minVal));
  ctx.lineTo(scaleX(maxVal), scaleY(maxVal));
  ctx.stroke();
  ctx.setLineDash([]);

  // Draw Points (Sample max 3000)
  ctx.fillStyle = 'rgba(255, 107, 61, 0.4)'; // Mars accent transparent
  sampleData.forEach(pt => {
    if (pt.pitch_dem == null || pt.pitch_rover == null) return;
    const x = scaleX(pt.pitch_dem);
    const y = scaleY(pt.pitch_rover);
    ctx.beginPath();
    ctx.arc(x, y, 1.5, 0, Math.PI * 2);
    ctx.fill();
  });

  // Draw Labels
  ctx.fillStyle = '#8A93A8';
  ctx.font = '11px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('DEM Pitch (°)', width / 2, height - 5);
  
  ctx.save();
  ctx.translate(12, height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText('Rover Pitch (°)', 0, 0);
  ctx.restore();
  
  // Ticks
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  [-20, -10, 0, 10, 20].forEach(tick => {
    if (tick >= minVal && tick <= maxVal) {
      const y = scaleY(tick);
      ctx.fillText(`${tick}°`, padding.left - 5, y);
    }
  });
}