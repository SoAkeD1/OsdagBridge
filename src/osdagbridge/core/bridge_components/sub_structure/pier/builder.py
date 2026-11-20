"""
Pier builder (substructure).

Single circular RCC pier column between the pile cap and the pier cap.

Local frame: origin on the pier axis, X = span, Y = transverse, Z = up.
The column runs from ``bottom_z`` (top of pile cap) to ``top_z``
(underside of pier cap).

Reinforcement:
    * longitudinal bars dia 16, arc spacing <= 150, extended into the pile cap
      and the pier cap (``anchorage_bottom`` / ``anchorage_top``)
    * circular hoops dia 8 @ 200
    * clear cover 40

Default dimensions (brief): diameter 800, height 3000.
"""

import math

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCC.Core.gp import gp_Ax2, gp_Dir, gp_Pnt

from osdagbridge.core.bridge_components.rebar_utils import (
    bars_on_circle, evenly_spaced, rebar_line, rebar_ring, rebars_to_compound,
)

PIER_DIAMETER = 800
PIER_HEIGHT = 3000


def build_pier(
    *,
    bottom_z,
    diameter=PIER_DIAMETER,
    height=PIER_HEIGHT,
    main_dia=16,
    main_spacing=150,
    tie_dia=8,
    tie_spacing=200,
    cover=40,
    anchorage_bottom=0.0,
    anchorage_top=0.0,
):
    top_z = bottom_z + height
    r = diameter / 2.0
    concrete = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, bottom_z), gp_Dir(0, 0, 1)), r, height
    ).Shape()

    r_tie = r - cover - tie_dia / 2.0
    r_main = r - cover - tie_dia - main_dia / 2.0
    n_bars = bars_on_circle(r_main, main_spacing)

    items = []
    for k in range(n_bars):
        a = 2 * math.pi * k / n_bars
        x, y = r_main * math.cos(a), r_main * math.sin(a)
        items.append(rebar_line((x, y, bottom_z - anchorage_bottom),
                                (x, y, top_z + anchorage_top), main_dia, "main"))
    for z in evenly_spaced(bottom_z + cover, top_z - cover, tie_spacing):
        items.append(rebar_ring((0.0, 0.0, z), r_tie, tie_dia, "transverse"))

    return {
        "concrete": [concrete],
        "rebar": rebars_to_compound(items),
        "rebar_items": items,
        "info": {
            "name": "Pier",
            "diameter": diameter, "height": height,
            "bottom_z": bottom_z, "top_z": top_z,
            "n_main_bars": n_bars,
        },
    }
