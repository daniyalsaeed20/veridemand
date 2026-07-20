/** Canvas overlay helpers for extraction review. */

function normToCanvas(poly, width, height) {
  if (!poly || !poly.length) return [];
  return poly.map(([x, y]) => [x * width, y * height]);
}

function canvasToNorm(x0, y0, x1, y1, width, height) {
  const nx0 = Math.min(x0, x1) / width;
  const ny0 = Math.min(y0, y1) / height;
  const nx1 = Math.max(x0, x1) / width;
  const ny1 = Math.max(y0, y1) / height;
  return [
    [clamp01(nx0), clamp01(ny0)],
    [clamp01(nx1), clamp01(ny0)],
    [clamp01(nx1), clamp01(ny1)],
    [clamp01(nx0), clamp01(ny1)],
  ];
}

function clamp01(v) {
  return Math.max(0, Math.min(1, v));
}

function drawPolygon(ctx, points, style) {
  if (!points.length) return;
  ctx.beginPath();
  ctx.moveTo(points[0][0], points[0][1]);
  for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1]);
  ctx.closePath();
  ctx.strokeStyle = style.stroke || "#0af";
  ctx.lineWidth = style.width || 1.5;
  ctx.globalAlpha = style.alpha ?? 0.9;
  if (style.fill) {
    ctx.fillStyle = style.fill;
    ctx.fill();
  }
  ctx.stroke();
  ctx.globalAlpha = 1;
}

function hitTest(items, x, y, width, height) {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i];
    const poly = it.polygon;
    if (!poly || poly.length < 3) continue;
    const pts = normToCanvas(poly, width, height);
    if (pointInPoly(x, y, pts)) return it;
  }
  return null;
}

function pointInPoly(x, y, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const xi = pts[i][0],
      yi = pts[i][1];
    const xj = pts[j][0],
      yj = pts[j][1];
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-9) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

window.ReviewOverlay = {
  normToCanvas,
  canvasToNorm,
  drawPolygon,
  hitTest,
};
