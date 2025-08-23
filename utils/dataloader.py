# utils/dataloader.py

import os

DATA_DIR = "data"
VALID_EXTS = (".jpg", ".jpeg", ".png")

def get_account_overview():
    """liefert dict {account: bildanzahl} zurück"""
    overview = {}

    for acc in os.listdir(DATA_DIR):
        # ordner überspringen
        if acc == "analysis" or acc == ".status":
            continue

        dir_path = os.path.join(DATA_DIR, acc)
        if os.path.isdir(dir_path):
            bild_count = 0
            for f in os.listdir(dir_path):
                fname = f.lower()
                if fname.endswith(VALID_EXTS):
                    bild_count += 1
                else:
                    # ignorieren wenn keine bilddatei
                    pass

            overview[acc] = bild_count

    return overview
