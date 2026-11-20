"""
Shared helpers for the parametric substructure builders.

Reinforcement is described first as lightweight *rebar items* (plain dicts
holding the bar centre-line and its diameter). The same item list is then

* turned into pythonOCC solids for the 3D CAD window (``rebars_to_compound``), and
* passed unchanged to the IFC exporter, which writes each item as an
  ``IfcSweptDiskSolid`` inside an ``IfcReinforcingBar`` (see
  ``core/ifc_export_bridge/substructure_ifc.py``).

Keeping one description of the bars means the GUI and the IFC file can never
disagree about where a bar is or how long it is.

Rebar item kinds (all coordinates in mm, in the local frame of the builder):

``line``  straight bar          {"kind": "line", "pts": [p1, p2], "dia": d}
``poly``  open bent bar         {"kind": "poly", "pts": [p1, ..., pn], "dia": d}
``loop``  closed stirrup / tie  {"kind": "loop", "pts": [p1, ..., pn], "dia": d}
``ring``  circular hoop (axis Z){"kind": "ring", "center": c, "radius": r, "dia": d}
"""

import math

from OCC.Core.BRep import BRep_Builder
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeTorus
from OCC.Core.TopoDS import TopoDS_Compound
from OCC.Core.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec


# ---------------------------------------------------------------------------
# Rebar item constructors
# ---------------------------------------------------------------------------

def rebar_line(p1, p2, dia, role="main"):
    return {"kind": "line", "pts": [tuple(p1), tuple(p2)], "dia": float(dia), "role": role}


def rebar_poly(pts, dia, role="main"):
    return {"kind": "poly", "pts": [tuple(p) for p in pts], "dia": float(dia), "role": role}


def rebar_loop(pts, dia, role="transverse"):
    return {"kind": "loop", "pts": [tuple(p) for p in pts], "dia": float(dia), "role": role}


def rebar_ring(center, radius, dia, role="transverse"):
    return {"kind": "ring", "center": tuple(center), "radius": float(radius),
            "dia": float(dia), "role": role}


def evenly_spaced(start, end, max_spacing):
    """Positions from start to end (inclusive) with spacing <= max_spacing."""
    span = end - start
    if span <= 0:
        return [0.5 * (start + end)]
    n = int(math.ceil(span / float(max_spacing))) + 1
    step = span / (n - 1)
    return [start + i * step for i in range(n)]


def bars_on_circle(radius, spacing, minimum=6):
    """Number of longitudinal bars on a circle so that the arc spacing <= spacing."""
    return max(minimum, int(math.ceil(2.0 * math.pi * radius / float(spacing))))


def ring_points(center, radius, segments=24):
    """Polygon approximation of a horizontal ring (used for IFC directrices)."""
    cx, cy, cz = center
    return [(cx + radius * math.cos(2 * math.pi * i / segments),
             cy + radius * math.sin(2 * math.pi * i / segments), cz)
            for i in range(segments)]


def rebar_length(item):
    """Centre-line length of a rebar item in mm."""
    if item["kind"] == "ring":
        return 2.0 * math.pi * item["radius"]
    pts = list(item["pts"])
    if item["kind"] == "loop":
        pts = pts + [pts[0]]
    return sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))


# ---------------------------------------------------------------------------
# OCC conversion
# ---------------------------------------------------------------------------

def _cylinder_between(p1, p2, radius):
    v = gp_Vec(gp_Pnt(*p1), gp_Pnt(*p2))
    length = v.Magnitude()
    if length < 1e-6:
        return None
    axis = gp_Ax2(gp_Pnt(*p1), gp_Dir(v))
    return BRepPrimAPI_MakeCylinder(axis, radius, length).Shape()


def rebar_to_shapes(item):
    """Convert one rebar item into a list of OCC solids."""
    r = item["dia"] / 2.0
    if item["kind"] == "ring":
        axis = gp_Ax2(gp_Pnt(*item["center"]), gp_Dir(0, 0, 1))
        return [BRepPrimAPI_MakeTorus(axis, item["radius"], r).Shape()]
    pts = list(item["pts"])
    if item["kind"] == "loop":
        pts = pts + [pts[0]]
    shapes = []
    for a, b in zip(pts[:-1], pts[1:]):
        cyl = _cylinder_between(a, b, r)
        if cyl is not None:
            shapes.append(cyl)
    return shapes


def make_compound(shapes):
    builder = BRep_Builder()
    comp = TopoDS_Compound()
    builder.MakeCompound(comp)
    for s in shapes:
        if s is not None:
            builder.Add(comp, s)
    return comp


def rebars_to_compound(items):
    shapes = []
    for it in items:
        shapes.extend(rebar_to_shapes(it))
    return make_compound(shapes)


# ---------------------------------------------------------------------------
# Placement helpers (local assembly frame -> global bridge frame)
# ---------------------------------------------------------------------------

def placement_trsf(origin=(0.0, 0.0, 0.0), rotation_deg=0.0):
    """Rotation about the vertical (Z) axis followed by a translation."""
    rot = gp_Trsf()
    rot.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(rotation_deg))
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(*origin))
    return tr.Multiplied(rot)


def transform_shape(shape, trsf):
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()
