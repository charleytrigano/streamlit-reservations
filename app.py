# app.py — Villa Tobias (AMÉLIORÉ ET COMPLÉTÉ)
# Améliorations : Robustesse, UI/UX, modularité, backups, logs, envoi SMS/email, charts interactifs, détection conflits, etc.
# Complétions : Login basique, export CSV, SMS batch, historique actions, tooltips calendrier.

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
import shutil
from urllib.parse import quote
import colorsys
import altair as alt  # Pour charts interactifs
from twilio.rest import Client  # Pour SMS (installez twilio)
import smtplib  # Pour emails
from email.mime.text import MIMEText

# Constantes
FICHIER = "reservations.xlsx"
PALETTE_SHEET = "Plateformes"
DATA_SHEET = "Sheet1"
LOG_SHEET = "Logs"  # Nouvelle feuille pour historique
BACKUP_DIR = "backups"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb": "#e74c3c",
    "Autre": "#f59e0b",
}

BASE_COLS = [
    "paye", "nom_client", "sms_envoye", "email_envoye",
    "plateforme", "telephone", "email",
    "date_arrivee", "date_depart", "nuitees",
    "prix_brut", "commissions", "frais_cb", "prix_net",
    "menage", "taxes_sejour", "base",
    "charges", "%", "AAAA", "MM", "ical_uid"
]

# ============================== PAGE CONFIG ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide", initial_sidebar_state="expanded")

# ============================== SESSION KEYS ==============================
if "palette" not in st.session_state:
    st.session_state.palette = DEFAULT_PALETTE.copy()
if "uploader_key_restore" not in st.session_state:
    st.session_state.uploader_key_restore = 0
if "did_clear_cache" not in st.session_state:
    st.session_state.did_clear_cache = False
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "logs" not in st.session_state:
    st.session_state.logs = pd.DataFrame(columns=["timestamp", "action", "details"])

# ============================== LOGIN BASIQUE ==============================
def login():
    st.sidebar.title("🔐 Connexion")
    username = st.sidebar.text_input("Utilisateur")
    password = st.sidebar.text_input("Mot de passe", type="password")
    if st.sidebar.button("Se connecter"):
        # Remplacez par vos credentials réels (hardcodé pour simplicité, utilisez secrets.toml en prod)
        if username == "admin" and password == "password":
            st.session_state.logged_in = True
            st.sidebar.success("Connecté !")
            st.rerun()
        else:
            st.sidebar.error("Identifiants incorrects.")

if not st.session_state.logged_in:
    login()
    st.stop()  # Arrête l'exécution si non connecté

# ============================== PALETTE (PLATEFORMES) ==============================
def _clean_hex(c: str) -> str:
    if not isinstance(c, str):
        return "#999999"
    c = c.strip().upper()
    if not c.startswith("#"):
        c = "#" + c
    if len(c) not in [4, 7] or not all(x in "0123456789ABCDEF" for x in c[1:]):
        return "#999999"
    return c

def get_palette() -> dict:
    pal = st.session_state.palette
    return {k.strip(): _clean_hex(v) for k, v in pal.items() if k}

def set_palette(pal: dict):
    st.session_state.palette = pal

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

# ============================== OUTILS ==============================
def to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def normalize_tel(x):
    if pd.isna(x) or x is None:
        return ""
    s = str(x).strip().replace(" ", "").replace("+", "").replace("-", "")
    if s.endswith(".0"):
        s = s[:-2]
    if not s.startswith("33") and s.startswith("0"):
        s = "33" + s[1:]
    return s

def normalize_email(x):
    if pd.isna(x) or x is None:
        return ""
    return str(x).strip().lower()

def log_action(action: str, details: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_log = pd.DataFrame({"timestamp": [now], "action": [action], "details": [details]})
    st.session_state.logs = pd.concat([st.session_state.logs, new_log], ignore_index=True)

# ============================== SCHEMA & CALCULS ==============================
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        df = pd.DataFrame(columns=BASE_COLS)
    df = df.copy()
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    df["email_envoye"] = df["email_envoye"].fillna(False).astype(bool)
    df["date_arrivee"] = df["date_arrivee"].apply(to_date_only)
    df["date_depart"] = df["date_depart"].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    df["email"] = df["email"].apply(normalize_email)

    numeric_cols = ["prix_brut", "commissions", "frais_cb", "prix_net", "menage", "taxes_sejour", "base", "charges", "%", "nuitees"]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df["nuitees"] = df.apply(lambda r: (r["date_depart"] - r["date_arrivee"]).days if isinstance(r["date_arrivee"], date) and isinstance(r["date_depart"], date) else 0, axis=1)
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
    df["MM"] = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["nom_client"] = df["nom_client"].fillna("")
    df["ical_uid"] = df["ical_uid"].fillna("")

    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"] = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0).clip(lower=0)

    for c in numeric_cols[:-1]:  # Exclut nuitees
        df[c] = df[c].round(2)

    ordered_cols = [c for c in BASE_COLS if c in df.columns]
    rest_cols = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + rest_cols]

def check_conflicts(df: pd.DataFrame, new_start: date, new_end: date, exclude_index=None):
    for idx, row in df.iterrows():
        if exclude_index is not None and idx == exclude_index:
            continue
        start = row["date_arrivee"]
        end = row["date_depart"]
        if isinstance(start, date) and isinstance(end, date):
            if max(start, new_start) < min(end, new_end):
                return True, f"Conflit avec {row['nom_client']} ({start} à {end})"
    return False, ""

