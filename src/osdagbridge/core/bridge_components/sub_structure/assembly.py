"""
Substructure assembly.

Stacks the individual substructure builders into one pier-and-foundation
unit and places one unit under each support line of the superstructure.

Vertical stack (top to bottom) in the local frame of one unit:

    girder soffit (bearing level)            z_bearing
    bearing pedestals                        pedestal_height
    hammerhead pier cap                      pier_cap_depth
    circular pier                            pier_height
    pile cap                                 pile_cap_depth
    piles (2 x 2)                            pile_length

Local frame of a unit: origin on the pier axis at the support line
(X = span, Y = transverse, Z = up, same Z datum as the superstructure).
Global placement = rotation about Z by the skew angle, then a translation
to the support's X position. The same origin/rotation is written to the IFC
file as the IfcLocalPlacement of the pier assembly, so every element inside
it keeps a proper relative local axis system.
"""

import math

from osdagbridge.core.bridge_components.rebar_utils import (
    make_compound, placement_trsf, transform_shape,
)
from osdagbridge.core.bridge_components.foundation.pile.builder import build_piles
from osdagbridge.core.bridge_components.foundation.pile_cap.builder import build_pile_cap
from osdagbridge.core.bridge_components.sub_structure.pier.builder import build_pier
from osdagbridge.core.bridge_components.sub_structure.pier_cap.builder import build_pier_cap
from osdagbridge.core.bridge_components.sub_structure.pedestal.builder import build_pedestals


# Default substructure parameters (mm) - values from the screening-task brief
DEFAULT_SUBSTRUCTURE_PARAMS = {
    # Pier (circular column)
    "pier_diameter": 800,
    "pier_height": 3000,
    # Pier cap (hammerhead / trapezoidal)
    "pier_cap_top_width": 3000,
    "pier_cap_bottom_width": 1200,
    "pier_cap_depth": 600,
    "pier_cap_thickness": 1200,
    "pier_cap_match_deck_width": True,
    "pier_cap_end_depth_ratio": 0.5,
    # Pile cap
    "pile_cap_length": 2200,
    "pile_cap_width": 1200,
    "pile_cap_depth": 600,
    # Piles
    "n_piles_x": 2,
    "n_piles_y": 2,
    "pile_diameter": 400,
    "pile_length": 5000,
    "pile_spacing": 600,
    "pile_anchorage_into_cap": 300,
    # Bearing pedestals
    "pedestal_height": 150,
    "pedestal_size": 500,
    # Reinforcement
    "rebar_main_diameter": 16,
    "rebar_spacing_longitudinal": 150,
    "rebar_transverse_diameter": 8,
    "rebar_spacing_transverse": 200,
    "rebar_cover": 40,
    # Material grades (metadata only)
    "concrete_grade": "M35",
    "rebar_grade": "Fe500",
}


def build_substructure_unit(*, z_bearing, deck_width, girder_y_positions, p):
    """Build one pier + foundation unit in its local frame."""
    rb = dict(main_dia=p["rebar_main_diameter"], main_spacing=p["rebar_spacing_longitudinal"],
              tie_dia=p["rebar_transverse_diameter"], tie_spacing=p["rebar_spacing_transverse"],
              cover=p["rebar_cover"])

    z_cap_top = z_bearing - p["pedestal_height"]
    z_pier_top = z_cap_top - p["pier_cap_depth"]
    z_pier_bot = z_pier_top - p["pier_height"]
    z_pile_cap_bot = z_pier_bot - p["pile_cap_depth"]

    pedestals = build_pedestals(y_positions=girder_y_positions, bottom_z=z_cap_top,
                                size_x=p["pedestal_size"], size_y=p["pedestal_size"],
                                height=p["pedestal_height"])

    pier_cap = build_pier_cap(top_z=z_cap_top, deck_width=deck_width,
                              match_deck_width=p["pier_cap_match_deck_width"],
                              top_width=p["pier_cap_top_width"],
                              bottom_width=p["pier_cap_bottom_width"],
                              depth=p["pier_cap_depth"], thickness=p["pier_cap_thickness"],
                              end_depth_ratio=p["pier_cap_end_depth_ratio"], **rb)

    md, cv = p["rebar_main_diameter"], p["rebar_cover"]
    pier = build_pier(bottom_z=z_pier_bot, diameter=p["pier_diameter"], height=p["pier_height"],
                      anchorage_bottom=p["pile_cap_depth"] - cv - 3 * md,
                      anchorage_top=p["pier_cap_depth"] - cv - p["rebar_transverse_diameter"] - 2 * md,
                      **rb)

    pile_cap = build_pile_cap(top_z=z_pier_bot, length=p["pile_cap_length"],
                              width=p["pile_cap_width"], depth=p["pile_cap_depth"], **rb)

    piles = build_piles(top_z=z_pile_cap_bot, pile_diameter=p["pile_diameter"],
                        pile_length=p["pile_length"], n_x=p["n_piles_x"], n_y=p["n_piles_y"],
                        spacing_x=p["pile_spacing"], spacing_y=p["pile_spacing"],
                        anchorage_into_cap=p["pile_anchorage_into_cap"], **rb)

    return {"pedestals": pedestals, "pier_cap": pier_cap, "pier": pier,
            "pile_cap": pile_cap, "piles": piles}


