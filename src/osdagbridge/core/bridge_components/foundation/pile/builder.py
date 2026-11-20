"""
Pile builder (foundation).

Builds a group of bored cast-in-situ circular piles under one pile cap, with
their longitudinal bars and circular hoops.

Local frame (same as every substructure builder):
    origin = pier axis, X = span direction, Y = transverse, Z = up.
The piles hang below ``top_z`` (the underside of the pile cap). Longitudinal
bars are extended ``anchorage_into_cap`` mm up into the pile cap.

Default dimensions follow the FOSSEE screening-task brief:
    4 piles in a 2 x 2 grid, dia 400, length 5000, spacing 600 c/c,
    main bars dia 16 @ 150, hoops dia 8 @ 200, clear cover 40.
"""

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCC.Core.gp import gp_Ax2, gp_Dir, gp_Pnt

from osdagbridge.core.bridge_components.rebar_utils import (
    bars_on_circle, evenly_spaced, make_compound, rebar_line, rebar_ring,
    rebars_to_compound,
)

# Default parameters (mm)
PILE_DIAMETER = 400
PILE_LENGTH = 5000
PILE_SPACING = 600          # centre-to-centre, both directions
N_PILES_X = 2
N_PILES_Y = 2


def pile_positions(n_x=N_PILES_X, n_y=N_PILES_Y, spacing_x=PILE_SPACING, spacing_y=PILE_SPACING):
    """(x, y) centres of a rectangular pile grid centred on the pier axis."""
    xs = [(i - (n_x - 1) / 2.0) * spacing_x for i in range(n_x)]
    ys = [(j - (n_y - 1) / 2.0) * spacing_y for j in range(n_y)]
    return [(x, y) for x in xs for y in ys]


def build_piles(
    *,
    top_z,
    pile_diameter=PILE_DIAMETER,
    pile_length=PILE_LENGTH,
    n_x=N_PILES_X,
    n_y=N_PILES_Y,
    spacing_x=PILE_SPACING,
    spacing_y=PILE_SPACING,
    main_dia=16,
    main_spacing=150,
    tie_dia=8,
    tie_spacing=200,
    cover=40,
    anchorage_into_cap=300,
):
    """
    Returns:
        dict with
            concrete : list[TopoDS_Shape]  one cylinder per pile
            rebar    : TopoDS_Compound     all pile reinforcement
            rebar_items : list[dict]       bar centre-lines (for IFC / BOQ)
            piles    : list[dict]          per-pile data for IFC
    """
    concrete, rebar_items, piles = [], [], []
    bottom_z = top_z - pile_length

    r_pile = pile_diameter / 2.0
    r_tie = r_pile - cover - tie_dia / 2.0              # hoop centre-line radius
    r_main = r_pile - cover - tie_dia - main_dia / 2.0  # main bar centre-line radius
    n_bars = bars_on_circle(r_main, main_spacing)

    import math
    for idx, (x, y) in enumerate(pile_positions(n_x, n_y, spacing_x, spacing_y)):
        axis = gp_Ax2(gp_Pnt(x, y, bottom_z), gp_Dir(0, 0, 1))
        concrete.append(BRepPrimAPI_MakeCylinder(axis, r_pile, pile_length).Shape())

        items = []
        # Longitudinal bars: from bottom cover up into the pile cap
        for k in range(n_bars):
            a = 2 * math.pi * k / n_bars
            bx, by = x + r_main * math.cos(a), y + r_main * math.sin(a)
            items.append(rebar_line((bx, by, bottom_z + cover),
                                    (bx, by, top_z + anchorage_into_cap),
                                    main_dia, role="main"))
        # Circular hoops along the pile shaft
        for z in evenly_spaced(bottom_z + cover + tie_dia / 2.0,
                               top_z - cover - tie_dia / 2.0, tie_spacing):
            items.append(rebar_ring((x, y, z), r_tie, tie_dia, role="transverse"))

        rebar_items.extend(items)
        piles.append({
            "name": f"Pile {idx + 1}",
            "x": x, "y": y, "top_z": top_z, "bottom_z": bottom_z,
            "diameter": pile_diameter, "length": pile_length,
            "rebar_items": items,
        })

    return {
        "concrete": concrete,
        "concrete_compound": make_compound(concrete),
        "rebar": rebars_to_compound(rebar_items),
        "rebar_items": rebar_items,
        "piles": piles,
    }