# ============================== EXCEL I/O ==============================
@st.cache_data(show_spinner=False)
def _read_workbook(path: str, mtime: float):
    try:
        with pd.ExcelFile(path, engine="openpyxl") as xf:
            df = pd.read_excel(xf, sheet_name=DATA_SHEET, engine="openpyxl",
                              converters={"telephone": normalize_tel, "email": normalize_email}) if DATA_SHEET in xf.sheet_names else pd.read_excel(xf, sheet_name=xf.sheet_names[0])
            df = ensure_schema(df)

            pal = DEFAULT_PALETTE.copy()
            if PALETTE_SHEET in xf.sheet_names:
                pf_df = pd.read_excel(xf, sheet_name=PALETTE_SHEET, engine="openpyxl")
                if {"plateforme", "couleur"}.issubset(set(pf_df.columns)):
                    for _, r in pf_df.iterrows():
                        name = str(r["plateforme"]).strip()
                        color = _clean_hex(str(r["couleur"]))
                        if name:
                            pal[name] = color

            logs = pd.DataFrame(columns=["timestamp", "action", "details"])
            if LOG_SHEET in xf.sheet_names:
                logs = pd.read_excel(xf, sheet_name=LOG_SHEET, engine="openpyxl")
            return df, pal, logs
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame()), DEFAULT_PALETTE.copy(), pd.DataFrame(columns=["timestamp", "action", "details"])

def charger_donnees():
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame()), get_palette(), st.session_state.logs
    mtime = os.path.getmtime(FICHIER)
    df, pal, logs = _read_workbook(FICHIER, mtime)
    set_palette(pal)
    st.session_state.logs = logs
    return df, pal, logs

def backup_file():
    if not os.path.exists(FICHIER):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"reservations_{timestamp}.xlsx")
    shutil.copy(FICHIER, backup_path)
    log_action("Backup", f"Sauvegarde créée : {backup_path}")

def _force_tel_text_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name)
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
    except Exception:
        pass

def sauvegarder_donnees(df: pd.DataFrame, palette: dict = None, logs: pd.DataFrame = None):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)

    backup_file()
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name=DATA_SHEET)
            _force_tel_text_openpyxl(w, out, DATA_SHEET)
            if palette is not None:
                p = pd.DataFrame([{"plateforme": k, "couleur": v} for k, v in sorted(palette.items())])
                p.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
            if logs is not None:
                logs.to_excel(w, index=False, sheet_name=LOG_SHEET)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
        log_action("Sauvegarde", f"Fichier {FICHIER} mis à jour")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

# ============================== ICS EXPORT ==============================
def _ics_escape(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def _fmt_date_ics(d: date) -> str:
    return d.strftime("%Y%m%d")

def _dtstamp_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _stable_uid(nom_client, plateforme, d1, d2, tel, salt="v1"):
    base = f"{nom_client}|{plateforme}|{d1}|{d2}|{tel}|{salt}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return f"vt-{h}@villatobias"

def df_to_ics(df: pd.DataFrame, cal_name: str = "Villa Tobias – Réservations") -> str:
    df = ensure_schema(df)
    if df.empty:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Villa Tobias//Reservations//FR",
            f"X-WR-CALNAME:{_ics_escape(cal_name)}",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "END:VCALENDAR",
        ]
        return "\r\n".join(lines) + "\r\n"

    core, _ = split_totals(df)
    core = sort_core(core)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        f"X-WR-CALNAME:{_ics_escape(cal_name)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        plateforme = str(row.get("plateforme") or "").strip()
        nom_client = str(row.get("nom_client") or "").strip()
        tel = str(row.get("telephone") or "").strip()
        brut = float(row.get("prix_brut") or 0.0)
        net = float(row.get("prix_net") or 0.0)
        nuitees = int(row.get("nuitees") or 0)
        summary = " - ".join([x for x in [plateforme, nom_client, tel] if x])
        desc = (
            f"Plateforme: {plateforme}\n"
            f"Client: {nom_client}\n"
            f"Téléphone: {tel}\n"
            f"Arrivée: {format_date_str(d1)}\n"
            f"Départ: {format_date_str(d2)}\n"
            f"Nuitées: {nuitees}\n"
            f"Brut: {brut:.2f} €\n"
            f"Net: {net:.2f} €"
        )
        uid_existing = str(row.get("ical_uid") or "").strip()
        uid = uid_existing if uid_existing else _stable_uid(nom_client, plateforme, d1, d2, tel)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(uid)}",
            f"DTSTAMP:{_dtstamp_utc_now()}",
            f"DTSTART;VALUE=DATE:{_fmt_date_ics(d1)}",
            f"DTEND;VALUE=DATE:{_fmt_date_ics(d2)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

# ============================== SMS & EMAIL ==============================
def sms_message_arrivee(row: pd.Series) -> str:
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    d1s = format_date_str(d1)
    d2s = format_date_str(d2)
    nuitees = int(row.get("nuitees") or 0)
    plateforme = str(row.get("plateforme") or "")
    nom = str(row.get("nom_client") or "")
    tel = normalize_tel(row.get("telephone"))
    return (
        f"VILLA TOBIAS\n"
        f"Plateforme: {plateforme}\n"
        f"Arrivée: {d1s} Départ: {d2s} Nuitées: {nuitees}\n\n"
        f"Bonjour {nom},\n"
        f"Nous sommes ravis de vous accueillir bientôt à Nice. Merci de nous indiquer votre heure d'arrivée.\n"
        f"Place de parking disponible. Check-in: 14h, Check-out: 11h.\n"
        f"Consignes à bagages disponibles à Nice.\n"
        f"Bon voyage ! Annick & Charley\n"
        f"Fiche d'arrivée: https://urlr.me/Xu7Sq3"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n"
        f"Merci d'avoir choisi Villa Tobias. Nous espérons que votre séjour fut agréable.\n"
        f"Revenez quand vous voulez, notre porte est toujours ouverte !\n"
        f"Annick & Charley"
    )

