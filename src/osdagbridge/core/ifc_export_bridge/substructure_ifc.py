"""
Substructure IFC writer.

Adds the pier caps, bearing pedestals, piers, pile caps, piles and all their
reinforcement to the IFC4 file produced by ``BridgeIfcGenerator``.

Data source: ``cad_generator.model_data["substructure_units"]`` - the same
layout the 3D CAD window was drawn from (see
``core/bridge_components/sub_structure/assembly.py``), so the IFC model and
the GUI model always match.

Spatial structure and axes
--------------------------
IfcProject
  IfcSite
    IfcBuilding "Bridge Structure"
      IfcBuildingStorey "Superstructure"   (existing girders, deck, ...)
      IfcBuildingStorey "Substructure"     <- IfcElementAssembly "Pier P<n>"
      IfcBuildingStorey "Foundation"       <- IfcElementAssembly "Foundation F<n>"

* All storeys share the global bridge axes (X span, Y width, Z up, metres).
* Each assembly has its own IfcLocalPlacement (support position + skew
  rotation about Z) relative to its storey: this is the local axis system of
  one pier unit.
* Concrete members and reinforcing bars are placed relative to their
  assembly; piles are placed relative to their pile cap.

BOQ support
-----------
* Correct IFC classes: IfcColumn (pier, pedestal), IfcBeam (pier cap),
  IfcFooting PILE_CAP, IfcPile BORED, IfcReinforcingBar MAIN / LIGATURE.
* IfcMaterial (concrete grade / rebar grade) through IfcRelAssociatesMaterial.
* Base quantities (Qto_*BaseQuantities) with volumes, lengths, counts and
  rebar weights, so a BIM tool can schedule concrete m3 and steel kg.
"""

import math

from osdagbridge.core.ifc_export_bridge.bridge_geometry_mapper import create_ifc_guid
from osdagbridge.core.bridge_components.rebar_utils import rebar_length, ring_points

S = 0.001                     # mm -> m
STEEL_DENSITY = 7850.0        # kg/m3
CONCRETE_RGB = (0.55, 0.57, 0.60)
REBAR_RGB = (0.20, 0.22, 0.27)
CONCRETE_TRANSPARENCY = 0.65   # opacity 0.35, same as the 3D CAD window


