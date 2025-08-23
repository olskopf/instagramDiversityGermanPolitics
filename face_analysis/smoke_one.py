# face_analysis/smoke_one.py

import os, sys, csv, subprocess
import pandas as pd

# Bildpfad (einfach ein einzelnes testbild nehmen)
TEST_IMG = r"C:/workspaceUniLeipzig/CulturalAnalytics/instagramDiversityGermanPolitics/data/Grune/3459825171206384036_2016981347_jpg.jpg"

FAIRFACE_DIR = os.path.join("face_analysis", "model", "FairFace")
CSV_FILE = "one_test.csv"
CSV_PATH = os.path.join(FAIRFACE_DIR, CSV_FILE)

if not os.path.isfile(TEST_IMG):
    raise SystemExit("Bild nicht gefunden: " + TEST_IMG)

# CSV bauen mit header
with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["img_path"])
    writer.writerow([os.path.abspath(TEST_IMG).replace("\\", "/")])

def run_script(script_name):
    cmd = [sys.executable, script_name, "--csv", CSV_FILE]  # nur filename, cwd wird gesetzt
    print("RUN:", " ".join(cmd), "(cwd=", FAIRFACE_DIR, ")")
    result = subprocess.run(cmd, cwd=FAIRFACE_DIR)
    return result.returncode

# predict versuchen
rc = run_script("predict.py")
if rc != 0:
    print("predict.py hat nicht geklappt, versuche predict_bbox.py ...")
    rc = run_script("predict_bbox.py")
    if rc != 0:
        raise SystemExit("FairFace lief nicht sauber durch. Bitte Logs checken.")

OUTFILE = os.path.join(FAIRFACE_DIR, "test_outputs.csv")
if not os.path.exists(OUTFILE):
    raise SystemExit("test_outputs.csv fehlt – evtl. fehlen Modelle (fairface_models/dlib_models)?")

df = pd.read_csv(OUTFILE)

# spalten flexibel handhaben
if "gender" not in df.columns:
    if "gender_preds" in df.columns:
        df["gender"] = df["gender_preds"]

if "race" not in df.columns:
    if "race_preds" in df.columns:
        df["race"] = df["race_preds"]

# nur wenn race_4 da ist, sonst leer
if "race_4" in df.columns:
    cols = ["face_name_align", "race", "race_4", "gender", "age"]
else:
    cols = ["face_name_align", "race", "gender", "age"]

print(df[cols].head())

if "race" in df.columns:
    print("\nRace counts:\n", df["race"].value_counts())

if "gender" in df.columns:
    print("\nGender counts:\n", df["gender"].value_counts())
