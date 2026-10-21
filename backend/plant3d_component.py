"""Thin Streamlit wrapper around the local 3D component in frontend/plant3d (no build step, works offline).

plotly.min.js ships inside the installed `plotly` package; it is copied next to index.html on first use (not committed to Git).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import plotly

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "plant3d"
_component = None


def ensure_plotly_js() -> Path:
    src = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    dst = FRONTEND / "plotly.min.js"
    if not src.exists():
        raise FileNotFoundError(f"plotly.min.js not found in the installed plotly package ({src}); reinstall plotly")
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        shutil.copyfile(src, dst)
    return dst


def plant3d_view(payload: dict, camera: dict, nonce: int, summary: dict, height: int = 640, key: str = "plant3d"):
    """Render (or update in place) the 3D view. `nonce` changes only when a camera preset is requested."""
    global _component
    if _component is None:
        import streamlit.components.v1 as components
        ensure_plotly_js()
        _component = components.declare_component("gbhp_plant3d", path=str(FRONTEND))
    return _component(fig=payload, camera=camera, camera_nonce=nonce, summary=summary, height=height, key=key, default=None)
