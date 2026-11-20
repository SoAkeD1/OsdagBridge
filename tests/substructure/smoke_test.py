"""
Headless check of the substructure CAD + IFC workflow (no GUI needed).

    conda activate osdagbridge-env
    cd osdagbridge/src            # repo-root/src
    python ../tests/substructure/smoke_test.py  [output.ifc]

1. Builds the full plate-girder bridge with PlateGirderCADGenerator.generate()
   (superstructure + new substructure) using the same sample parameters as
   the standalone test in desktop/ui/cad_3d.py.
2. Checks that every substructure solid is valid (BRepCheck) and reports the
   bounding box of each component.
3. Exports the IFC file through the same handler the GUI uses
   (File > Save 3D CAD Model > .ifc) and re-opens it with IfcOpenShell to
   list element counts and the BOQ (concrete m3, rebar kg).
"""
import sys
import os
from collections import Counter

from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib

from osdagbridge.core.bridge_types.plate_girder.cad_generator import PlateGirderCADGenerator
from osdagbridge.core.bridge_types.plate_girder.dto import (
    BridgeParametersDTO, SectionDimsDTO, ISectionDimsDTO, ShearStudParamsDTO, GirderSegmentDTO,
)
from osdagbridge.core.ifc_export_bridge.export_ifc_handler import PlateGirderIfcExportHandler


def sample_params(skew=0):
    angle = dict(leg_h=100, leg_w=50, connection_type="LONGER_LEG")
    small = dict(leg_h=80, leg_w=40, connection_type="LONGER_LEG")
    return BridgeParametersDTO(
        steel_grade="E250", concrete_grade="M35",
        span_length_L=25_000, girder_section_d=900, girder_section_bf=500, girder_section_bf_b=500,
        girder_section_tf=260, girder_section_tf_b=260, girder_section_tw=100,
        num_girders=5, girder_spacing=2_750, skew_angle=skew,
        carriageway_width=12_000, deck_thickness=400, footpath_config="BOTH",
        footpath_width=1_500, railing_width=300,
        barrier_type="Semi-Rigid", crash_barrier_subtype="Double W-beam",
        enable_median=True, median_type="Metallic Crash Barrier", rail_count=3, railing_type="rcc",
        include_intermediate_stiffeners=True, intermediate_stiffener_spacing=2_000,
        intermediate_stiffener_thickness=20, intermediate_stiffener_outstand=None,
        num_end_stiffener_pairs=4, end_stiffener_thickness=30, end_stiffener_outstand=None,
        include_longitudinal_stiffeners=True, num_longitudinal_stiffeners=2,
        longitudinal_stiffener_thickness=20, longitudinal_stiffener_outstand=None,
        cross_bracing_spacing=4_000, bracing_type="X", x_bracket_option="BOTH", k_top_bracket=True,
        diagonal_section_type="ANGLE", diagonal_section_dims=SectionDimsDTO(**angle), diagonal_thickness=5,
        top_chord_section_type="DOUBLE_CHANNEL", top_chord_section_dims=SectionDimsDTO(**small), top_chord_thickness=5,
        bottom_chord_section_type="ANGLE", bottom_chord_section_dims=SectionDimsDTO(**small), bottom_chord_thickness=5,
        end_diaphragm_type="Cross Bracing", end_diaphragm_spacing=100, end_diaphragm_bracing_type="K",
        end_diaphragm_diagonal_section_type="ANGLE", end_diaphragm_diagonal_section_dims=SectionDimsDTO(**angle),
        end_diaphragm_diagonal_thickness=5,
        end_diaphragm_top_chord_section_type="CHANNEL", end_diaphragm_top_chord_section_dims=SectionDimsDTO(**small),
        end_diaphragm_top_chord_thickness=5,
        end_diaphragm_bottom_chord_section_type="ANGLE", end_diaphragm_bottom_chord_section_dims=SectionDimsDTO(**small),
        end_diaphragm_bottom_chord_thickness=5,
        end_diaphragm_section="I_SECTION",
        end_diaphragm_dims=ISectionDimsDTO(depth=800, flange_width=250, web_thickness=12, flange_thickness=100),
        shear_stud_params=ShearStudParamsDTO(base_diameter=50, top_diameter=70, base_height=150, top_height=50,
                                             num_per_section=4, transverse_spacing=305, pitch=500),
        girder_segments=[GirderSegmentDTO(length=25_000, D=900, tw=100, T_ft=260, T_fb=260, B_ft=500, B_fb=500)],
        girder_segments_dict=None,
    )


def bbox(shape):
    b = Bnd_Box()
    brepbndlib.Add(shape, b)
    return [round(v) for v in b.Get()]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath("osdag_bridge_substructure.ifc")
    skew = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0

    gen = PlateGirderCADGenerator()
    gen.model_data = gen.generate(sample_params(skew))
    md = gen.model_data

    print("Superstructure deck bbox :", bbox(md["deck_slab"][0] if isinstance(md["deck_slab"], list) else md["deck_slab"]))
    for key in ("pier_caps", "pedestals", "piers", "pile_caps", "piles", "substructure_rebar"):
        shp = md[key][0]
        ok = BRepCheck_Analyzer(shp).IsValid()
        print(f"{key:20s} valid={ok}  bbox={bbox(shp)}")

    done = {}
    PlateGirderIfcExportHandler(gen, out, lambda ok, msg: done.update(ok=ok, msg=msg)).export()
    print(done.get("msg"))

    import ifcopenshell
    f = ifcopenshell.open(out)
    counts = Counter(e.is_a() for e in f.by_type("IfcElement"))
    print("IFC elements:", dict(counts))
    print("Storeys:", [s.Name for s in f.by_type("IfcBuildingStorey")])

    vol, kg = 0.0, 0.0
    for q in f.by_type("IfcQuantityVolume"):
        if q.Name == "NetVolume":
            vol += q.VolumeValue
    for q in f.by_type("IfcQuantityWeight"):
        kg += q.WeightValue
    print(f"BOQ substructure: concrete {vol:.2f} m3, reinforcement {kg:.0f} kg")


if __name__ == "__main__":
    main()
