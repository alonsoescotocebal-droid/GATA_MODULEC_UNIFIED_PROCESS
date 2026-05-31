import json, argparse, datetime, shutil
from pathlib import Path

def iso_now():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gata-root", required=True)
    args = ap.parse_args()

    gata_root = Path(args.gata_root)
    out_root  = gata_root / "Complementariedad de analisis" / "Module C" / "03_outputs"
    qa_dir    = out_root / "qa"
    inputs_p  = qa_dir / "inputs_resolved.json"
    if not inputs_p.is_file():
        raise FileNotFoundError(f"Falta: {inputs_p}")

    tables_dir = out_root / "tables"
    if not tables_dir.is_dir():
        raise FileNotFoundError(f"Falta dir tables: {tables_dir}")

    required = [
        "IECH_unit_2015_2024.csv",
        "recurrence_unit_2015_2024.csv",
        "smoke_days_unit_2015_2024.csv",
        "pop_unit_2015_2025_2030.csv",
        "IECH_scenarios_unit_2026_2030_mean.csv"
    ]

    missing = [fn for fn in required if not (tables_dir / fn).is_file()]
    if missing:
        raise RuntimeError("Faltan CSV en 03_outputs\\tables: " + ", ".join(missing))

    # Backup
    bak = inputs_p.with_name(f"inputs_resolved.json.bak_step7_{iso_now()}")
    shutil.copy2(inputs_p, bak)

    # Read JSON (tolerante a BOM)
    obj = json.loads(inputs_p.read_text(encoding="utf-8-sig"))

    payload = {
        "tables_dir": str(tables_dir),
        "tables_files": {fn: str(tables_dir / fn) for fn in required},
        "note": "DERIVADO PARA STEP7: rutas de tablas bajo 03_outputs\\tables (backup creado)."
    }

    if isinstance(obj, dict):
        obj["derived_step7_tables"] = payload
    else:
        obj = {"inputs_resolved_original": obj, "derived_step7_tables": payload}

    inputs_p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK PATCH STEP7")
    print(" - inputs_resolved.json =", inputs_p)
    print(" - backup =", bak)
    print(" - injected keys: derived_step7_tables.tables_dir + tables_files")

if __name__ == "__main__":
    main()
