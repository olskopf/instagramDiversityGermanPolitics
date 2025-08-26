# face_analysis/analyze_images.py

import os, sys, csv, json, time, subprocess, shutil, base64
from collections import Counter
from datetime import datetime, timezone
import pandas as pd
import re

# gültige Bild-Endungen
VALID_EXTS = (".jpg", ".jpeg", ".png")

# timestamp zwischen underscores rausziehen
_TS_UNDERSCORE = re.compile(r'_(\d{10,13})(?=_)')
# fallback: irgendeine 10-13 stellige Zahl
_TS_FALLBACK = re.compile(r'(?<!\d)(\d{10,13})(?!\d)')

_MIN_TS = int(datetime(2005, 1, 1, tzinfo=timezone.utc).timestamp())
_MAX_TS = int(datetime(2100, 1, 1, tzinfo=timezone.utc).timestamp())


def iso_from_ts(ts: int) -> str:
    # ts in iso-string wandeln
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return ""


def list_images_ordner(folder_path):
    # alle bilder im ordner sammeln
    all_imgs = []
    for f in os.listdir(folder_path):
        if f.lower().endswith(VALID_EXTS):
            full = os.path.abspath(os.path.join(folder_path, f)).replace("\\", "/")
            all_imgs.append(full)
    all_imgs.sort()
    return all_imgs


def save_progress(pfad, **kw):
    data = {"ts": int(time.time())}
    if os.path.exists(pfad):
        try:
            with open(pfad, encoding="utf-8") as r:
                data.update(json.load(r))
        except Exception:
            pass
    data.update(kw)
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)


def read_fairface_csv(dateipfad):
    df = pd.read_csv(dateipfad)

    # harmonisierung der spalten (leicht schlampig)
    if "gender" not in df.columns:
        if "gender_preds" in df.columns:
            df["gender"] = df["gender_preds"]

    if "race" not in df.columns:
        if "race_preds" in df.columns:
            df["race"] = df["race_preds"]

    if "race4" not in df.columns:
        if "race_4" in df.columns:
            df["race4"] = df["race_4"]

    if "face_name_align" not in df.columns:
        for alt in ("face_path", "file", "aligned_name"):
            if alt in df.columns:
                df["face_name_align"] = df[alt]
                break

    must_cols = {"face_name_align", "race", "gender"}
    missing = must_cols - set(df.columns)
    if missing:
        raise ValueError(f"test_outputs.csv ohne spalten: {missing}")
    return df


def extract_ts_from_filename(fname):
    # timestamp aus dateiname ziehen
    base = os.path.basename(fname)
    candidates = []

    for m in _TS_UNDERSCORE.finditer(base):
        candidates.append((m.start(), m.group(1)))

    if not candidates:
        for m in _TS_FALLBACK.finditer(base):
            candidates.append((m.start(), m.group(1)))

    if not candidates:
        return None

    candidates.sort(key=lambda t: t[0])
    ordered = [s for _, s in candidates][::-1]  # von hinten

    for s in ordered:
        try:
            n = int(s)
            if n > 10**12:
                n //= 1000  # ms → sekunden
            if _MIN_TS <= n <= _MAX_TS:
                return n
        except Exception:
            continue
    return None


def bild_to_datauri(pfad):
    try:
        with open(pfad, "rb") as f:
            content = f.read()
        return "data:image/jpeg;base64," + base64.b64encode(content).decode("ascii")
    except Exception:
        return None


