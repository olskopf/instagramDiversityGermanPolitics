import base64
import os

DATA_DIR = "data"
ALLOWED_EXTS = [".jpg", ".jpeg", ".png"]

def save_uploaded_image(partei_name: str, content: str, filename: str):
    """speichert ein einzelnes hochgeladenes bild ab"""
    ziel_ordner = os.path.join(DATA_DIR, partei_name)
    os.makedirs(ziel_ordner, exist_ok=True)

    ext = os.path.splitext(filename)[1].lower()
    if ext in ALLOWED_EXTS:
        ok = True
    else:
        ok = False

    if not ok:
        return f"Format nicht erlaubt: {ext}"

    try:
        # split in header + inhalt
        if "," in content:
            header, encoded = content.split(",", 1)
        else:
            encoded = content
        decoded = base64.b64decode(encoded)

        pfad = os.path.join(ziel_ordner, filename)
        with open(pfad, "wb") as f:
            f.write(decoded)

        return f"Bild '{filename}' gespeichert"
    except Exception as e:
        return "Fehler bei '" + filename + "': " + str(e)
