# io_utils.py — I/O Excel + Plateformes pour Villa Tobias
import streamlit as st
import pandas as pd
import numpy as np
from datetime import date
from io import BytesIO
import os

# ============================== Réglages ==============================
FICHIER = "reservations.xlsx"
SHEET_RESAS = "Sheet1"
SHEET_PLAT = "Plateformes"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

BASE_COLS = [
    "paye", "nom_client", "sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%", "AAAA","MM","ical_uid"
]

# ============================== Utils internes ==============================

def _to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def _normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"): s = s[:-2]
    return s

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    # colonnes minimales
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    # types / défauts
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(_to_date_only)
    df["telephone"] = df["telephone"].apply(_normalize_tel)

    for c in ["prix_brut","commissions","frais_cb","prix_net",
              "menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # nuitées
    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]

    # AAAA/MM
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    # défauts
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")

    # NaN -> 0 pour calculs
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    # calculs
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    # arrondis
    for c in ["prix_brut","commissions","frais_cb","prix_net",
              "menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)

    # ordre
    ordered_cols = [c for c in BASE_COLS if c in df.columns]
    rest_cols = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + rest_cols]

# ============================== Lecture / écriture Excel ==============================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float) -> dict:
    """Retourne un dict {'resas': DataFrame, 'plat': DataFrame}."""
    try:
        xl = pd.ExcelFile(path, engine="openpyxl")
        # réservations
        if SHEET_RESAS in xl.sheet_names:
            df_res = pd.read_excel(xl, SHEET_RESAS, engine="openpyxl",
                                   converters={"telephone": _normalize_tel})
        else:
            df_res = pd.DataFrame()
        # plateformes
        if SHEET_PLAT in xl.sheet_names:
            df_plat = pd.read_excel(xl, SHEET_PLAT, engine="openpyxl")
        else:
            df_plat = pd.DataFrame(columns=["plateforme","couleur"])
        return {"resas": df_res, "plat": df_plat}
    except Exception as e:
        # propage pour gestion amont
        raise e

def charger_donnees() -> pd.DataFrame:
    """Charge les réservations (onglet Sheet1) + applique le schéma."""
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        payload = _read_excel_cached(FICHIER, mtime)
        return ensure_schema(payload.get("resas", pd.DataFrame()))
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def load_plateformes() -> dict:
    """Charge la palette depuis l’onglet Plateformes. Si absent → DEFAULT_PALETTE."""
    if not os.path.exists(FICHIER):
        return DEFAULT_PALETTE.copy()
    try:
        mtime = os.path.getmtime(FICHIER)
        payload = _read_excel_cached(FICHIER, mtime)
        dfp = payload.get("plat", pd.DataFrame(columns=["plateforme","couleur"]))
        pal = {}
        for _, r in dfp.iterrows():
            name = str(r.get("plateforme") or "").strip()
            col  = str(r.get("couleur") or "").strip()
            if name and col and col.startswith("#"):
                pal[name] = col
        if not pal:
            pal = DEFAULT_PALETTE.copy()
        return pal
    except Exception as e:
        st.error(f"Erreur de lecture Excel (Plateformes) : {e}")
        return DEFAULT_PALETTE.copy()

def save_plateformes(palette: dict):
    """Sauvegarde/écrase l’onglet Plateformes avec (plateforme,couleur)."""
    # On lit d’abord l’existant pour ne pas perdre les réservations
    if os.path.exists(FICHIER):
        try:
            mtime = os.path.getmtime(FICHIER)
            payload = _read_excel_cached(FICHIER, mtime)
            df_res = ensure_schema(payload.get("resas", pd.DataFrame()))
        except Exception:
            df_res = ensure_schema(pd.DataFrame())
    else:
        df_res = ensure_schema(pd.DataFrame())

    dfp = pd.DataFrame(
        [{"plateforme": k, "couleur": v} for k, v in palette.items()],
        columns=["plateforme","couleur"]
    )

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df_res.to_excel(w, index=False, sheet_name=SHEET_RESAS)
            dfp.to_excel(w, index=False, sheet_name=SHEET_PLAT)
        st.cache_data.clear()
        st.success("🎨 Plateformes sauvegardées.")
    except Exception as e:
        st.error(f"Échec sauvegarde plateformes : {e}")

def sauvegarder_donnees(df: pd.DataFrame):
    """Sauvegarde les réservations en conservant/creant aussi l’onglet Plateformes si besoin."""
    df = ensure_schema(df)

    # Charger palette existante (pour la recopier)
    palette = load_plateformes()

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=SHEET_RESAS)
            # (re)écrit l’onglet Plateformes
            pd.DataFrame(
                [{"plateforme": k, "couleur": v} for k, v in palette.items()],
                columns=["plateforme","couleur"]
            ).to_excel(w, index=False, sheet_name=SHEET_PLAT)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

# ============================== Restauration / Téléchargement ==============================

def bouton_restaurer():
    """Uploader un xlsx et remplace complètement `reservations.xlsx` (2 onglets)."""
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            # On valide la lecture avant d’écrire
            xl = pd.ExcelFile(BytesIO(raw), engine="openpyxl")
            df_res = pd.read_excel(xl, SHEET_RESAS, engine="openpyxl") if SHEET_RESAS in xl.sheet_names else pd.DataFrame()
            df_res = ensure_schema(df_res)

            if SHEET_PLAT in xl.sheet_names:
                dfp = pd.read_excel(xl, SHEET_PLAT, engine="openpyxl")
                # petite normalisation
                if "plateforme" not in dfp.columns or "couleur" not in dfp.columns:
                    dfp = pd.DataFrame(columns=["plateforme","couleur"])
            else:
                dfp = pd.DataFrame(
                    [{"plateforme": k, "couleur": v} for k, v in DEFAULT_PALETTE.items()],
                    columns=["plateforme","couleur"]
                )

            # Ecrit le nouveau fichier
            with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
                df_res.to_excel(w, index=False, sheet_name=SHEET_RESAS)
                dfp.to_excel(w, index=False, sheet_name=SHEET_PLAT)

            st.cache_data.clear()
            st.sidebar.success("✅ Fichier restauré.")
            # Streamlit 1.32+: st.rerun ; plus ancien: st.experimental_rerun
            try:
                st.rerun()
            except Exception:
                st.experimental_rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    """Télécharger l’état actuel (réservations + plateformes) en xlsx."""
    # s’assure qu’on écrit aussi la palette actuelle
    palette = load_plateformes()
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            ensure_schema(df).to_excel(w, index=False, sheet_name=SHEET_RESAS)
            pd.DataFrame(
                [{"plateforme": k, "couleur": v} for k, v in palette.items()],
                columns=["plateforme","couleur"]
            ).to_excel(w, index=False, sheet_name=SHEET_PLAT)
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = b""

    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data_xlsx) == 0),
    )

# ============================== API palette pour app.py ==============================

def get_palette() -> dict:
    """Retourne la palette (depuis Excel si possible, sinon défaut) + la mémorise."""
    pal = load_plateformes()
    # garde aussi en session pour rapidité UI (facultatif)
    st.session_state["palette"] = pal
    return pal

def save_palette(palette: dict):
    """Sauvegarde palette dans Excel + session."""
    if not isinstance(palette, dict):
        return
    # nettoyage simple
    clean = {str(k): str(v) for k, v in palette.items() if k and isinstance(v, str) and v.startswith("#")}
    save_plateformes(clean)
    st.session_state["palette"] = clean