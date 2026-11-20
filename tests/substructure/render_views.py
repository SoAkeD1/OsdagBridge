"""
Offscreen renders of the bridge with the new substructure (no Qt window).

    python tests/substructure/render_views.py  out_dir

Uses the same colours / transparency as desktop/ui/cad_3d.py:
concrete opacity 0.35 (OCC transparency 0.65), rebar opaque steel colour.
Writes iso / front / side / substructure-only PNGs for the report.
"""
import os
import sys

from OCC.Display.OCCViewer import Viewer3d
from OCC.Core.Quantity import Quantity_Color, Quantity_TOC_RGB

sys.path.insert(0, os.path.dirname(__file__))
from smoke_test import sample_params  # noqa: E402

from osdagbridge.core.bridge_types.plate_girder.cad_generator import PlateGirderCADGenerator


def rgb(r, g, b):
    return Quantity_Color(r, g, b, Quantity_TOC_RGB)


SUPER = [("girders", rgb(0.53, 0.53, 0.39), None), ("cross_bracings", rgb(0.24, 0.24, 0.24), None),
         ("deck_slab", rgb(0.39, 0.39, 0.39), 0.5), ("crash_barriers", rgb(0.16, 0.16, 0.16), None),
         ("railings", rgb(0.16, 0.16, 0.16), None)]
CONCRETE = rgb(0.62, 0.66, 0.70)
SUB = [(k, CONCRETE, 0.65) for k in ("pier_caps", "pedestals", "piers", "pile_caps", "piles")]
REBAR = [("substructure_rebar", rgb(0.55, 0.27, 0.07), None)]


def render(md, layers, path, view="iso", size=(1600, 1000)):
    v = Viewer3d()
    v.Create()
    v.SetSize(*size)
    v.SetModeShaded()
    v.set_bg_gradient_color([255, 255, 255], [225, 230, 236])
    for key, color, transp in layers:
        shapes = md.get(key) or []
        if not isinstance(shapes, list):
            shapes = [shapes]
        for s in shapes:
            if transp is None:
                v.DisplayShape(s, color=color, update=False)
            else:
                v.DisplayShape(s, color=color, transparency=transp, update=False)
    {"iso": v.View_Iso, "front": v.View_Front, "right": v.View_Right, "top": v.View_Top}[view]()
    v.FitAll()
    v.ZoomFactor(0.95)
    v.Repaint()
    v.ExportToImage(path)
    print("wrote", path)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "renders"
    os.makedirs(out, exist_ok=True)
    gen = PlateGirderCADGenerator()
    md = gen.generate(sample_params())
    render(md, SUPER + SUB + REBAR, os.path.join(out, "bridge_iso.png"))
    render(md, SUPER + SUB + REBAR, os.path.join(out, "bridge_front.png"), "front")
    render(md, SUPER + SUB + REBAR, os.path.join(out, "bridge_side.png"), "right")
    render(md, SUB + REBAR, os.path.join(out, "substructure_iso.png"))
    render(md, REBAR, os.path.join(out, "rebar_only_iso.png"))


if __name__ == "__main__":
    main()
