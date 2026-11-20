r"""
Pier cap builder (substructure) - hammerhead / trapezoidal cap.

Elevation (looking along the span, Y horizontal, Z up):

        -L/2                                 +L/2
         +-------------------------------------+   <- top_z
         |                                     |   end depth
          \                                   /
            \                               /
              +-------------------------+          <- top_z - depth
              -Wb/2                  +Wb/2

    L  = cap length along Y. ``match_deck_width=True`` (default) sets it to the
         deck width so the cap carries every girder; otherwise ``top_width``
         (3000 in the brief) is used.
    Wb = bottom (soffit) width, 1200 in the brief, sitting on the pier.
    depth = 600 (full depth over the soffit); the cantilever tips are
         ``end_depth_ratio`` x depth deep.
    The cap is ``thickness`` mm wide along the span (X), centred on the pier.

Reinforcement:
    * top main bars dia 16 @ 150 along Y (hogging steel of the cantilevers)
    * bottom bars dia 16 @ 150 bent to follow the sloping soffit
    * closed vertical stirrups dia 8 @ 200 whose height follows the taper
    * clear cover 40
"""

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCC.Core.gp import gp_Pnt, gp_Vec

from osdagbridge.core.bridge_components.rebar_utils import (
    evenly_spaced, rebar_line, rebar_loop, rebar_poly, rebars_to_compound,
)

PIER_CAP_TOP_WIDTH = 3000
PIER_CAP_BOTTOM_WIDTH = 1200
PIER_CAP_DEPTH = 600
PIER_CAP_THICKNESS = 1200     # along the span (X)
END_DEPTH_RATIO = 0.5


def pier_cap_profile(length, bottom_width, depth, end_depth, top_z):
    """Hexagonal Y-Z outline of the hammerhead, counter-clockwise."""
    a, b = length / 2.0, bottom_width / 2.0
    return [
        (-b, top_z - depth),
        (b, top_z - depth),
        (a, top_z - end_depth),
        (a, top_z),
        (-a, top_z),
        (-a, top_z - end_depth),
    ]


def build_pier_cap(
    *,
    top_z,
    deck_width=None,
    match_deck_width=True,
    top_width=PIER_CAP_TOP_WIDTH,
    bottom_width=PIER_CAP_BOTTOM_WIDTH,
    depth=PIER_CAP_DEPTH,
    thickness=PIER_CAP_THICKNESS,
    end_depth_ratio=END_DEPTH_RATIO,
    main_dia=16,
    main_spacing=150,
    tie_dia=8,
    tie_spacing=200,
    cover=40,
):
    length = deck_width if (match_deck_width and deck_width) else top_width
    length = max(length, bottom_width)
    end_depth = depth * end_depth_ratio
    a, b = length / 2.0, bottom_width / 2.0

    # --- concrete: extrude the Y-Z profile along X -------------------------
    profile = pier_cap_profile(length, bottom_width, depth, end_depth, top_z)
    poly = BRepBuilderAPI_MakePolygon()
    for (y, z) in profile:
        poly.Add(gp_Pnt(-thickness / 2.0, y, z))
    poly.Close()
    face = BRepBuilderAPI_MakeFace(poly.Wire()).Face()
    concrete = BRepPrimAPI_MakePrism(face, gp_Vec(thickness, 0, 0)).Shape()

    def soffit_z(y):
        """Z of the underside of the cap at transverse position y."""
        ay = abs(y)
        if ay <= b:
            return top_z - depth
        t = (ay - b) / (a - b) if a > b else 1.0
        return top_z - depth + t * (depth - end_depth)

    items = []
    inset = cover + tie_dia + main_dia / 2.0
    xs = evenly_spaced(-thickness / 2.0 + inset, thickness / 2.0 - inset, main_spacing)
    y_end = a - cover - main_dia / 2.0

    # Top main bars along Y
    z_top_bar = top_z - inset
    for x in xs:
        items.append(rebar_line((x, -y_end, z_top_bar), (x, y_end, z_top_bar), main_dia, "main"))

    # Bottom bars bent along the soffit
    for x in xs:
        pts = [(x, -y_end, soffit_z(-y_end) + inset),
               (x, -b, soffit_z(-b) + inset),
               (x, b, soffit_z(b) + inset),
               (x, y_end, soffit_z(y_end) + inset)]
        items.append(rebar_poly(pts, main_dia, "main"))

    # Closed stirrups in the X-Z plane, height following the taper
    xs0 = -thickness / 2.0 + cover + tie_dia / 2.0
    xs1 = thickness / 2.0 - cover - tie_dia / 2.0
    for y in evenly_spaced(-a + cover + tie_dia, a - cover - tie_dia, tie_spacing):
        z0 = soffit_z(y) + cover + tie_dia / 2.0
        z1 = top_z - cover - tie_dia / 2.0
        items.append(rebar_loop([(xs0, y, z0), (xs1, y, z0), (xs1, y, z1), (xs0, y, z1)],
                                tie_dia, "transverse"))

    return {
        "concrete": [concrete],
        "rebar": rebars_to_compound(items),
        "rebar_items": items,
        "info": {
            "name": "Pier Cap",
            "length": length, "bottom_width": bottom_width, "depth": depth,
            "end_depth": end_depth, "thickness": thickness,
            "top_z": top_z, "bottom_z": top_z - depth,
            "profile_yz": profile,
        },
    }
