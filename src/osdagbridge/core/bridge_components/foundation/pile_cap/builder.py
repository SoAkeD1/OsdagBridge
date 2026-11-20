"""
Pile cap builder (foundation).

Rectangular RCC pile cap that transfers the pier load to the pile group.

Local frame: origin on the pier axis, X = span, Y = transverse, Z = up.
The cap occupies  -width/2..width/2 (X), -length/2..length/2 (Y),
top_z - depth .. top_z (Z).

Reinforcement:
    * bottom and top mats, main bars dia 16 @ 150 in both directions
    * horizontal perimeter ties dia 8 @ 200 on the side faces
    * clear cover 40 on every face

Default dimensions (brief): 2200 (Y) x 1200 (X) x 600 deep.
"""

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt

from osdagbridge.core.bridge_components.rebar_utils import (
    evenly_spaced, rebar_line, rebar_loop, rebars_to_compound,
)

PILE_CAP_LENGTH = 2200   # along Y (transverse)
PILE_CAP_WIDTH = 1200    # along X (span)
PILE_CAP_DEPTH = 600


def build_pile_cap(
    *,
    top_z,
    length=PILE_CAP_LENGTH,
    width=PILE_CAP_WIDTH,
    depth=PILE_CAP_DEPTH,
    main_dia=16,
    main_spacing=150,
    tie_dia=8,
    tie_spacing=200,
    cover=40,
):
    bottom_z = top_z - depth
    concrete = BRepPrimAPI_MakeBox(
        gp_Pnt(-width / 2.0, -length / 2.0, bottom_z), width, length, depth
    ).Shape()

    items = []
    # Bars stop `cover` short of each face
    x0, x1 = -width / 2.0 + cover + tie_dia, width / 2.0 - cover - tie_dia
    y0, y1 = -length / 2.0 + cover + tie_dia, length / 2.0 - cover - tie_dia

    # Bottom mat: layer 1 along Y, layer 2 along X on top of it
    z_b1 = bottom_z + cover + main_dia / 2.0
    z_b2 = z_b1 + main_dia
    # Top mat: layer 1 along Y (outermost), layer 2 along X below it
    z_t1 = top_z - cover - main_dia / 2.0
    z_t2 = z_t1 - main_dia

    for x in evenly_spaced(x0, x1, main_spacing):
        items.append(rebar_line((x, y0, z_b1), (x, y1, z_b1), main_dia, "main"))
        items.append(rebar_line((x, y0, z_t1), (x, y1, z_t1), main_dia, "main"))
    for y in evenly_spaced(y0, y1, main_spacing):
        items.append(rebar_line((x0, y, z_b2), (x1, y, z_b2), main_dia, "main"))
        items.append(rebar_line((x0, y, z_t2), (x1, y, z_t2), main_dia, "main"))

    # Side-face perimeter ties between the two mats
    xt0, xt1 = -width / 2.0 + cover + tie_dia / 2.0, width / 2.0 - cover - tie_dia / 2.0
    yt0, yt1 = -length / 2.0 + cover + tie_dia / 2.0, length / 2.0 - cover - tie_dia / 2.0
    for z in evenly_spaced(z_b2 + main_dia, z_t2 - main_dia, tie_spacing):
        items.append(rebar_loop([(xt0, yt0, z), (xt1, yt0, z), (xt1, yt1, z), (xt0, yt1, z)],
                                tie_dia, "transverse"))

    return {
        "concrete": [concrete],
        "rebar": rebars_to_compound(items),
        "rebar_items": items,
        "info": {
            "name": "Pile Cap",
            "length": length, "width": width, "depth": depth,
            "top_z": top_z, "bottom_z": bottom_z,
        },
    }