def analyze_party_images(party_folder: str):
    """
    Hauptanalyse für einen Ordner mit Bildern.
    Es wird eine Reihe von outputs erstellt (json, csv, logs).
    """
    party_name = os.path.basename(party_folder.rstrip("/\\"))

    out_dir = os.path.join("data", "analysis", party_name)
    os.makedirs(out_dir, exist_ok=True)

    progress_file = os.path.join(out_dir, "progress.json")
    save_progress(progress_file, status="running", party=party_name,
                   message="Starte Analyse ...", done=0, total=0,
                   started_at=int(time.time()))

    images = list_images_ordner(party_folder)
    total = len(images)

    # outputs anlegen
    per_image_jsonl = os.path.join(out_dir, "per_image.jsonl")
    open(per_image_jsonl, "w", encoding="utf-8").close()
    per_image_rows = []
    all_faces = []

    fairface_dir = os.path.join("face_analysis", "model", "FairFace")
    predict_script = "predict.py"
    det_src = os.path.join(fairface_dir, "detected_faces")
    det_dst = os.path.join(out_dir, "detected_faces")

    if os.path.isdir(det_src):
        shutil.rmtree(det_src, ignore_errors=True)
    os.makedirs(det_src, exist_ok=True)

    log_path = os.path.join(out_dir, "predict.log")
    log = open(log_path, "w", encoding="utf-8", newline="")
    log.write(f"PARTEI: {party_name}\nTOTAL IMAGES: {total}\n\n")

    if total == 0:
        # keine bilder -> default leere dateien
        for fname in ("predictions.csv", "predictions.json", "summary.json"):
            with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
                if fname.endswith(".json"):
                    f.write("[]")
                else:
                    f.write("face_file,race,race4,gender,age\n")
        save_progress(progress_file, status="done", message="Keine Bilder da.", total=0, done=0)
        log.close()
        return os.path.join(out_dir, "predictions.csv")

    start = time.time()
    done = 0
    tmp_csv = os.path.join(out_dir, "_single.csv")

    for bild_path in images:
        bild_name = os.path.basename(bild_path)
        ts = extract_ts_from_filename(bild_name)
        iso = iso_from_ts(ts) if ts else ""

        preview = bild_to_datauri(bild_path)

        save_progress(progress_file, status="running",
                       message=f"Analysiere {bild_name}",
                       done=done, total=total,
                       current_image=bild_name,
                       current_preview=preview,
                       current_result="")

        # einzel-csv schreiben
        with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["img_path"])
            w.writerow([bild_path])

        # predict.py call
        cmd = [sys.executable, predict_script, "--csv", os.path.abspath(tmp_csv).replace("\\", "/")]
        log.write("CMD: " + " ".join(cmd) + "\n")

        try:
            proc = subprocess.run(cmd, cwd=fairface_dir, capture_output=True, text=True)
            log.write(proc.stdout or "")
            if proc.stderr:
                log.write("\nSTDERR:\n" + proc.stderr + "\n")
            if proc.returncode != 0:
                raise RuntimeError(f"predict.py exit {proc.returncode}")
        except Exception as e:
            # fehler -> trotzdem weitermachen
            rec = {
                "party": party_name,
                "image_name": bild_name,
                "img_path": bild_path,
                "created_ts": ts,
                "created_iso": iso,
                "faces_total": 0,
                "genders": {}, "races": {}, "races4": {},
                "ages": [], "error": str(e)
            }
            with open(per_image_jsonl, "a", encoding="utf-8") as jf:
                jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            per_image_rows.append(rec)
            done += 1
            elapsed = int(time.time() - start)
            save_progress(progress_file, status="running",
                           message="Fehler übersprungen",
                           done=done, total=total, elapsed_secs=elapsed,
                           current_image=bild_name,
                           current_preview=preview,
                           current_result=f"Fehler: {e}")
            continue

        # outputs von fairface lesen
        produced = os.path.join(fairface_dir, "test_outputs.csv")
        faces_df, faces_list = None, []
        if os.path.exists(produced) and os.path.getsize(produced) > 0:
            try:
                faces_df = read_fairface_csv(produced)
                faces_list = faces_df.to_dict(orient="records")
            except Exception as e:
                log.write(f"CSV Fehler bei {bild_name}: {e}\n")

        genders, races, races4 = Counter(), Counter(), Counter()
        ages = []

        for row in faces_list:
            g = str(row.get("gender", "")).strip()
            r = str(row.get("race", "")).strip()
            r4 = str(row.get("race4", "")).strip() if "race4" in row else ""
            a = row.get("age", "")
            if g: genders[g] += 1
            if r: races[r] += 1
            if r4: races4[r4] += 1
            if a != "" and a is not None:
                try:
                    ages.append(float(a))
                except Exception:
                    ages.append(str(a))

        faces_total = sum(genders.values()) if genders else 0

        rec = {
            "party": party_name,
            "image_name": bild_name,
            "img_path": bild_path,
            "created_ts": ts,
            "created_iso": iso,
            "faces_total": faces_total,
            "genders": dict(genders),
            "races": dict(races),
            "races4": dict(races4),
            "ages": ages,
            "error": None
        }
        with open(per_image_jsonl, "a", encoding="utf-8") as jf:
            jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        per_image_rows.append(rec)

        g_str = ", ".join([f"{k}={v}" for k, v in sorted(genders.items())]) or "keine"
        r_str = ", ".join([f"{k}={v}" for k, v in sorted(races.items())]) or "—"
        result_text = f"{faces_total} gesichter · Gender: {g_str} · Race: {r_str}"

        done += 1
        elapsed = int(time.time() - start)
        speed = done / max(1, elapsed)
        remaining = max(0, total - done)
        eta = int(remaining / speed) if speed > 0 else None
        save_progress(progress_file, status="running",
                       message=f"Fertig: {bild_name}",
                       done=done, total=total,
                       elapsed_secs=elapsed, eta_secs=eta,
                       current_image=bild_name,
                       current_preview=preview,
                       current_result=result_text)

        for row in faces_list:
            all_faces.append({
                "face_file": os.path.basename(str(row.get("face_name_align", ""))),
                "race": str(row.get("race", "")),
                "race4": str(row.get("race4", "")) if "race4" in row else "",
                "gender": str(row.get("gender", "")),
                "age": row.get("age", "")
            })

    # ende schleife

    if os.path.isdir(det_dst):
        shutil.rmtree(det_dst, ignore_errors=True)
    if os.path.isdir(det_src):
        shutil.move(det_src, det_dst)
        os.makedirs(det_src, exist_ok=True)

    pred_csv = os.path.join(out_dir, "predictions.csv")
    with open(pred_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["face_file", "race", "race4", "gender", "age"])
        for r in all_faces:
            w.writerow([r["face_file"], r["race"], r["race4"], r["gender"], r["age"]])
    with open(os.path.join(out_dir, "predictions.json"), "w", encoding="utf-8") as fp:
        json.dump(all_faces, fp, indent=2, ensure_ascii=False)

    # per_image.csv bauen
    per_image_csv = os.path.join(out_dir, "per_image.csv")
    all_gender_keys = sorted({k for r in per_image_rows for k in r["genders"].keys()})
    all_race_keys = sorted({k for r in per_image_rows for k in r["races"].keys()})
    all_race4_keys = sorted({k for r in per_image_rows for k in r["races4"].keys()})

    header = ["party", "image_name", "created_ts", "created_iso", "faces_total"]
    header += [f"gender_{k}" for k in all_gender_keys]
    header += [f"race_{k}" for k in all_race_keys]
    header += [f"race4_{k}" for k in all_race4_keys]
    header += ["ages_json", "error"]

    with open(per_image_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in per_image_rows:
            row = [
                r["party"], r["image_name"], r["created_ts"] or "",
                r["created_iso"] or "", r["faces_total"]
            ]
            row += [r["genders"].get(k, 0) for k in all_gender_keys]
            row += [r["races"].get(k, 0) for k in all_race_keys]
            row += [r["races4"].get(k, 0) for k in all_race4_keys]
            row += [json.dumps(r["ages"], ensure_ascii=False), r["error"] or ""]
            w.writerow(row)

    # summary schreiben
    sum_faces = sum(r["faces_total"] for r in per_image_rows)
    agg_gender, agg_race = Counter(), Counter()
    for r in per_image_rows:
        agg_gender.update(r["genders"])
        agg_race.update(r["races"])

    summary = {
        "party": party_name,
        "total_images": total,
        "images_processed": len(per_image_rows),
        "faces_total": int(sum_faces),
        "by_gender": dict(agg_gender),
        "by_race": dict(agg_race)
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False)

    elapsed = int(time.time() - start)
    save_progress(progress_file, status="done",
                   message="Analyse abgeschlossen.",
                   elapsed_secs=elapsed, total=total, done=total)
    log.close()
    return pred_csv
