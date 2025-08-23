# app.py

import dash
from dash import dcc, html, Input, Output, MATCH, ALL, State, ctx, dash_table
import dash_bootstrap_components as dbc
import os, threading, json, time, shutil
import pandas as pd
import plotly.express as px

# utils import (eigene imports)
from utils.uploader import save_uploaded_image
from utils.dataloader import get_account_overview

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.MATERIA],
    suppress_callback_exceptions=True,  # sonst probleme bei callbacks
)
app.title = "Instagram Diversity Scanner"

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------- helper funktionen ---------------- #
RACE_KEY_MAP = {
    "White": "White",
    "Black": "Black",
    "East Asian": "East Asian",
    "Southeast Asian": "Southeast Asian",
    "Indian": "Indian",
    "Middle Eastern": "Middle Eastern",
    "Latino_Hispanic": "Latino/Hispanic",
}


def load_party_summaries():
    """Liest alle summary.json Dateien und bastelt DataFrames zurück"""
    root = os.path.join(DATA_DIR, "analysis")
    rows, race_rows = [], []

    if not os.path.isdir(root):
        return pd.DataFrame(), pd.DataFrame()

    for party in sorted(os.listdir(root)):
        summary_file = os.path.join(root, party, "summary.json")
        if not os.path.isfile(summary_file):
            continue

        try:
            s = json.load(open(summary_file, encoding="utf-8"))
        except Exception:
            continue

        faces_total = int(s.get("faces_total", 0) or 0)
        total_images = int(s.get("total_images", 0) or 0)
        images_processed = int(s.get("images_processed", 0) or 0)
        by_gender = s.get("by_gender", {}) or {}
        by_race = s.get("by_race", {}) or {}
        avg_age = float(s.get("average_age", 0) or 0)

        female = int(by_gender.get("Female", 0) or 0)
        male = int(by_gender.get("Male", 0) or 0)

        if faces_total > 0:
            female_pct = 100 * female / faces_total
            male_pct = 100 * male / faces_total
        else:
            female_pct = 0
            male_pct = 0

        white = int(by_race.get("White", 0) or 0)
        poc_count = faces_total - white if faces_total else 0
        poc_pct = (100 * poc_count / faces_total) if faces_total else 0

        rows.append({
            "party": s.get("party", party),
            "total_images": total_images,
            "images_processed": images_processed,
            "faces_total": faces_total,
            "female": female,
            "male": male,
            "female_pct": round(female_pct, 1),
            "male_pct": round(male_pct, 1),
            "poc_pct": round(poc_pct, 1),
            "average_age": round(avg_age, 1),
        })

        # hauttypen aufsplitten
        for k_raw, label in RACE_KEY_MAP.items():
            cnt = int(by_race.get(k_raw, 0) or 0)
            if faces_total > 0:
                pct = 100 * cnt / faces_total
            else:
                pct = 0
            race_rows.append({
                "party": s.get("party", party),
                "race": label,
                "pct": round(pct, 1)
            })

    df = pd.DataFrame(rows).sort_values("party")
    races_long_df = pd.DataFrame(race_rows)
    return df, races_long_df


# ---------- Layout (Reiter) ---------- #
app.layout = dbc.Container([
    html.H1("Instagram Diversity Scanner", className="text-center my-4"),

    # referenzwerte für deutschland
    dcc.Store(id="ref-values",
              data={"gender_f": 54, "skin_poc": 29},
              storage_type="local"),

    dbc.Tabs([
        dbc.Tab(label="📅 Datenimport", tab_id="import"),
        dbc.Tab(label="📊 Datenübersicht", tab_id="overview"),
        dbc.Tab(label="📈 Analyse", tab_id="analysis"),
        dbc.Tab(label="📉 Datenauswertung", tab_id="insights"),
        dbc.Tab(label="⚙️ Einstellungen", tab_id="settings"),
    ], id="tabs", active_tab="import"),
    html.Div(id="tab-content", className="p-4")
])

# ---------- Reiter-inhalte ---------- #
def render_import_tab():
    return dbc.Row([
        dbc.Col([
            html.H4("Bilder hochladen für eine Partei"),
            dbc.Input(id="party-name", placeholder="Parteiname (zB SPD)", type="text"),
            dcc.Upload(
                id="upload",
                children=html.Div(["📄 Dateien hier ablegen oder klicken"]),
                style={"border": "2px dashed #888", "padding": "40px", "textAlign": "center"},
                multiple=True,
                accept=".jpg,.jpeg,.png"
            ),
            html.Div(id="upload-feedback", className="mt-2 text-muted"),
            html.Div(id="upload-status", className="mt-2 text-danger")
        ], md=6)
    ])


