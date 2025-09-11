# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO
from datetime import datetime
import os, time

# -------------------- CONFIG MINIMALE --------------------
st.set_page_config(page_title="✨ Villa Tobias — Safe Mode", page_icon="✨", layout="wide")
st.write("# ✨ Villa Tobias — Safe Mode")

# (Optionnel) Réduit certains logs verbeux
st.set_option("client.showErrorDetails", True)

CSV_RESERVATIONS = "reservations.csv"

# -------------------- OUTILS SÛRS --------------------
def _detect_delimiter_and_read(raw_bytes: bytes) -> pd.DataFrame:
    """Essaie ; , tab | puis fallback. Retourne DataFrame (dtype=str)."""
    if raw_bytes is None:
        return pd.DataFrame()
    txt = raw_bytes.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 1:
                return df
        except Exception:
            continue
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _load_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _safe_to_date(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series([], dtype="object")
    s = series.astype(str).str.strip()
    # 1) dayfirst
    d1 = pd.to_datetime(s, errors="coerce", dayfirst=True)
    # 2) y-m-d si beaucoup de NaT
    if d1.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d1 = d1.fillna(d2)
    return d1.dt.date

def _safe_to_num(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series([], dtype="float64")
    s = (series.astype(str)
         .str.replace("€","",regex=False)
         .str.replace(" ","",regex=False)
         .str.replace(",",".",regex=False)
         .str.strip())
    out = pd.to_numeric(s, errors="coerce")
    return out

# -------------------- ÉTAT / DEBUG --------------------
if "cycle" not in st.session_state:
    st.session_state.cycle = 0
st.session_state.cycle += 1

with st.expander("🛠️ Panneau debug"):
    st.write("**Cycle (compteur de reruns)** :", st.session_state.cycle)
    st.write("**CWD** :", os.getcwd())
    st.write("**Fichier visé** :", os.path.abspath(CSV_RESERVATIONS))
    try:
        stat = os.stat(CSV_RESERVATIONS)
        st.write("**mtime** :", time.ctime(stat.st_mtime))
        st.write("**taille** :", stat.st_size, "octets")
    except Exception as e:
        st.info(f"reservations.csv introuvable pour stats : {e}")

# -------------------- SIDEBAR ACTIONS --------------------
st.sidebar.header("⚙️ Actions")
refresh = st.sidebar.button("🔄 Rafraîchir (sans purge cache)")
st.sidebar.caption("Safe mode : aucun clear cache automatique, pas de rerun forcé en boucle.")

# -------------------- CHARGEMENT SANS BOUCLE --------------------
@st.cache_data(ttl=60)  # petit TTL pour limiter les relectures
def charger_df():
    raw = _load_bytes(CSV_RESERVATIONS)
    base = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    # Normalisation minimale pour test
    df = base.copy()
    if not df.empty:
        # Si colonnes dates existent, on tente une conversion douce
        for c in ["date_arrivee", "date_depart"]:
            if c in df.columns:
                df[c] = _safe_to_date(df[c])
        # Si numériques évidents
        for c in ["prix_brut","prix_net","nuitees"]:
            if c in df.columns:
                df[c] = _safe_to_num(df[c])
    return df

if refresh:
    # Pas de clear automatique, juste recharger la fonction cache
    charger_df.clear()

df = charger_df()

# -------------------- AFFICHAGE --------------------
if df is None or df.empty:
    st.warning("Aucune donnée chargée. Place ton **reservations.csv** à la racine du projet.")
else:
    st.success(f"Données chargées ✅ — {len(df)} lignes • {len(df.columns)} colonnes")
    st.write("Aperçu :")
    st.dataframe(df.head(50), use_container_width=True)

    # Mini test logique optionnel : compter les arrivées du jour si la colonne existe
    if "date_arrivee" in df.columns:
        try:
            today = datetime.now().date()
            n_arr = int((pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date == today).sum())
            st.info(f"Arrivées **aujourd'hui** (si colonne présente) : {n_arr}")
        except Exception as e:
            st.warning(f"Conversion dates arrivée problématique : {e}")

# -------------------- NOTES --------------------
st.markdown("---")
st.write("**Étapes suivantes**")
st.write("""
1. Vérifie que ça **ne tourne pas dans le vide** (le compteur de cycle doit rester stable si tu ne touches rien).
2. Si c’est stable, on ré-intègre progressivement:
   - Filtres & KPIs (Réservations)
   - Clients
   - Export ICS
   - Calendrier grille
   - SMS
3. Si ça repart en boucle, dis-moi **le nombre de cycles** qui s’affiche sans rien faire et s’il y a un message en bas.
""")