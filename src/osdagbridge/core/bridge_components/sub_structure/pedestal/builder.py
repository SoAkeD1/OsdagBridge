"""
Bearing pedestal builder (substructure).

Small RCC plinths on top of the pier cap, one under each girder, that raise
the bearing seat to the girder soffit.

Local frame: origin on the pier axis, X = span, Y = transverse, Z = up.
"""

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.gp import gp_Pnt

PEDESTAL_SIZE_X = 500
PEDESTAL_SIZE_Y = 500
PEDESTAL_HEIGHT = 150


def build_pedestals(
    *,
    y_positions,
    bottom_z,
    size_x=PEDESTAL_SIZE_X,
    size_y=PEDESTAL_SIZE_Y,
    height=PEDESTAL_HEIGHT,
):
    concrete, info = [], []
    for i, y in enumerate(y_positions):
        concrete.append(BRepPrimAPI_MakeBox(
            gp_Pnt(-size_x / 2.0, y - size_y / 2.0, bottom_z), size_x, size_y, height
        ).Shape())
        info.append({"name": f"Pedestal {i + 1}", "y": y, "size_x": size_x,
                     "size_y": size_y, "height": height, "bottom_z": bottom_z})
    return {"concrete": concrete, "info": info}
