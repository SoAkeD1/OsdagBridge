# Substructure 3D CAD + IFC (FOSSEE Winter Internship 2026 screening task)

This branch adds parametric pythonOCC models of the bridge **substructure**
(pier cap, bearing pedestals, pier, pile cap, piles, and all their reinforcement)
to OsdagBridge. It shows them in the desktop 3D CAD window next to the existing
superstructure and writes them into the `.ifc` export.

## What was added / changed

```
src/osdagbridge/core/bridge_components/
├── rebar_utils.py                    NEW  shared rebar description + OCC helpers
├── sub_structure/
│   ├── assembly.py                   NEW  stacks the builders into one pier unit and
│   │                                      places a unit under each support line
│   ├── pier/builder.py               NEW  circular pier + longitudinal bars + hoops
│   ├── pier_cap/builder.py           NEW  hammerhead (trapezoidal) cap + top/bottom bars + stirrups
│   └── pedestal/builder.py           NEW  bearing pedestals under each girder
└── foundation/
    ├── pile_cap/builder.py           NEW  rectangular pile cap + top/bottom mats + side ties
    └── pile/builder.py               NEW  2x2 bored piles + longitudinal bars + hoops

src/osdagbridge/core/bridge_types/plate_girder/cad_generator.py
                                      CHANGED  STEP 12 builds the substructure; new keys in model_data
src/osdagbridge/desktop/ui/cad_3d.py  CHANGED  draws concrete at 0.35 opacity and rebar opaque;
                                               new "Substructure" and "Reinforcement" checkboxes
src/osdagbridge/core/ifc_export_bridge/
├── substructure_ifc.py               NEW  writes substructure + rebar to IFC4 (storeys,
│                                          assemblies, local placements, materials, quantities)
└── bridge_ifc_generator.py           CHANGED  calls the substructure writer before saving
tests/substructure/smoke_test.py      NEW  headless check: builds the model, validates the
                                           solids, exports the IFC and prints a BOQ
```

## Data flow

```
builder.py files (pier, pier_cap, pedestal, pile_cap, pile)
        │  concrete solids + rebar items (bar centre-lines)
        ▼
sub_structure/assembly.py  ── one unit per support (x = 0 and x = L), skew rotation
        ▼
plate_girder/cad_generator.py  generate() → model_data["piers", "pier_caps", "pile_caps",
        │                                   "piles", "pedestals", "substructure_rebar",
        │                                   "substructure_units", "substructure_params"]
        ├──► desktop/ui/cad_3d.py   display (concrete transparency 0.65, rebar opaque)
        └──► ifc_export_bridge/substructure_ifc.py   File > Save 3D CAD Model > .ifc
```

The rebar is stored once as centre-lines (`line`, `poly`, `loop`, `ring`). The GUI
turns them into OCC cylinders/tori, and the IFC writer turns the **same** list into
`IfcSweptDiskSolid`s, so the CAD view and the IFC file always match.

## Default parameters (mm), from the task brief

| Component | Parameters |
|---|---|
| Pier | diameter 800, height 3000 |
| Pier cap | top length = deck width (or 3000 when `pier_cap_match_deck_width=False`), bottom 1200, depth 600, thickness along span 1200 |
| Pile cap | 2200 (Y) x 1200 (X) x 600 |
| Piles | 2 x 2, dia 400, length 5000, spacing 600 c/c, bars anchored 300 into the cap |
| Rebar | main dia 16 @ 150, transverse dia 8 @ 200, clear cover 40 |

All values live in `DEFAULT_SUBSTRUCTURE_PARAMS` in `sub_structure/assembly.py`. A
design can override any of them by giving the DTO an optional `substructure_params`
dict.

## Axes

* X is the span, Y is the deck width, Z is vertical. The substructure uses the same
  frame and Z datum as the existing superstructure (girders run from x = 0 to x = L),
  so the two line up without any extra transformation.
* Each pier unit has its own local frame: the origin is on the pier axis at the
  support line, rotated about Z by the skew angle. In the IFC file this frame is the
  `IfcLocalPlacement` of the `IfcElementAssembly` "Pier P<n>" / "Foundation F<n>".
  Members are placed relative to their assembly, and piles are placed relative to
  their pile cap.

## IFC structure

```
IfcProject → IfcSite → IfcBuilding "Bridge Structure"
   ├─ IfcBuildingStorey "Superstructure"   girders, deck, bracing, barriers (existing)
   ├─ IfcBuildingStorey "Substructure"     IfcElementAssembly Pier P1, P2
   │      IfcBeam (PierCap), IfcColumn (Pier, BearingPedestal), IfcReinforcingBar
   └─ IfcBuildingStorey "Foundation"       IfcElementAssembly Foundation F1, F2
          IfcFooting PILE_CAP, IfcPile BORED, IfcReinforcingBar
```

Each element carries an `IfcMaterial` (Concrete M35 / Reinforcement Fe500), a
`Qto_*BaseQuantities` set (volume, length, area; rebar count, length and weight),
and an Osdag property set. A BIM tool can therefore schedule concrete m³ and steel kg
(a BOQ) directly from the file.

## Running

```
conda activate osdagbridge-env
cd src
python -m osdagbridge.desktop                  # GUI: design, then File > Save 3D CAD Model > .ifc
python ../tests/substructure/smoke_test.py out.ifc   # headless check + BOQ printout
```
