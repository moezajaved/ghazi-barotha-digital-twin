"""Pure-numpy mesh primitives for the 3D plant scene (no Streamlit or Plotly imports; unit-testable).

A mesh is a dict {"x","y","z","i","j","k"}: vertex coordinates (metres) and triangle indices, ready for plotly Mesh3d.
"""
from __future__ import annotations

import numpy as np

Mesh = dict


def box(x0, x1, y0, y1, z0, z1) -> Mesh:
    """Axis-aligned box from two opposite corners (8 vertices, 12 triangles)."""
    xs, ys, zs = (x0, x1), (y0, y1), (z0, z1)
    v = np.array([[xs[a], ys[b], zs[c]] for c in (0, 1) for b in (0, 1) for a in (0, 1)], float)   # index = a + 2b + 4c
    t = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    t = np.array(t)
    return {"x": v[:, 0], "y": v[:, 1], "z": v[:, 2], "i": t[:, 0], "j": t[:, 1], "k": t[:, 2]}


def cylinder(p0, p1, r: float, n: int = 16, caps: bool = True) -> Mesh:
    """Closed cylinder of radius r along the axis p0 -> p1 (any direction)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    ax = p1 - p0
    length = np.linalg.norm(ax)
    if length == 0 or r <= 0:
        raise ValueError("cylinder needs distinct end points and r > 0")
    ax = ax / length
    helper = np.array([0.0, 0.0, 1.0]) if abs(ax[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(ax, helper)
    u /= np.linalg.norm(u)
    w = np.cross(ax, u)
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.outer(np.cos(th), u) + np.outer(np.sin(th), w)           # (n, 3)
    v = np.vstack([p0 + r * ring, p1 + r * ring])
    tri = []
    for a in range(n):
        b = (a + 1) % n
        tri += [(a, b, n + b), (a, n + b, n + a)]
    if caps:
        v = np.vstack([v, p0, p1])
        c0, c1 = 2 * n, 2 * n + 1
        for a in range(n):
            b = (a + 1) % n
            tri += [(c0, b, a), (c1, n + a, n + b)]
    tri = np.array(tri)
    return {"x": v[:, 0], "y": v[:, 1], "z": v[:, 2], "i": tri[:, 0], "j": tri[:, 1], "k": tri[:, 2]}


def merge(meshes: list[Mesh]) -> Mesh:
    """Concatenate meshes into one (indices offset), so many parts become a single Mesh3d trace."""
    if not meshes:
        return {k: np.array([]) for k in "xyzijk"}
    out = {k: [] for k in "xyzijk"}
    off = 0
    for m in meshes:
        for k in "xyz":
            out[k].append(np.asarray(m[k], float))
        for k in "ijk":
            out[k].append(np.asarray(m[k], int) + off)
        off += len(m["x"])
    return {k: np.concatenate(v) for k, v in out.items()}


def validate(m: Mesh) -> None:
    """Raise ValueError if the mesh is malformed (index out of range, NaN, ragged arrays)."""
    n = len(m["x"])
    if not (len(m["y"]) == len(m["z"]) == n):
        raise ValueError("vertex arrays differ in length")
    if not all(np.isfinite(np.asarray(m[k], float)).all() for k in "xyz"):
        raise ValueError("non-finite vertex coordinate")
    idx = np.concatenate([np.asarray(m[k], int) for k in "ijk"]) if len(m["i"]) else np.array([0])
    if idx.min() < 0 or idx.max() >= n:
        raise ValueError("triangle index out of range")


def bounds(m: Mesh):
    return tuple((float(np.min(m[k])), float(np.max(m[k]))) for k in "xyz")
