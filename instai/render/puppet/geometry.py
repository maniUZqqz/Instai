"""2D affine maths and easing for the puppet renderer. A matrix is (a, b, c, d, e, f) as in SVG: x' = a*x + c*y + e, y' = b*x + d*y + f.
Positive rotation turns clockwise on screen (the y axis points down)."""
from __future__ import annotations

import math

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mul(m: Matrix, n: Matrix) -> Matrix:
    """m after n (apply n first)."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2, a1 * c2 + c1 * d2, b1 * c2 + d1 * d2, a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def translate(tx: float, ty: float) -> Matrix:
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def scale(sx: float, sy: float | None = None) -> Matrix:
    return (sx, 0.0, 0.0, sx if sy is None else sy, 0.0, 0.0)


def rotate(deg: float) -> Matrix:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (c, s, -s, c, 0.0, 0.0)


def apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def invert(m: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    det = a * d - b * c
    if abs(det) < 1e-12:
        raise ValueError("singular matrix")
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return (ia, ib, ic, id_, -(ia * e + ic * f), -(ib * e + id_ * f))


def pil_inverse(m: Matrix) -> tuple[float, float, float, float, float, float]:
    """Coefficients for PIL Image.transform(AFFINE): maps each OUTPUT pixel back to the input pixel (the inverse of m)."""
    ia, ib, ic, id_, ie, if_ = invert(m)
    return (ia, ic, ie, ib, id_, if_)


def bbox(m: Matrix, w: float, h: float) -> tuple[float, float, float, float]:
    pts = [apply(m, x, y) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# ------------------------------------------------------------------ easing

def _smooth(u: float) -> float:
    return u * u * (3 - 2 * u)


EASINGS = {
    "linear": lambda u: u,
    "in": lambda u: u * u,
    "out": lambda u: 1 - (1 - u) * (1 - u),
    "inout": _smooth,
    "hold": lambda u: 0.0,                                  # keep the previous value until the next key
    "back": lambda u: 1 + 2.70158 * (u - 1) ** 3 + 1.70158 * (u - 1) ** 2,   # overshoot
}


def ease(name: str, u: float) -> float:
    return EASINGS.get(name, EASINGS["linear"])(max(0.0, min(1.0, u)))


def track_value(keys: list, t: float, default: float = 0.0) -> float:
    """keys: [(t, value)] or [(t, value, easing)] sorted by t; the easing of key i shapes the segment i-1 -> i. Clamped at both ends."""
    if not keys:
        return default
    if t <= keys[0][0]:
        return float(keys[0][1])
    for i in range(1, len(keys)):
        t1 = keys[i][0]
        if t <= t1:
            t0, v0 = keys[i - 1][0], float(keys[i - 1][1])
            v1 = float(keys[i][1])
            name = keys[i][2] if len(keys[i]) > 2 else "linear"
            u = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            return v0 + (v1 - v0) * ease(name, u)
    return float(keys[-1][1])