def send_sms(tel: str, body: str):
    try:
        client = Client(st.secrets["TWILIO_SID"], st.secrets["TWILIO_AUTH_TOKEN"])
        client.messages.create(
            body=body,
            from_=st.secrets["TWILIO_PHONE"],
            to=f"+{tel}"
        )
        return True, "SMS envoyé"
    except Exception as e:
        return False, f"Erreur SMS: {e}"

def send_email(email: str, subject: str, body: str):
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = st.secrets["EMAIL_SENDER"]
        msg["To"] = email
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(st.secrets["EMAIL_SENDER"], st.secrets["EMAIL_PASSWORD"])
            server.sendmail(st.secrets["EMAIL_SENDER"], email, msg.as_string())
        return True, "Email envoyé"
    except Exception as e:
        return False, f"Erreur Email: {e}"

# ============================== UI HELPERS ==============================
def kpi_chips(df: pd.DataFrame):
    core, _ = split_totals(df)
    if core.empty:
        return
    b = core["prix_brut"].sum()
    total_comm = core["commissions"].sum()
    total_cb = core["frais_cb"].sum()
    ch = total_comm + total_cb
    n = core["prix_net"].sum()
    base = core["base"].sum()
    nuits = core["nuitees"].sum()
    pct = (ch / b * 100) if b else 0
    pm_nuit = (b / nuits) if nuits else 0
    html = f"""
    <style>
    .chips-wrap {{ display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px 0; }}
    .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12); border: 1px solid rgba(127,127,127,0.25); font-size:0.9rem; }}
    .chip b {{ display:block; margin-bottom:3px; font-size:0.85rem; opacity:0.8; }}
    .chip .v {{ font-weight:600; }}
    </style>
    <div class="chips-wrap">
      <div class="chip"><b>Total Brut</b><div class="v">{b:,.2f} €</div></div>
      <div class="chip"><b>Total Net</b><div class="v">{n:,.2f} €</div></div>
      <div class="chip"><b>Total Base</b><div class="v">{base:,.2f} €</div></div>
      <div class="chip"><b>Total Charges</b><div class="v">{ch:,.2f} €</div></div>
      <div class="chip"><b>Nuitées</b><div class="v">{int(nuits)}</div></div>
      <div class="chip"><b>Commission moy.</b><div class="v">{pct:.2f} %</div></div>
      <div class="chip"><b>Prix moyen/nuit</b><div class="v">{pm_nuit:,.2f} €</div></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def search_box(df: pd.DataFrame) -> pd.DataFrame:
    st.markdown("### Recherche avancée")
    c1, c2, c3 = st.columns(3)
    q = c1.text_input("🔎 Nom/Plateforme/Téléphone", "")
    annee = c2.selectbox("Année", ["Toutes"] + sorted(df["AAAA"].dropna().unique().astype(int).tolist()), index=0)
    mois = c3.selectbox("Mois", ["Tous"] + [f"{i:02d}" for i in range(1, 13)], index=0)

    data = df.copy()
    if annee != "Toutes":
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]
    if q:
        ql = q.strip().lower()
        data = data[
            data["nom_client"].str.lower().str.contains(ql, na=False) |
            data["plateforme"].str.lower().str.contains(ql, na=False) |
            data["telephone"].str.contains(ql, na=False)
        ]
    return data

# ============================== VUES ==============================
def vue_reservations(df: pd.DataFrame):
    palette = get_palette()
    st.title("📋 Réservations")

    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)

    st.markdown("### Plateformes")
    badges = " &nbsp;&nbsp;".join([platform_badge(pf, palette) for pf in sorted(palette.keys())])
    st.markdown(badges, unsafe_allow_html=True)

    df = ensure_schema(df)
    if filtre_paye == "Payé":
        df = df[df["paye"] == True].copy()
    elif filtre_paye == "Non payé":
        df = df[df["paye"] == False].copy()

    if show_kpi:
        kpi_chips(df)
    if enable_search:
        df = search_box(df)

    core, totals = split_totals(df)
    core = sort_core(core)

    core_edit = core.copy()
    core_edit["__rowid"] = core_edit.index
    core_edit["date_arrivee"] = core_edit["date_arrivee"].apply(format_date_str)
    core_edit["date_depart"] = core_edit["date_depart"].apply(format_date_str)

    cols_order = [
        "paye", "nom_client", "sms_envoye", "email_envoye", "plateforme", "telephone", "email",
        "date_arrivee", "date_depart", "nuitees",
        "prix_brut", "commissions", "frais_cb", "prix_net",
        "menage", "taxes_sejour", "base", "charges", "%", "AAAA", "MM", "__rowid"
    ]
    cols_show = [c for c in cols_order if c in core_edit.columns]

    edited = st.data_editor(
        core_edit[cols_show],
        use_container_width=True,
        hide_index=True,
        column_config={
            "paye": st.column_config.CheckboxColumn("Payé"),
            "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
            "email_envoye": st.column_config.CheckboxColumn("Email envoyé"),
            "__rowid": st.column_config.Column("id", help="Interne", disabled=True, width="small"),
            "date_arrivee": st.column_config.TextColumn("Arrivée", disabled=True),
            "date_depart": st.column_config.TextColumn("Départ", disabled=True),
        }
    )

    c1, _ = st.columns([1, 3])
    if c1.button("💾 Enregistrer les cases cochées"):
        for _, r in edited.iterrows():
            ridx = int(r["__rowid"])
            core.at[ridx, "paye"] = bool(r.get("paye", False))
            core.at[ridx, "sms_envoye"] = bool(r.get("sms_envoye", False))
            core.at[ridx, "email_envoye"] = bool(r.get("email_envoye", False))
        new_df = pd.concat([core, totals], ignore_index=False).reset_index(drop=True)
        sauvegarder_donnees(new_df, get_palette(), st.session_state.logs)
        st.success("✅ Statuts mis à jour.")
        log_action("Mise à jour", "Statuts Payé/SMS/Email modifiés")
        st.rerun()

    if not totals.empty:
        show_tot = totals.copy()
        for c in ["date_arrivee", "date_depart"]:
            show_tot[c] = show_tot[c].apply(format_date_str)
        st.caption("Lignes de totaux (non éditables) :")
        cols_tot = [c for c in cols_order if c in show_tot.columns and c != "__rowid"]
        st.dataframe(show_tot[cols_tot], use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    st.caption("Saisie compacte avec validation")
    palette = get_palette()

    def inline_input(label, widget_fn, key=None, **widget_kwargs):
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"**{label}**")
        with col2:
            return widget_fn(label, key=key, label_visibility="collapsed", **widget_kwargs)

    paye = inline_input("Payé", st.checkbox, key="add_paye", value=False)
    nom = inline_input("Nom", st.text_input, key="add_nom", value="", placeholder="Nom du client")
    sms_envoye = inline_input("SMS envoyé", st.checkbox, key="add_sms", value=False)
    email_envoye = inline_input("Email envoyé", st.checkbox, key="add_email", value=False)
    tel = inline_input("Téléphone (+33...)", st.text_input, key="add_tel", value="", placeholder="+33612345678")
    email = inline_input("Email", st.text_input, key="add_email_input", value="", placeholder="client@example.com")
    pf_options = sorted(palette.keys())
    plateforme = inline_input("Plateforme", st.selectbox, key="add_pf", options=pf_options, index=pf_options.index("Booking") if "Booking" in pf_options else 0)

    arrivee = inline_input("Arrivée", st.date_input, key="add_arrivee", value=date.today())
    min_dep = arrivee + timedelta(days=1)
    depart = inline_input("Départ", st.date_input, key="add_depart", value=min_dep, min_value=min_dep)

    brut = inline_input("Prix brut (€)", st.number_input, key="add_brut", min_value=0.0, step=1.0, format="%.2f")
    commissions = inline_input("Commissions (€)", st.number_input, key="add_comm", min_value=0.0, step=1.0, format="%.2f")
    frais_cb = inline_input("Frais CB (€)", st.number_input, key="add_cb", min_value=0.0, step=1.0, format="%.2f")

    net_calc = max(float(brut) - float(commissions) - float(frais_cb), 0.0)
    inline_input("Prix net (calculé)", st.number_input, key="add_net", value=round(net_calc, 2), step=0.01, format="%.2f", disabled=True)

    menage = inline_input("Ménage (€)", st.number_input, key="add_menage", min_value=0.0, step=1.0, format="%.2f")
    taxes = inline_input("Taxes séjour (€)", st.number_input, key="add_taxes", min_value=0.0, step=1.0, format="%.2f")

    base_calc = max(net_calc - float(menage) - float(taxes), 0.0)
    charges_calc = max(float(brut) - net_calc, 0.0)
    pct_calc = (charges_calc / float(brut) * 100) if float(brut) > 0 else 0.0

    inline_input("Base (calculée)", st.number_input, key="add_base", value=round(base_calc, 2), step=0.01, format="%.2f", disabled=True)
    inline_input("Commission (%)", st.number_input, key="add_pct", value=round(pct_calc, 2), step=0.01, format="%.2f", disabled=True)

    if st.button("Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        conflict, conflict_msg = check_conflicts(df, arrivee, depart)
        if conflict:
            st.error(f"Conflit de réservation : {conflict_msg}")
            return
        ligne = {
            "paye": bool(paye),
            "nom_client": nom.strip(),
            "sms_envoye": bool(sms_envoye),
            "email_envoye": bool(email_envoye),
            "plateforme": plateforme,
            "telephone": normalize_tel(tel),
            "email": normalize_email(email),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": float(brut),
            "commissions": float(commissions),
            "frais_cb": float(frais_cb),
            "prix_net": round(net_calc, 2),
            "menage": float(menage),
            "taxes_sejour": float(taxes),
            "base": round(base_calc, 2),
            "charges": round(charges_calc, 2),
            "%": round(pct_calc, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month,
            "ical_uid": ""
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        sauvegarder_donnees(df2, get_palette(), st.session_state.logs)
        st.success("✅ Réservation enregistrée")
        log_action("Ajout", f"Réservation pour {nom} ({arrivee} à {depart})")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation.")
        return

    df["identifiant"] = df["nom_client"].astype(str) + " | " + df["date_arrivee"].apply(format_date_str)
    choix = st.selectbox("Choisir une réservation", df["identifiant"])
    idx = df.index[df["identifiant"] == choix]
    if len(idx) == 0:
        st.warning("Sélection invalide.")
        return
    i = idx[0]

    t0, t1, t2, t3 = st.columns(4)
    paye = t0.checkbox("Payé", value=bool(df.at[i, "paye"]))
    sms_envoye = t1.checkbox("SMS envoyé", value=bool(df.at[i, "sms_envoye"]))
    email_envoye = t2.checkbox("Email envoyé", value=bool(df.at[i, "email_envoye"]))
    nom = t3.text_input("Nom", df.at[i, "nom_client"])

    col = st.columns(3)
    tel = col[0].text_input("Téléphone", normalize_tel(df.at[i, "telephone"]))
    email = col[1].text_input("Email", normalize_email(df.at[i, "email"]))
    palette = get_palette()
    options_pf = sorted(palette.keys())
    cur_pf = df.at[i, "plateforme"]
    pf_index = options_pf.index(cur_pf) if cur_pf in options_pf else 0
    plateforme = col[2].selectbox("Plateforme", options_pf, index=pf_index)

    arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"] if isinstance(df.at[i, "date_arrivee"], date) else date.today())
    depart = st.date_input("Départ", df.at[i, "date_depart"] if isinstance(df.at[i, "date_depart"], date) else arrivee + timedelta(days=1), min_value=arrivee + timedelta(days=1))

    c1, c2, c3 = st.columns(3)
    brut = c1.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i, "prix_brut"]), step=1.0, format="%.2f")
    commissions = c2.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i, "commissions"]), step=1.0, format="%.2f")
    frais_cb = c3.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i, "frais_cb"]), step=1.0, format="%.2f")

    net_calc = max(brut - commissions - frais_cb, 0.0)
    d1, d2, d3 = st.columns(3)
    menage = d1.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i, "menage"]), step=1.0, format="%.2f")
    taxes = d2.number_input("Taxes séjour (€)", min_value=0.0, value=float(df.at[i, "taxes_sejour"]), step=1.0, format="%.2f")
    base_calc = max(net_calc - menage - taxes, 0.0)

    charges_calc = max(brut - net_calc, 0.0)
    pct_calc = (charges_calc / brut * 100) if brut > 0 else 0.0
    d3.markdown(f"**Prix net (calculé)**: {net_calc:.2f} €  \n**Base (calculée)**: {base_calc:.2f} €  \n**%**: {pct_calc:.2f}")

    c_save, c_del = st.columns(2)
    if c_save.button("💾 Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        conflict, conflict_msg = check_conflicts(df, arrivee, depart, exclude_index=i)
        if conflict:
            st.error(f"Conflit de réservation : {conflict_msg}")
            return
        df.at[i, "paye"] = bool(paye)
        df.at[i, "nom_client"] = nom.strip()
        df.at[i, "sms_envoye"] = bool(sms_envoye)
        df.at[i, "email_envoye"] = bool(email_envoye)
        df.at[i, "plateforme"] = plateforme
        df.at[i, "telephone"] = normalize_tel(tel)
        df.at[i, "email"] = normalize_email(email)
        df.at[i, "date_arrivee"] = arrivee
        df.at[i, "date_depart"] = depart
        df.at[i, "prix_brut"] = float(brut)
        df.at[i, "commissions"] = float(commissions)
        df.at[i, "frais_cb"] = float(frais_cb)
        df.at[i, "prix_net"] = round(net_calc, 2)
        df.at[i, "menage"] = float(menage)
        df.at[i, "taxes_sejour"] = float(taxes)
        df.at[i, "base"] = round(base_calc, 2)
        df.at[i, "charges"] = round(charges_calc, 2)
        df.at[i, "%"] = round(pct_calc, 2)
        df.at[i, "nuitees"] = (depart - arrivee).days
        df.at[i, "AAAA"] = arrivee.year
        df.at[i, "MM"] = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df, get_palette(), st.session_state.logs)
        st.success("✅ Modifié")
        log_action("Modification", f"Réservation pour {nom} ({arrivee} à {depart})")
        st.rerun()

    if c_del.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2, get_palette(), st.session_state.logs)
        st.warning("Supprimé.")
        log_action("Suppression", f"Réservation pour {df.at[i, 'nom_client']} ({df.at[i, 'date_arrivee']})")
        st.rerun()

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier - VILLA TOBIAS")
    palette = get_palette()
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    cols = st.columns(2)
    mois_nom = cols[0].selectbox("Mois", list(calendar.month_name)[1:], index=date.today().month-1)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = cols[1].selectbox("Année", annees, index=len(annees)-1) if annees else date.today().year

    m = list(calendar.month_name).index(mois_nom)
    monthcal = calendar.monthcalendar(annee, m)

    planning = {}
    nb_jours = calendar.monthrange(annee, m)[1]
    for j in range(1, nb_jours+1):
        planning[date(annee, m, j)] = []

    for _, row in df.iterrows():
        d1 = row["date_arrivee"]
        d2 = row["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        pf = str(row["plateforme"] or "Autre")
        nom = str(row["nom_client"] or "")
        tel = str(row["telephone"] or "")
        cursor = d1
        while cursor < d2:
            if cursor.month == m and cursor.year == annee:
                planning[cursor].append((pf, nom, tel))
            cursor += timedelta(days=1)

    st.markdown("""
    <style>
    .cal-wrap { overflow-x:auto; }
    table.cal { border-collapse: collapse; width:100%; table-layout: fixed; }
    table.cal th, table.cal td { border: 1px solid rgba(127,127,127,0.35); vertical-align: top; padding: 6px; }
    table.cal th { text-align:center; font-weight:600; }
    .daynum { font-weight:700; margin-bottom:4px; opacity:0.85; }
    .bar { border-radius:6px; padding:4px 6px; margin:4px 0; font-size:0.85rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; cursor:pointer; }
    .bar:hover { filter: brightness(1.2); }
    </style>
    """, unsafe_allow_html=True)

    headers = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    html = ['<div class="cal-wrap"><table class="cal">']
    html.append("<thead><tr>" + "".join([f"<th>{h}</th>" for h in headers]) + "</tr></thead><tbody>")

    for semaine in monthcal:
        html.append("<tr>")
        for jour in semaine:
            if jour == 0:
                html.append('<td style="background:transparent;"></td>')
                continue
            d = date(annee, m, jour)
            items = planning.get(d, [])
            cell = [f'<div class="daynum">{jour}</div>']
            for pf, nom, tel in items:
                base = palette.get(pf, "#999999")
                fg = "#000000" if colorsys.rgb_to_hls(*[int(base.lstrip("#")[i:i+2], 16)/255 for i in (0, 2, 4)])[1] > 0.6 else "#ffffff"
                cell.append(f'<div class="bar" style="background:{base};color:{fg};" title="{nom} ({pf}, {tel})">{nom}</div>')
            html.append(f"<td>{''.join(cell)}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div>")

    st.markdown("".join(html), unsafe_allow_html=True)

    st.caption("Légende plateformes :")
    leg = " • ".join([platform_badge(pf, palette) for pf in sorted(palette.keys())])
    st.markdown(leg, unsafe_allow_html=True)

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport - VILLA TOBIAS")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.info("Aucune année disponible.")
        return

    c1, c2, c3 = st.columns(3)
    annee = c1.selectbox("Année", annees, index=len(annees)-1, key="rapport_annee")
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = c2.selectbox("Plateforme", pf_opt, key="rapport_pf")
    mois_opt = ["Tous"] + [f"{i:02d}" for i in range(1, 13)]
    mois_label = c3.selectbox("Mois", mois_opt, key="rapport_mois")

    data = df[df["AAAA"] == int(annee)].copy()
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]
    if mois_label != "Tous":
        data = data[data["MM"] == int(mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    detail = data.copy()
    for c in ["date_arrivee", "date_depart"]:
        detail[c] = detail[c].apply(format_date_str)
    detail = detail.sort_values(by=["date_arrivee", "nom_client"], na_position="last").reset_index(drop=True)

    cols_detail = [
        "paye", "nom_client", "sms_envoye", "email_envoye", "plateforme", "telephone", "email",
        "date_arrivee", "date_depart", "nuitees",
        "prix_brut", "commissions", "frais_cb", "prix_net", "menage", "taxes_sejour", "base", "charges", "%"
    ]
    cols_detail = [c for c in cols_detail if c in detail.columns]
    st.dataframe(detail[cols_detail], use_container_width=True)

    core, _ = split_totals(data)
    kpi_chips(core)

    stats = core.groupby(["MM", "plateforme"], dropna=True).agg(
        prix_brut=("prix_brut", "sum"),
        prix_net=("prix_net", "sum"),
        base=("base", "sum"),
        charges=("charges", "sum"),
        nuitees=("nuitees", "sum")
    ).reset_index()

    def bar_chart_metric(metric_label, metric_col):
        if stats.empty:
            return
        pvt = stats.pivot(index="MM", columns="plateforme", values=metric_col).fillna(0).sort_index()
        pvt.index = [f"{int(m):02d}" for m in pvt.index]
        chart = alt.Chart(pvt.reset_index()).mark_bar().encode(
            x=alt.X("MM:N", title="Mois"),
            y=alt.Y(f"sum({metric_col}):Q", title=metric_label),
            color="plateforme:N",
            tooltip=["MM", "plateforme", metric_col]
        ).properties(title=metric_label)
        st.altair_chart(chart, use_container_width=True)

    bar_chart_metric("Revenus bruts (€)", "prix_brut")
    bar_chart_metric("Revenus nets (€)", "prix_net")
    bar_chart_metric("Base (€)", "base")
    bar_chart_metric("Nuitées", "nuitees")

    # Pie chart pour répartition par plateforme
    pie_data = core.groupby("plateforme").agg({"prix_brut": "sum"}).reset_index()
    pie_chart = alt.Chart(pie_data).mark_arc().encode(
        theta=alt.Theta("prix_brut:Q", title="Revenus bruts"),
        color=alt.Color("plateforme:N"),
        tooltip=["plateforme", "prix_brut"]
    ).properties(title="Répartition des revenus par plateforme")
    st.altair_chart(pie_chart, use_container_width=True)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        detail[cols_detail].to_excel(writer, index=False, sheet_name="Détail")
    st.download_button(
        "⬇️ Télécharger le détail (XLSX)",
        data=buf.getvalue(),
        file_name=f"rapport_detail_{annee}{'' if mois_label=='Tous' else '_'+mois_label}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        "⬇️ Télécharger le détail (CSV)",
        data=detail[cols_detail].to_csv(index=False).encode("utf-8"),
        file_name=f"rapport_detail_{annee}{'' if mois_label=='Tous' else '_'+mois_label}.csv",
        mime="text/csv"
    )

def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    c1, c2 = st.columns(2)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", annees, index=len(annees)-1) if annees else None
    mois = c2.selectbox("Mois", ["Tous"] + [f"{i:02d}" for i in range(1, 13)])

    data = df.copy()
    if annee:
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]

    if data.empty:
        st.info("Aucune donnée pour cette période.")
        return

    data["prix_brut/nuit"] = data.apply(lambda r: round(r["prix_brut"]/r["nuitees"] if r["nuitees"] else 0, 2), axis=1)
    data["prix_net/nuit"] = data.apply(lambda r: round(r["prix_net"]/r["nuitees"] if r["nuitees"] else 0, 2), axis=1)

    show = data.copy()
    for c in ["date_arrivee", "date_depart"]:
        show[c] = show[c].apply(format_date_str)

    cols = [
        "paye", "nom_client", "sms_envoye", "email_envoye", "plateforme", "telephone", "email",
        "date_arrivee", "date_depart", "nuitees",
        "prix_brut", "commissions", "frais_cb", "prix_net", "menage", "taxes_sejour", "base", "charges", "%",
        "prix_brut/nuit", "prix_net/nuit"
    ]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

def vue_export_ics(df: pd.DataFrame):
    st.title("📤 Export ICS (Google Agenda – Import manuel)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée à exporter.")
        return

    c1, c2, c3 = st.columns(3)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", ["Toutes"] + annees, index=len(annees)) if annees else "Toutes"
    mois = c2.selectbox("Mois", ["Tous"] + [f"{i:02d}" for i in range(1, 13)])
    pfopt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = c3.selectbox("Plateforme", pfopt)

    data = df.copy()
    if annee != "Toutes":
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]

    if data.empty:
        st.info("Aucune réservation pour ces filtres.")
        return

    ics_text = df_to_ics(data)
    st.download_button(
        "⬇️ Télécharger reservations.ics",
        data=ics_text.encode("utf-8"),
        file_name="reservations.ics",
        mime="text/calendar"
    )
    st.caption("Dans Google Agenda : Paramètres → Importer & exporter → Importer → sélectionnez ce fichier .ics.")

def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS & Emails (envoi manuel/automatique)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    today = date.today()
    demain = today + timedelta(days=1)
    hier = today - timedelta(days=1)

    colA, colB = st.columns(2)

    with colA:
        st.subheader("📆 Arrivées demain")
        arrives = df[df["date_arrivee"] == demain].copy()
        if arrives.empty:
            st.info("Aucune arrivée demain.")
        else:
            if st.button("📩 Envoyer SMS à tous (arrivées demain)"):
                for _, r in arrives.iterrows():
                    body = sms_message_arrivee(r)
                    tel = normalize_tel(r.get("telephone"))
                    if tel:
                        success, msg = send_sms(tel, body)
                        if success:
                            r["sms_envoye"] = True
                            st.success(f"SMS envoyé à {r['nom_client']}")
                            log_action("SMS envoyé", f"À {r['nom_client']} ({tel})")
                        else:
                            st.error(msg)
                sauvegarder_donnees(df, get_palette(), st.session_state.logs)

            for _, r in arrives.reset_index(drop=True).iterrows():
                body = sms_message_arrivee(r)
                tel = normalize_tel(r.get("telephone"))
                email = normalize_email(r.get("email"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                email_link = f"mailto:{email}?subject=Bienvenue à Villa Tobias&body={quote(body)}" if email and body else ""
                st.markdown(f"**{r.get('nom_client', '')}** — {r.get('plateforme', '')}")
                st.code(body)
                c1, c2, c3 = st.columns(3)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                if email_link: c3.link_button("📧 Envoyer Email", email_link)
                st.divider()

    with colB:
        st.subheader("🕒 Relance +24h après départ")
        dep_24h = df[df["date_depart"] == hier].copy()
        if dep_24h.empty:
            st.info("Aucun départ hier.")
        else:
            if st.button("📩 Envoyer SMS à tous (départs hier)"):
                for _, r in dep_24h.iterrows():
                    body = sms_message_depart(r)
                    tel = normalize_tel(r.get("telephone"))
                    if tel:
                        success, msg = send_sms(tel, body)
                        if success:
                            r["sms_envoye"] = True
                            st.success(f"SMS envoyé à {r['nom_client']}")
                            log_action("SMS envoyé", f"À {r['nom_client']} ({tel})")
                        else:
                            st.error(msg)
                sauvegarder_donnees(df, get_palette(), st.session_state.logs)

            for _, r in dep_24h.reset_index(drop=True).iterrows():
                body = sms_message_depart(r)
                tel = normalize_tel(r.get("telephone"))
                email = normalize_email(r.get("email"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                email_link = f"mailto:{email}?subject=Merci pour votre séjour&body={quote(body)}" if email and body else ""
                st.markdown(f"**{r.get('nom_client', '')}** — {r.get('plateforme', '')}")
                st.code(body)
                c1, c2, c3 = st.columns(3)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                if email_link: c3.link_button("📧 Envoyer Email", email_link)
                st.divider()

    st.subheader("✍️ Composer un SMS/Email manuel")
    df_pick = df.copy()
    df_pick["id_aff"] = df_pick["nom_client"].astype(str) + " | " + df_pick["plateforme"].astype(str) + " | " + df_pick["date_arrivee"].apply(format_date_str)
    choix = st.selectbox("Choisir une réservation", df_pick["id_aff"])
    r = df_pick.loc[df_pick["id_aff"] == choix].iloc[0]
    tel = normalize_tel(r.get("telephone"))
    email = normalize_email(r.get("email"))

    choix_type = st.radio("Modèle de message", ["Arrivée (demande d’heure)", "Relance après départ", "Message libre"], horizontal=True)
    if choix_type == "Arrivée (demande d’heure)":
        body = sms_message_arrivee(r)
    elif choix_type == "Relance après départ":
        body = sms_message_depart(r)
    else:
        body = st.text_area("Votre message", value="", height=160, placeholder="Tapez votre SMS/Email ici…")

    if tel or email:
        c1, c2, c3 = st.columns(3)
        if tel:
            c1.link_button(f"📞 Appeler {tel}", f"tel:{tel}")
            c2.link_button("📩 Envoyer SMS", f"sms:{tel}?&body={quote(body)}")
            if c2.button("📩 Envoyer SMS (automatique)"):
                success, msg = send_sms(tel, body)
                if success:
                    df.loc[df["id_aff"] == choix, "sms_envoye"] = True
                    sauvegarder_donnees(df, get_palette(), st.session_state.logs)
                    st.success(f"SMS envoyé à {r['nom_client']}")
                    log_action("SMS envoyé", f"À {r['nom_client']} ({tel})")
                else:
                    st.error(msg)
        if email:
            c3.link_button(f"📧 Envoyer Email", f"mailto:{email}?subject=Message de Villa Tobias&body={quote(body)}")
            if c3.button("📧 Envoyer Email (automatique)"):
                success, msg = send_email(email, "Message de Villa Tobias", body)
                if success:
                    df.loc[df["id_aff"] == choix, "email_envoye"] = True
                    sauvegarder_donnees(df, get_palette(), st.session_state.logs)
                    st.success(f"Email envoyé à {r['nom_client']}")
                    log_action("Email envoyé", f"À {r['nom_client']} ({email})")
                else:
                    st.error(msg)
    else:
        st.info("Renseignez un téléphone ou un email et un message.")

def vue_plateformes():
    st.title("🎨 Plateformes (palette couleurs)")
    pal = get_palette()

    st.caption("Ajoutez, modifiez, supprimez des plateformes. Cliquez sur **Enregistrer la palette** pour sauvegarder.")
    pf_df = pd.DataFrame([{"plateforme": k, "couleur": v} for k, v in sorted(pal.items())])
    pf_df = st.data_editor(
        pf_df,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "plateforme": st.column_config.TextColumn("Plateforme", required=True),
            "couleur": st.column_config.TextColumn("Couleur (hex)", help="Format #RRGGBB ou #RGB"),
        }
    )

    c1, c2, c3 = st.columns(3)
    if c1.button("💾 Enregistrer la palette"):
        new_p = {str(r.get("plateforme", "")).strip(): _clean_hex(str(r.get("couleur", "#999999"))) for _, r in pf_df.iterrows() if str(r.get("plateforme", "")).strip()}
        set_palette(new_p)
        df_current, _, _ = charger_donnees()
        sauvegarder_donnees(df_current, new_p, st.session_state.logs)
        st.success("✅ Palette enregistrée dans Excel.")
        log_action("Palette", "Palette de couleurs mise à jour")

    if c2.button("♻️ Réinitialiser palette par défaut"):
        set_palette(DEFAULT_PALETTE.copy())
        df_current, _, _ = charger_donnees()
        sauvegarder_donnees(df_current, get_palette(), st.session_state.logs)
        st.success("✅ Palette réinitialisée.")
        log_action("Palette", "Palette réinitialisée par défaut")
        st.rerun()

    if c3.button("🔄 Recharger depuis Excel"):
        _, pal_file, _ = charger_donnees()
        set_palette(pal_file)
        st.success("✅ Palette rechargée depuis Excel.")
        log_action("Palette", "Palette rechargée depuis Excel")
        st.rerun()

    st.markdown("### Aperçu")
    badges = " &nbsp;&nbsp;".join([platform_badge(pf, pal) for pf in sorted(pal.keys())])
    st.markdown(badges, unsafe_allow_html=True)

def vue_logs():
    st.title("📜 Historique des actions")
    logs = st.session_state.logs
    if logs.empty:
        st.info("Aucun historique disponible.")
        return
    st.dataframe(logs.sort_values(by="timestamp", ascending=False), use_container_width=True)
    st.download_button(
        "📥 Télécharger historique (CSV)",
        data=logs.to_csv(index=False).encode("utf-8"),
        file_name="historique_actions.csv",
        mime="text/csv"
    )

# ============================== APP ==============================
def main():
    st.sidebar.title("📁 Fichier")
    df_tmp, pal_tmp, _ = charger_donnees()
    st.sidebar.download_button(
        "💾 Télécharger reservations.xlsx",
        data=BytesIO(pd.ExcelWriter(FICHIER, engine="openpyxl").__enter__().write()).getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], key=f"restore_{st.session_state.uploader_key_restore}")
    if up is not None and st.sidebar.button("Restaurer maintenant"):
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            with pd.ExcelFile(bio, engine="openpyxl") as xf:
                df_new = pd.read_excel(xf, sheet_name=DATA_SHEET if DATA_SHEET in xf.sheet_names else xf.sheet_names[0], engine="openpyxl",
                                      converters={"telephone": normalize_tel, "email": normalize_email})
                df_new = ensure_schema(df_new)
                palette_new = DEFAULT_PALETTE.copy()
                if PALETTE_SHEET in xf.sheet_names:
                    pal_df = pd.read_excel(xf, sheet_name=PALETTE_SHEET, engine="openpyxl")
                    if {"plateforme", "couleur"}.issubset(set(pal_df.columns)):
                        for _, r in pal_df.iterrows():
                            name = str(r["plateforme"]).strip()
                            color = _clean_hex(str(r["couleur"]))
                            if name:
                                palette_new[name] = color
            sauvegarder_donnees(df_new, palette_new, st.session_state.logs)
            set_palette(palette_new)
            st.sidebar.success("✅ Fichier restauré.")
            log_action("Restauration", "Fichier Excel restauré depuis upload")
            st.session_state.uploader_key_restore += 1
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache"):
        st.cache_data.clear()
        st.session_state.did_clear_cache = True
        st.sidebar.success("Cache vidé.")
        log_action("Maintenance", "Cache vidé")

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations", "➕ Ajouter", "✏️ Modifier / Supprimer", "📅 Calendrier",
         "📊 Rapport", "👥 Liste clients", "📤 Export ICS", "✉️ SMS & Emails", "🎨 Plateformes", "📜 Historique"]
    )

    df, _, _ = charger_donnees()
    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df)
    elif onglet == "📅 Calendrier":
        vue_calendrier(df)
    elif onglet == "📊 Rapport":
        vue_rapport(df)
    elif onglet == "👥 Liste clients":
        vue_clients(df)
    elif onglet == "📤 Export ICS":
        vue_export_ics(df)
    elif onglet == "✉️ SMS & Emails":
        vue_sms(df)
    elif onglet == "🎨 Plateformes":
        vue_plateformes()
    elif onglet == "📜 Historique":
        vue_logs()

if __name__ == "__main__":
    main()