def build_substructure(
    *,
    span_length,
    z_bearing,
    deck_width,
    num_girders,
    girder_spacing,
    skew_angle=0.0,
    support_x_positions=None,
    params=None,
):
    """
    Build every substructure unit and place it in the global bridge frame.

    Args:
        span_length: span L (mm); default supports are at x = 0 and x = L.
        z_bearing: Z of the girder soffit (bearing level) in the bridge frame.
        deck_width: overall deck width (mm), used for the pier cap length.
        num_girders, girder_spacing: girder layout for the bearing pedestals.
        skew_angle: skew of the support line in degrees (as used by the
            superstructure: x_shift = y * tan(skew)).
        params: overrides for DEFAULT_SUBSTRUCTURE_PARAMS.

    Returns:
        dict of display-ready compounds (global frame) plus "substructure_units",
        the per-unit layout consumed by the IFC exporter.
    """
    p = dict(DEFAULT_SUBSTRUCTURE_PARAMS)
    if params:
        p.update({k: v for k, v in params.items() if v is not None})

    if support_x_positions is None:
        support_x_positions = [0.0, float(span_length)]

    theta = math.radians(skew_angle or 0.0)
    cos_t = math.cos(theta) if abs(math.cos(theta)) > 1e-6 else 1.0
    rotation_deg = -float(skew_angle or 0.0)   # local +Y -> skewed support line

    total = (num_girders - 1) * girder_spacing
    girder_y_local = [((i * girder_spacing) - total / 2.0) / cos_t for i in range(num_girders)]

    out = {k: [] for k in ("pier", "pier_cap", "pile_cap", "piles", "pedestals",
                           "pier_rebar", "pier_cap_rebar", "pile_cap_rebar", "pile_rebar")}
    units = []

    for idx, x_s in enumerate(support_x_positions):
        unit = build_substructure_unit(z_bearing=z_bearing, deck_width=deck_width / cos_t,
                                       girder_y_positions=girder_y_local, p=p)
        trsf = placement_trsf((x_s, 0.0, 0.0), rotation_deg)
        g = lambda shp: transform_shape(shp, trsf)

        out["pedestals"] += [g(s) for s in unit["pedestals"]["concrete"]]
        out["pier_cap"] += [g(s) for s in unit["pier_cap"]["concrete"]]
        out["pier"] += [g(s) for s in unit["pier"]["concrete"]]
        out["pile_cap"] += [g(s) for s in unit["pile_cap"]["concrete"]]
        out["piles"] += [g(s) for s in unit["piles"]["concrete"]]
        out["pier_cap_rebar"].append(g(unit["pier_cap"]["rebar"]))
        out["pier_rebar"].append(g(unit["pier"]["rebar"]))
        out["pile_cap_rebar"].append(g(unit["pile_cap"]["rebar"]))
        out["pile_rebar"].append(g(unit["piles"]["rebar"]))

        units.append({
            "name": f"Pier P{idx + 1}",
            "origin": (float(x_s), 0.0, 0.0),
            "rotation_deg": rotation_deg,
            "components": unit,
        })

    def _c(key):
        return [make_compound(out[key])] if out[key] else []

    rebar_all = out["pier_rebar"] + out["pier_cap_rebar"] + out["pile_cap_rebar"] + out["pile_rebar"]
    return {
        "pier": _c("pier"),
        "pier_cap": _c("pier_cap"),
        "pile_cap": _c("pile_cap"),
        "piles": _c("piles"),
        "pedestals": _c("pedestals"),
        "substructure_rebar": [make_compound(rebar_all)] if rebar_all else [],
        "substructure_units": units,
        "substructure_params": p,
    }
