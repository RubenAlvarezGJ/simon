import type { Point, Polygon } from './types';

export function distance(a: Point, b: Point): number {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return Math.hypot(dx, dy);
}

export function nearestVertex(poly: Polygon, p: Point, radius: number): number {
  let best = -1;
  let bestDist = radius;
  for (let i = 0; i < poly.length; i++) {
    const d = distance(poly[i], p);
    if (d <= bestDist) {
      best = i;
      bestDist = d;
    }
  }
  return best;
}

export function pointInPolygon(poly: Polygon, p: Point): boolean {
  // Ray-casting algorithm
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    const intersects =
      yi > p[1] !== yj > p[1] &&
      p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi + 1e-9) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

export function findContainingZone(zones: Record<string, Polygon>, p: Point): string | null {
  for (const [name, poly] of Object.entries(zones)) {
    if (poly.length >= 3 && pointInPolygon(poly, p)) return name;
  }
  return null;
}