def render_overview_tab():
    overview = get_account_overview()
    cards = []
    for acc, count in overview.items():
        cards.append(
            dbc.Card([
                dbc.CardBody([
                    html.H5(acc, className="card-title"),
                    html.P(f"{count} Bilder"),
                    dbc.Button("Daten löschen",
                               id={"type": "delete-btn", "index": acc},
                               color="danger", size="sm")
                ])
            ], className="mb-3")
        )
    return html.Div(cards)


def party_card(party):
    analysis_dir = os.path.join("data", "analysis", party)
    os.makedirs(analysis_dir, exist_ok=True)
    summary_file = os.path.join(analysis_dir, "summary.json")
    analyzed = os.path.exists(summary_file)

    if analyzed:
        status_txt = "✅ Bereits analysiert"
        color = "green"
    else:
        status_txt = "❌ Noch nicht analysiert"
        color = "red"

    return dbc.Card([
        dbc.CardBody([
            html.H5(party, className="card-title"),
            html.P(status_txt, style={"color": color}),
            dbc.Button("Analysiere Partei",
                       id={"type": "analyze-btn", "index": party},
                       color="primary", size="sm", className="mb-2"),

            html.Div(id={"type": "progress-box", "index": party}, children=[
                dbc.Progress(id={"type": "progress-bar", "index": party},
                             value=0, striped=True, animated=True,
                             style={"height": "20px"}),
                html.Small(id={"type": "progress-text", "index": party}, className="text-muted"),
                html.Div(id={"type": "progress-preview", "index": party},
                         className="d-flex align-items-center gap-3 mt-2")
            ])
        ])
    ], className="mb-3")


def render_analysis_tab():
    cards = []
    data_dir = os.path.join("data")
    for party in sorted(os.listdir(data_dir)):
        party_dir = os.path.join(data_dir, party)
        if not os.path.isdir(party_dir): continue
        if party in ("analysis", ".status"): continue
        cards.append(party_card(party))

    return html.Div([
        html.H4("Analyse starten"),
        dbc.Button("Alle Parteien analysieren",
                   id="start-analysis-btn", color="success", className="mb-3"),
        html.Hr(),
        dcc.Interval(id="progress-poller", interval=1500, n_intervals=0),
        html.Div(cards, id="analysis-status")
    ])


def render_settings_tab():
    return html.Div([
        html.H4("Referenzwerte für Deutschland"),
        dbc.Label("Anteil Frauen (%)"),
        dcc.Slider(id="gender-f", min=0, max=100, value=54,
                   marks={i: f"{i}%" for i in range(0, 101, 10)},
                   tooltip={"always_visible": True}),
        dbc.Label("Anteil People of Color (%)", className="mt-4"),
        dcc.Slider(id="skin-poc", min=0, max=100, value=29,
                   marks={i: f"{i}%" for i in range(0, 101, 10)},
                   tooltip={"always_visible": True}),
        html.Div(id="settings-status", className="mt-3")
    ])


