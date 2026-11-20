"""
Bill of Quantities from an exported OsdagBridge .ifc file (IfcOpenShell only).

    python tests/substructure/ifc_boq.py  model.ifc  [boq.csv]

Shows that the IFC is BOQ-ready: walks the spatial tree
(storey -> assembly -> element), reads each element's base quantities and
material, and prints concrete volume per member and steel weight per bar set.
"""
import csv
import sys

import ifcopenshell
import ifcopenshell.util.element as eu


def quantities(elem):
    out = {}
    for qset in eu.get_psets(elem, qtos_only=True).values():
        out.update({k: v for k, v in qset.items() if k != "id"})
    return out


def material_name(elem):
    m = eu.get_material(elem)
    return getattr(m, "Name", "") if m else ""


def main():
    f = ifcopenshell.open(sys.argv[1])
    rows = []
    for storey in f.by_type("IfcBuildingStorey"):
        for elem in eu.get_decomposition(storey):
            if elem.is_a("IfcElementAssembly"):
                continue
            q = quantities(elem)
            asm = eu.get_aggregate(elem)
            rows.append({
                "Storey": storey.Name,
                "Assembly": asm.Name if asm else "",
                "Class": elem.is_a(),
                "Name": elem.Name,
                "Material": material_name(elem),
                "Volume_m3": round(q.get("NetVolume", 0.0), 4) or "",
                "Count": int(q["Count"]) if "Count" in q else "",
                "Length_m": round(q.get("Length", 0.0), 3) or "",
                "Weight_kg": round(q.get("Weight", 0.0), 2) or "",
            })
    rows = [r for r in rows if r["Storey"] != "Superstructure"]

    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    summary = {}
    for r in rows:
        key = (r["Class"], r["Material"])
        s = summary.setdefault(key, [0, 0.0, 0.0])
        s[0] += 1
        s[1] += r["Volume_m3"] or 0.0
        s[2] += r["Weight_kg"] or 0.0
    print(f"{'IFC class':22s} {'Material':24s} {'No.':>4s} {'Concrete m3':>12s} {'Steel kg':>10s}")
    for (cls, mat), (n, v, w) in sorted(summary.items()):
        print(f"{cls:22s} {mat:24s} {n:4d} {v:12.3f} {w:10.1f}")
    print(f"{'TOTAL':22s} {'':24s} {'':4s} {sum(s[1] for s in summary.values()):12.3f} "
          f"{sum(s[2] for s in summary.values()):10.1f}")


if __name__ == "__main__":
    main()
