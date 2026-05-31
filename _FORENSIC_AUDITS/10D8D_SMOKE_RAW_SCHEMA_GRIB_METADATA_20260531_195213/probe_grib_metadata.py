import sys, os, json, re
paths = sys.argv[1:]
out = []
for path in paths:
    row = {"path": path, "exists": os.path.exists(path), "method": "", "dates": [], "shortNames": [], "error": ""}
    if not os.path.exists(path):
        out.append(row)
        continue
    try:
        import eccodes
        row["method"] = "eccodes"
        dates = []
        names = []
        with open(path, "rb") as f:
            for i in range(0, 50):
                gid = eccodes.codes_grib_new_from_file(f)
                if gid is None:
                    break
                for key in ("dataDate", "validityDate"):
                    try:
                        v = eccodes.codes_get(gid, key)
                        if v not in dates:
                            dates.append(str(v))
                    except Exception:
                        pass
                for key in ("shortName", "paramId"):
                    try:
                        v = eccodes.codes_get(gid, key)
                        if str(v) not in names:
                            names.append(str(v))
                    except Exception:
                        pass
                eccodes.codes_release(gid)
        row["dates"] = dates[:30]
        row["shortNames"] = names[:30]
    except Exception as e1:
        try:
            import cfgrib
            row["method"] = "cfgrib_import_available_no_open"
            row["error"] = "eccodes_failed: " + repr(e1)
        except Exception as e2:
            row["method"] = "none"
            row["error"] = "eccodes_failed: " + repr(e1) + " | cfgrib_failed: " + repr(e2)
    out.append(row)
print(json.dumps(out, indent=2))