# --- Tab insights
def render_insights_tab(ref_values):
    df, races_long = load_party_summaries()
    if df.empty:
        return html.Div([html.P("Keine Analysen gefunden. Bitte zuerst im Tab 'Analyse' ausführen.")])

    # Kennzahlen
    columns = [
        {"name": "Partei", "id": "party"},
        {"name": "Bilder gesamt", "id": "total_images", "type": "numeric"},
        {"name": "Bilder verarbeitet", "id": "images_processed", "type": "numeric"},
        {"name": "Gesichter", "id": "faces_total", "type": "numeric"},
        {"name": "Frauen %", "id": "female_pct", "type": "numeric"},
        {"name": "PoC %", "id": "poc_pct", "type": "numeric"},
        {"name": "Ø Alter", "id": "average_age", "type": "numeric"},
    ]
    table = dash_table.DataTable(
        id="summary-table",
        columns=columns,
        data=df.to_dict("records"),
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"padding": "6px", "fontSize": 14},
        style_header={"fontWeight": "bold"}
    )

    # referenzwerte badges
    ref_gender = (ref_values or {}).get("gender_f", 54)
    ref_poc = (ref_values or {}).get("skin_poc", 29)
    ref_badges = dbc.Badge(f"Referenz Frauen: {ref_gender}%", color="primary", className="me-2")
    ref_badges2 = dbc.Badge(f"Referenz PoC: {ref_poc}%", color="info")

    # Diagramme
    fig_gender = px.bar(df, x="party", y="female_pct", text="female_pct",
                        labels={"party": "Partei", "female_pct": "Frauen in %"},
                        title="Frauenanteil pro Partei")
    fig_gender.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
    fig_gender.add_hline(y=ref_gender, line_dash="dash",
                         annotation_text=f"Referenz {ref_gender}%",
                         annotation_position="top left")

    fig_poc = px.bar(df, x="party", y="poc_pct", text="poc_pct",
                     labels={"party": "Partei", "poc_pct": "PoC in %"},
                     title="Anteil People of Color pro Partei")
    fig_poc.update_traces(texttemplate="%{text:.1f}%", textposition="outside", cliponaxis=False)
    fig_poc.add_hline(y=ref_poc, line_dash="dash",
                      annotation_text=f"Referenz {ref_poc}%",
                      annotation_position="top left")

    fig_age = px.bar(df, x="party", y="average_age",
                     labels={"party": "Partei", "average_age": "Ø Alter"},
                     title="Durchschnittsalter")

    fig_corr = px.scatter(df, x="female_pct", y="poc_pct",
                          size="faces_total", color="party", text="party",
                          labels={"female_pct": "Frauen %", "poc_pct": "PoC %"},
                          title="Frauen% vs. PoC%")
    fig_corr.update_traces(textposition="top center")

    if not races_long.empty:
        fig_races = px.bar(races_long, x="party", y="pct", color="race", barmode="stack",
                           labels={"party": "Partei", "pct": "%", "race": "Hauttyp"},
                           title="Hauttypen-Verteilung pro Partei")
    else:
        fig_races = None

    return html.Div([
        html.H4("Datenauswertung"),
        html.Div([ref_badges, ref_badges2], className="mb-3"),
        html.H5("Übersicht aller Summaries"),
        table, html.Hr(),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_gender), md=6),
            dbc.Col(dcc.Graph(figure=fig_poc), md=6)
        ]),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig_age), md=6),
            dbc.Col(dcc.Graph(figure=fig_corr), md=6)
        ]),
        dcc.Graph(figure=fig_races) if fig_races else html.Div()
    ], id="insights-content")


# ---------- Callback zum Rendern der Tabs ---------- #
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
    Input("ref-values", "data"),
)
def render_tab_content(active_tab, ref_values):
    if active_tab == "import":
        return render_import_tab()
    elif active_tab == "overview":
        return render_overview_tab()
    elif active_tab == "analysis":
        return render_analysis_tab()
    elif active_tab == "settings":
        return render_settings_tab()
    elif active_tab == "insights":
        return render_insights_tab(ref_values)
    return html.P("Fehler: Unbekannter Tab")


# ---------- Callback zum Upload von Bildern ---------- #
@app.callback(
    Output("upload-status", "children"),
    Output("upload-feedback", "children"),
    Input("upload", "contents"),
    State("upload", "filename"),
    State("party-name", "value"),
    prevent_initial_call=True
)
def handle_folder_upload(contents, filenames, party):
    if not contents or not filenames or not party:
        return "", "❌ Ungültiger Upload."
    try:
        saved = 0
        skipped = 0
        for content, filename in zip(contents, filenames):
            result = save_uploaded_image(party, content, filename)
            if result.startswith("✅"):
                saved += 1
            else:
                skipped += 1
        return "", html.Div([
            html.Span("✅ Upload abgeschlossen: "),
            html.Span(f"{saved} Bilder gespeichert, {skipped} Dateien übersprungen.", style={"color": "green"})
        ])
    except Exception as e:
        return "", f"❌ Fehler bei Verarbeitung: {str(e)}"


# ---------- Callback zum Löschen von Datensätzen ---------- #
@app.callback(
    Output("tab-content", "children", allow_duplicate=True),
    Input({"type": "delete-btn", "index": dash.ALL}, "n_clicks"),
    State("tabs", "active_tab"),
    prevent_initial_call=True
)
def delete_dataset(n_clicks_list, active_tab):
    if not any(n_clicks_list):
        return dash.no_update
    triggered = ctx.triggered_id
    if triggered and "index" in triggered:
        dir_to_remove = os.path.join(DATA_DIR, triggered["index"])
        if os.path.isdir(dir_to_remove):
            shutil.rmtree(dir_to_remove)
        # auch Analyseordner der Partei löschen
        ana_dir = os.path.join(DATA_DIR, "analysis", triggered["index"])
        if os.path.isdir(ana_dir):
            shutil.rmtree(ana_dir)
    # Nach dem Löschen ggf. Inhalt des aktuellen Tabs neu zeichnen
    if active_tab == "insights":
        return render_insights_tab(dash.get_app().layout.children[1].data)
    return render_tab_content(active_tab, None)