class SubstructureIfcWriter:
    def __init__(self, generator):
        self.g = generator
        self.f = generator.file
        self.oh = generator._owner_history
        self.mapper = generator.mapper
        self.metadata = generator.metadata
        self._mat_assoc = {}       # material name -> list of elements

    # ------------------------------------------------------------------ utils
    def _place(self, rel_to, origin=(0., 0., 0.), z_dir=(0., 0., 1.), x_dir=(1., 0., 0.)):
        ax = self.mapper.create_axis2placement_3d(origin, z_dir=z_dir, x_dir=x_dir)
        return self.f.createIfcLocalPlacement(rel_to, ax)

    def _identity(self):
        return self.mapper.create_axis2placement_3d((0., 0., 0.))

    def _shape(self, items, rep_type, rgb, transparency=None):
        rep = self.f.createIfcShapeRepresentation(self.mapper._context3d, "Body", rep_type, items)
        self.mapper.apply_color(rep, rgb, transparency)
        return self.f.createIfcProductDefinitionShape(None, None, [rep])

    def _material(self, element, name, category):
        if name not in self._mat_assoc:
            mat = self.f.createIfcMaterial(name, None, category)
            self._mat_assoc[name] = (mat, [])
        self._mat_assoc[name][1].append(element)

    def _quantities(self, element, qto_name, values):
        q = []
        for name, (kind, val) in values.items():
            if kind == "len":
                q.append(self.f.createIfcQuantityLength(name, None, None, float(val)))
            elif kind == "area":
                q.append(self.f.createIfcQuantityArea(name, None, None, float(val)))
            elif kind == "vol":
                q.append(self.f.createIfcQuantityVolume(name, None, None, float(val)))
            elif kind == "count":
                q.append(self.f.createIfcQuantityCount(name, None, None, float(val)))
            elif kind == "weight":
                q.append(self.f.createIfcQuantityWeight(name, None, None, float(val)))
        eq = self.f.createIfcElementQuantity(create_ifc_guid(), self.oh, qto_name, None, None, q)
        self.f.createIfcRelDefinesByProperties(create_ifc_guid(), self.oh, None, None, [element], eq)

    def _storey(self, name, elevation_mm):
        st = self.f.createIfcBuildingStorey(
            create_ifc_guid(), self.oh, Name=name,
            ObjectPlacement=self._place(self.g.building.ObjectPlacement),
            CompositionType="ELEMENT", Elevation=elevation_mm * S)
        return st

    def _assembly(self, name, storey, origin_mm, rotation_deg):
        a = math.radians(rotation_deg)
        placement = self._place(storey.ObjectPlacement,
                                origin=[v * S for v in origin_mm],
                                x_dir=(math.cos(a), math.sin(a), 0.))
        asm = self.f.createIfcElementAssembly(
            create_ifc_guid(), self.oh, Name=name, ObjectPlacement=placement,
            AssemblyPlace="SITE", PredefinedType="USERDEFINED")
        asm.ObjectType = "PierUnit" if name.startswith("Pier") else "FoundationUnit"
        self.f.createIfcRelContainedInSpatialStructure(
            create_ifc_guid(), self.oh, RelatingStructure=storey, RelatedElements=[asm])
        return asm

    # -------------------------------------------------------------- concrete
    def _extrusion(self, profile, depth_m, position=None):
        return self.mapper.create_extruded_solid(profile, depth_m, position or self._identity())

    def _circle_profile(self, radius_mm):
        return self.f.createIfcCircleProfileDef("AREA", None, self.mapper.create_axis2placement_2d(),
                                                radius_mm * S)

    def _concrete_element(self, ifc_class, name, placement, solid, grade, **attrs):
        elem = getattr(self.f, "create" + ifc_class)(
            create_ifc_guid(), self.oh, Name=name, ObjectPlacement=placement,
            Representation=self._shape([solid], "SweptSolid", CONCRETE_RGB, CONCRETE_TRANSPARENCY), **attrs)
        self._material(elem, f"Concrete {grade}", "Concrete")
        return elem

    # ---------------------------------------------------------------- rebar
    def _rebar_items_to_solids(self, items):
        solids = []
        for it in items:
            if it["kind"] == "ring":
                pts = ring_points(it["center"], it["radius"])
                pts = pts + [pts[0]]
            elif it["kind"] == "loop":
                pts = list(it["pts"]) + [it["pts"][0]]
            else:
                pts = list(it["pts"])
            ifc_pts = [self.mapper.create_cartesian_point_3d(*(c * S for c in p)) for p in pts]
            directrix = self.f.createIfcPolyline(ifc_pts)
            solids.append(self.f.createIfcSweptDiskSolid(directrix, it["dia"] / 2.0 * S, None, None, None))
        return solids

    def _rebar_set(self, name, items, placement, grade, host_name):
        """One IfcReinforcingBar per bar set (same host, diameter and role)."""
        out = []
        groups = {}
        for it in items:
            groups.setdefault((it["role"], it["dia"]), []).append(it)
        for (role, dia), group in groups.items():
            total_len_m = sum(rebar_length(it) for it in group) * S
            area_m2 = math.pi * (dia * S) ** 2 / 4.0
            weight = total_len_m * area_m2 * STEEL_DENSITY
            label = "Main" if role == "main" else "Transverse"
            bar = self.f.createIfcReinforcingBar(
                create_ifc_guid(), self.oh,
                Name=f"{name} - {label} Bars T{dia:.0f}",
                ObjectType=f"{host_name} reinforcement",
                ObjectPlacement=placement,
                Representation=self._shape(self._rebar_items_to_solids(group),
                                           "AdvancedSweptSolid", REBAR_RGB),
                SteelGrade=grade,
                NominalDiameter=dia * S,
                CrossSectionArea=area_m2,
                BarLength=total_len_m / len(group),
                PredefinedType="MAIN" if role == "main" else "LIGATURE",
                BarSurface="TEXTURED")
            self._material(bar, f"Reinforcement {grade}", "Steel")
            self._quantities(bar, "Qto_ReinforcingElementBaseQuantities", {
                "Count": ("count", len(group)),
                "Length": ("len", total_len_m),
                "Weight": ("weight", weight),
            })
            self.metadata.assign_metadata(bar, {
                "Host": host_name, "BarDiameter_mm": float(dia), "NumberOfBars": len(group),
                "TotalLength_m": round(total_len_m, 3), "Weight_kg": round(weight, 2),
            }, "Pset_OsdagReinforcement")
            out.append(bar)
        return out

    # ----------------------------------------------------------------- main
    def write(self, cad_generator):
        data = getattr(cad_generator, "model_data", {}) or {}
        units = data.get("substructure_units") or []
        p = data.get("substructure_params") or {}
        if not units:
            return
        cg, rg = p.get("concrete_grade", "M35"), p.get("rebar_grade", "Fe500")
        cover = p.get("rebar_cover", 40)

        first = units[0]["components"]
        sub_storey = self._storey("Substructure", first["pier"]["info"]["bottom_z"])
        fdn_storey = self._storey("Foundation", first["pile_cap"]["info"]["bottom_z"])
        self.f.createIfcRelAggregates(create_ifc_guid(), self.oh,
                                      RelatingObject=self.g.building,
                                      RelatedObjects=[sub_storey, fdn_storey])

        for n, unit in enumerate(units, start=1):
            c = unit["components"]
            pier_asm = self._assembly(f"Pier P{n}", sub_storey, unit["origin"], unit["rotation_deg"])
            fdn_asm = self._assembly(f"Foundation F{n}", fdn_storey, unit["origin"], unit["rotation_deg"])
            pier_parts, fdn_parts = [], []
            pa, fa = pier_asm.ObjectPlacement, fdn_asm.ObjectPlacement

            # --- Pier cap (hammerhead): Y-Z profile extruded along local X
            info = c["pier_cap"]["info"]
            pts = [(y * S, z * S) for (y, z) in info["profile_yz"]]
            prof = self.mapper.create_polygonal_profile(pts, "HammerheadProfile")
            pos = self.mapper.create_axis2placement_3d((-info["thickness"] / 2.0 * S, 0., 0.),
                                                       z_dir=(1., 0., 0.), x_dir=(0., 1., 0.))
            cap = self._concrete_element(
                "IfcBeam", f"Pier Cap P{n}", self._place(pa),
                self._extrusion(prof, info["thickness"] * S, pos), cg,
                PredefinedType="USERDEFINED")
            cap.ObjectType = "PierCap"
            area = 0.5 * abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                                 in zip(info["profile_yz"], info["profile_yz"][1:] + info["profile_yz"][:1])))
            self._quantities(cap, "Qto_BeamBaseQuantities", {
                "Length": ("len", info["length"] * S),
                "CrossSectionArea": ("area", area * S * S),
                "NetVolume": ("vol", area * info["thickness"] * S ** 3)})
            self.metadata.assign_metadata(cap, {
                "ConcreteGrade": cg, "TopLength_mm": float(info["length"]),
                "BottomWidth_mm": float(info["bottom_width"]), "Depth_mm": float(info["depth"]),
                "Thickness_mm": float(info["thickness"]), "ClearCover_mm": float(cover)})
            pier_parts.append(cap)
            pier_parts += self._rebar_set(f"Pier Cap P{n}", c["pier_cap"]["rebar_items"], self._place(pa), rg, "Pier Cap")

            # --- Bearing pedestals
            for ped in c["pedestals"]["info"]:
                prof = self.mapper.create_rectangular_profile(ped["size_x"] * S, ped["size_y"] * S)
                e = self._concrete_element(
                    "IfcColumn", f"{ped['name']} P{n}",
                    self._place(pa, (0., ped["y"] * S, ped["bottom_z"] * S)),
                    self._extrusion(prof, ped["height"] * S), cg, PredefinedType="USERDEFINED")
                e.ObjectType = "BearingPedestal"
                self._quantities(e, "Qto_ColumnBaseQuantities", {
                    "Length": ("len", ped["height"] * S),
                    "NetVolume": ("vol", ped["size_x"] * ped["size_y"] * ped["height"] * S ** 3)})
                pier_parts.append(e)

            # --- Pier column
            info = c["pier"]["info"]
            r = info["diameter"] / 2.0
            pier = self._concrete_element(
                "IfcColumn", f"Pier P{n}", self._place(pa, (0., 0., info["bottom_z"] * S)),
                self._extrusion(self._circle_profile(r), info["height"] * S), cg,
                PredefinedType="COLUMN")
            self._quantities(pier, "Qto_ColumnBaseQuantities", {
                "Length": ("len", info["height"] * S),
                "CrossSectionArea": ("area", math.pi * (r * S) ** 2),
                "NetVolume": ("vol", math.pi * (r * S) ** 2 * info["height"] * S)})
            self.metadata.assign_metadata(pier, {
                "ConcreteGrade": cg, "Diameter_mm": float(info["diameter"]),
                "Height_mm": float(info["height"]), "ClearCover_mm": float(cover)})
            pier_parts.append(pier)
            pier_parts += self._rebar_set(f"Pier P{n}", c["pier"]["rebar_items"], self._place(pa), rg, "Pier")

            # --- Pile cap
            info = c["pile_cap"]["info"]
            pc_place = self._place(fa, (0., 0., info["bottom_z"] * S))
            prof = self.mapper.create_rectangular_profile(info["width"] * S, info["length"] * S)
            pile_cap = self._concrete_element(
                "IfcFooting", f"Pile Cap F{n}", pc_place,
                self._extrusion(prof, info["depth"] * S), cg, PredefinedType="PILE_CAP")
            self._quantities(pile_cap, "Qto_FootingBaseQuantities", {
                "Length": ("len", info["length"] * S), "Width": ("len", info["width"] * S),
                "Height": ("len", info["depth"] * S),
                "NetVolume": ("vol", info["length"] * info["width"] * info["depth"] * S ** 3)})
            self.metadata.assign_metadata(pile_cap, {
                "ConcreteGrade": cg, "Length_mm": float(info["length"]),
                "Width_mm": float(info["width"]), "Depth_mm": float(info["depth"]),
                "ClearCover_mm": float(cover)})
            fdn_parts.append(pile_cap)
            fdn_parts += self._rebar_set(f"Pile Cap F{n}", c["pile_cap"]["rebar_items"], self._place(fa), rg, "Pile Cap")

            # --- Piles: placed relative to the pile cap (nested local axes)
            for pile in c["piles"]["piles"]:
                rp = pile["diameter"] / 2.0
                place = self._place(pc_place, (pile["x"] * S, pile["y"] * S, -pile["length"] * S))
                e = self._concrete_element(
                    "IfcPile", f"{pile['name']} F{n}", place,
                    self._extrusion(self._circle_profile(rp), pile["length"] * S), cg,
                    PredefinedType="BORED", ConstructionType="CAST_IN_PLACE")
                self._quantities(e, "Qto_PileBaseQuantities", {
                    "Length": ("len", pile["length"] * S),
                    "CrossSectionArea": ("area", math.pi * (rp * S) ** 2),
                    "NetVolume": ("vol", math.pi * (rp * S) ** 2 * pile["length"] * S)})
                self.metadata.assign_metadata(e, {
                    "ConcreteGrade": cg, "Diameter_mm": float(pile["diameter"]),
                    "Length_mm": float(pile["length"]), "ClearCover_mm": float(cover)})
                fdn_parts.append(e)
                fdn_parts += self._rebar_set(f"{pile['name']} F{n}", pile["rebar_items"], self._place(fa), rg, "Pile")

            self.f.createIfcRelAggregates(create_ifc_guid(), self.oh,
                                          RelatingObject=pier_asm, RelatedObjects=pier_parts)
            self.f.createIfcRelAggregates(create_ifc_guid(), self.oh,
                                          RelatingObject=fdn_asm, RelatedObjects=fdn_parts)

        for name, (mat, elems) in self._mat_assoc.items():
            self.f.createIfcRelAssociatesMaterial(create_ifc_guid(), self.oh, None, None, elems, mat)


def add_substructure_to_ifc(generator, cad_generator):
    """Entry point used by BridgeIfcGenerator.generate_from_extracted_data."""
    SubstructureIfcWriter(generator).write(cad_generator)