# ---------- Callback: Alle analysieren ---------- #
@app.callback(
    Output("analysis-status", "children"),
    Input("start-analysis-btn", "n_clicks"),
    prevent_initial_call=True
)
def start_all_analyses(n):
    data_dir = os.path.join("data")
    for party in os.listdir(data_dir):
        party_dir = os.path.join(data_dir, party)
        if os.path.isdir(party_dir) and party not in ("analysis", ".status"):
            start_background_analysis(party)
    # re-render, damit Cards da sind
    return render_analysis_tab().children


# ---------- Callback: Einzelne Analyse-Buttons ---------- #
@app.callback(
    Output("analysis-status", "children", allow_duplicate=True),
    Input({"type": "analyze-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True
)
def analyze_single_party(n_clicks_list):
    triggered = ctx.triggered_id
    if triggered and "index" in triggered:
        party = triggered["index"]
        start_background_analysis(party)
    return render_analysis_tab().children


# ---------- Progress-Updates inklus Vorschau ---------- #
@app.callback(
    Output({"type": "progress-bar", "index": MATCH}, "value"),
    Output({"type": "progress-bar", "index": MATCH}, "label"),
    Output({"type": "progress-text", "index": MATCH}, "children"),
    Output({"type": "progress-preview", "index": MATCH}, "children"),
    Input("progress-poller", "n_intervals"),
    State({"type": "progress-bar", "index": MATCH}, "id")
)
def update_progress(_n, comp_id):
    party = comp_id["index"]
    progress_path = os.path.join("data", "analysis", party, "progress.json")
    if not os.path.exists(progress_path):
        return 0, "", "", ""
    try:
        p = json.load(open(progress_path, encoding="utf-8"))
    except Exception:
        return 0, "", "", ""

    total = max(1, int(p.get("total", 1)))
    done = int(p.get("done", 0))
    percent = min(100, round(100 * done / total))
    status = p.get("status", "running")
    msg = p.get("message", "")

    now = int(time.time())
    started = int(p.get("started_at", now))
    elapsed = now - started
    eta_secs = p.get("eta_secs")
    eta_str = f" | ETA: {eta_secs//60}m {eta_secs%60}s" if isinstance(eta_secs, int) else ""

    label = "100%" if status == "done" else f"{percent}%"
    if status == "done":
        percent = 100

    text = f"{done}/{total} Bilder • {status.upper()}: {msg} | Laufzeit: {elapsed//60}m {elapsed%60}s{eta_str}"
    if status == "error":
        text = f"❌ Fehler: {msg}"

    # Vorschau 
    prev_children = ""
    if p.get("current_preview"):
        prev_children = html.Div([
            html.Img(src=p["current_preview"], style={"maxWidth": "220px", "maxHeight": "220px"}),
            html.Div([
                html.Code(p.get("current_image", "")),
                html.Br(),
                html.Small(p.get("current_result", ""), className="text-muted")
            ])
        ], className="d-flex gap-3")

    return percent, label, text, prev_children


# ---------- Einstellungen speichern ---------- #
@app.callback(
    Output("settings-status", "children"),
    Output("ref-values", "data"),
    Input("gender-f", "value"),
    Input("skin-poc", "value"),
    prevent_initial_call=False,
)
def save_settings(gender_f, skin_poc):
    data = {"gender_f": int(gender_f or 0), "skin_poc": int(skin_poc or 0)}
    status = html.Span([
        "Gespeichert: ",
        html.B(f"Frauen {data['gender_f']}%"), " | ", html.B(f"PoC {data['skin_poc']}%")
    ], className="text-success")
    return status, data


# --- Hintergrundjobs
ACTIVE_JOBS = {}

def start_background_analysis(party):
    if party in ACTIVE_JOBS and ACTIVE_JOBS[party].is_alive():
        return
    party_dir = os.path.join(DATA_DIR, party)
    if not os.path.isdir(party_dir): return
    from face_analysis.analyze_images import analyze_party_images
    t = threading.Thread(target=analyze_party_images, args=(party_dir,), daemon=True)
    t.start()
    ACTIVE_JOBS[party] = t


if __name__ == "__main__":
    app.run(debug=True)