# app.py
import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, datetime, timedelta
from io import BytesIO
from urllib.parse import quote
import requests
import re
import os
import json
import matplotlib.pyplot as plt
import time

# =========================  CONSTANTES  =========================
FICHIER = "reservations.xlsx"
SMS_LOG = "historique_sms.csv"
ICAL_STORE = "ical_calendars.json"  # stockage des calendriers (plateforme + url)

# =========================  UTILS GÉNÉRALES  ====================

_money_re = re.compile(r"[^0-9,.\-]")

def to_money(x):
    """'1 234,50 €' -> 1234.50 (float)."""
    if pd.isna(x) or x is None:
        return np.nan
    s = str(x).strip()
    s = _money_re.sub("", s).replace(",", ".")
    try:
        return float(s)
    except Exception:
        return np.nan

def to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoie et normalise le schéma + types."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()

    # Dates -> date
    for col in ["date_arrivee", "date_depart"]:
        if col in df.columns:
            df[col] = df[col].apply(to_date_only)

    # Numériques propres (gère € et virgules)
    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            if df[col].dtype == object or (df[col].dtype.kind not in "fi"):
                df[col] = df[col].apply(to_money)
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    # Recalcul charges / %
    if "prix_brut" in df.columns and "prix_net" in df.columns:
        df["prix_brut"] = df["prix_brut"].fillna(0)
        df["prix_net"] = df["prix_net"].fillna(0)
        df["charges"] = df["prix_brut"] - df["prix_net"]
        with pd.option_context("mode.use_inf_as_na", True):
            df["%"] = (df["charges"] / df["prix_brut"].replace(0, np.nan) * 100).fillna(0)

    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    # Nuitées
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]
        df["nuitees"] = pd.to_numeric(df["nuitees"], errors="coerce").fillna(0).astype(int)

    # AAAA / MM
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
        df["MM"] = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)
        df["AAAA"] = pd.to_numeric(df["AAAA"], errors="coerce").astype("Int64")
        df["MM"] = pd.to_numeric(df["MM"], errors="coerce").astype("Int64")

    # Colonnes minimales
    for k, v in {"plateforme": "Autre", "nom_client": "", "telephone": ""}.items():
        if k not in df.columns:
            df[k] = v

    # Téléphone : enlever l'apostrophe (on la remettra à la sauvegarde)
    if "telephone" in df.columns:
        def _clean_tel(x):
            s = "" if pd.isna(x) else str(x).strip()
            return s[1:] if s.startswith("'") else s
        df["telephone"] = df["telephone"].apply(_clean_tel)

    if "ical_uid" not in df.columns:
        df["ical_uid"] = ""

    cols_order = ["nom_client","plateforme","telephone","date_arrivee","date_depart","nuitees",
                  "prix_brut","prix_net","charges","%","AAAA","MM","ical_uid"]
    ordered = [c for c in cols_order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

def _marque_totaux(df: pd.DataFrame) -> pd.Series:
    """Détecte les lignes 'Total' (ou équivalentes sans dates mais avec montants)."""
    if df is None or df.empty:
        return pd.Series([], dtype=bool)
    mask = pd.Series(False, index=df.index)
    for col in ["nom_client", "plateforme"]:
        if col in df.columns:
            mask |= df[col].astype(str).str.strip().str.lower().eq("total")
    has_no_dates = pd.Series(True, index=df.index)
    for c in ["date_arrivee","date_depart"]:
        if c in df.columns:
            has_no_dates &= df[c].isna()
    has_money = pd.Series(False, index=df.index)
    for c in ["prix_brut","prix_net","charges"]:
        if c in df.columns:
            has_money |= df[c].notna()
    return mask | (has_no_dates & has_money)

def _trier_et_recoller_totaux(df: pd.DataFrame) -> pd.DataFrame:
    """Tri par date_arrivee puis nom, lignes 'Total' à la fin."""
    if df is None or df.empty:
        return df
    df = df.copy()
    tot_mask = _marque_totaux(df)
    df_total = df[tot_mask].copy()
    df_core = df[~tot_mask].copy()
    by_cols = [c for c in ["date_arrivee","nom_client"] if c in df_core.columns]
    if by_cols:
        df_core = df_core.sort_values(by=by_cols, na_position="last").reset_index(drop=True)
    return pd.concat([df_core, df_total], ignore_index=True)

# =========================  I/O EXCEL + CACHE  =============================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float, cache_buster: int):
    _ = cache_buster
    return pd.read_excel(path)

def charger_donnees(cache_buster: int = 0) -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return pd.DataFrame()
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime, cache_buster)
        return _trier_et_recoller_totaux(ensure_schema(df))
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return pd.DataFrame()

def sauvegarder_donnees(df: pd.DataFrame):
    df = _trier_et_recoller_totaux(ensure_schema(df))
    df_to_save = df.copy()
    # Mise au format 'texte' pour le téléphone -> pour conserver le '+'
    if "telephone" in df_to_save.columns:
        def _to_excel_text(s):
            s = "" if pd.isna(s) else str(s).strip()
            return s if s.startswith("'") or s == "" else "'" + s
        df_to_save["telephone"] = df_to_save["telephone"].apply(_to_excel_text)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as writer:
            df_to_save.to_excel(writer, index=False)
        st.cache_data.clear()
        if "cache_buster" in st.session_state:
            st.session_state.cache_buster += 1
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer un fichier Excel", type=["xlsx"])
    if up is not None:
        try:
            df_new = pd.read_excel(up)
            df_new = _trier_et_recoller_totaux(ensure_schema(df_new))
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            _trier_et_recoller_totaux(ensure_schema(df)).to_excel(writer, index=False)
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = None

    st.sidebar.download_button(
        "📥 Télécharger le fichier Excel",
        data=data_xlsx if data_xlsx else b"",
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(data_xlsx is None),
    )

# =========================  VUES  ==========================================

def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")

    df = _trier_et_recoller_totaux(ensure_schema(df)).copy()
    if df.empty:
        st.info("Aucune donnée.")
        return

    # Filtres
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    colf1, colf2, colf3 = st.columns(3)

    with colf1:
        pf_opts = ["Toutes"] + sorted(df["plateforme"].dropna().astype(str).unique().tolist())
        filtre_pf = st.selectbox("Plateforme", pf_opts, key="res_pf")

    with colf2:
        annee_sel = st.selectbox("Année", annees, index=len(annees)-1 if annees else 0, key="res_annee")

    with colf3:
        mois_opts = ["Tous"] + [f"{i:02d}" for i in range(1,13)]
        mois_sel = st.selectbox("Mois (01–12)", mois_opts, key="res_mois")

    # Appliquer filtres
    data = df.copy()
    if filtre_pf != "Toutes":
        data = data[data["plateforme"] == filtre_pf]
    if annee_sel is not None:
        data = data[data["AAAA"] == int(annee_sel)]
    if mois_sel != "Tous":
        data = data[data["MM"] == int(mois_sel)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # --- Masquage : cacher uniquement les lignes à 0 ET nom_client vide
    mask_zero_and_no_name = (
        (data["prix_brut"].fillna(0) == 0) &
        (data["prix_net"].fillna(0) == 0) &
        (data["charges"].fillna(0) == 0) &
        (data["nom_client"].astype(str).str.strip() == "")
    )
    # On garde les 'Total' même si ça ressemble à zéro
    is_total = _marque_totaux(data)
    to_display = data[~(mask_zero_and_no_name & ~is_total)].copy()

    # Totaux (calcul direct sur les lignes filtrées, hors 'Total')
    core = data[~is_total].copy()
    for c in ["prix_brut","prix_net","charges","nuitees"]:
        core[c] = pd.to_numeric(core[c], errors="coerce").fillna(0)

    tot_ctrl = {
        "prix_brut": float(core["prix_brut"].sum()),
        "prix_net":  float(core["prix_net"].sum()),
        "charges":   float(core["charges"].sum()),
        "nuitees":   int(core["nuitees"].sum()),
        "reservations": int(len(core))
    }

    # Affichage : tri + format dates
    core_sorted = to_display.sort_values(["date_arrivee","nom_client"], na_position="last")
    show = core_sorted.copy()
    for col in ["date_arrivee","date_depart"]:
        if col in show.columns:
            show[col] = show[col].apply(format_date_str)

    cols = [
        "nom_client","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","prix_net","charges","%","AAAA","MM"
    ]
    cols = [c for c in cols if c in show.columns]

    st.dataframe(show[cols], use_container_width=True)

    st.markdown("#### Totaux (calcul direct sur les lignes filtrées, hors 'Total')")
    cA, cB, cC, cD, cE = st.columns(5)
    cA.metric("Prix brut (€)", f"{tot_ctrl['prix_brut']:.2f}")
    cB.metric("Prix net (€)",  f"{tot_ctrl['prix_net']:.2f}")
    cC.metric("Charges (€)",   f"{tot_ctrl['charges']:.2f}")
    cD.metric("Nuitées",       f"{tot_ctrl['nuitees']}")
    cE.metric("Réservations",  f"{tot_ctrl['reservations']}")

    # Export
    csv = show[cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Télécharger la sélection (CSV)",
        data=csv,
        file_name=f"reservations_{annee_sel}_{mois_sel if mois_sel!='Tous' else 'all'}_{filtre_pf}.csv".replace(" ", "_"),
        mime="text/csv",
    )

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    with st.form("ajout_resa"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone (format +33...)")

        if "ajout_arrivee" not in st.session_state:
            st.session_state.ajout_arrivee = date.today()
        arrivee = st.date_input("Date d’arrivée", key="ajout_arrivee")

        min_dep = st.session_state.ajout_arrivee + timedelta(days=1)
        if "ajout_depart" not in st.session_state or not isinstance(st.session_state.ajout_depart, date):
            st.session_state.ajout_depart = min_dep
        elif st.session_state.ajout_depart < min_dep:
            st.session_state.ajout_depart = min_dep
        depart = st.date_input("Date de départ", key="ajout_depart", min_value=min_dep)

        prix_brut = st.number_input("Prix brut (€)", min_value=0.0, step=1.0, format="%.2f")
        prix_net = st.number_input("Prix net (€)", min_value=0.0, step=1.0, format="%.2f", help="Doit être ≤ prix brut.")
        charges_calc = max(prix_brut - prix_net, 0.0)
        pct_calc = (charges_calc / prix_brut * 100) if prix_brut > 0 else 0.0

        st.number_input("Charges (€)", value=round(charges_calc, 2), step=0.01, format="%.2f", disabled=True)
        st.number_input("Commission (%)", value=round(pct_calc, 2), step=0.01, format="%.2f", disabled=True)

        ok = st.form_submit_button("Enregistrer")

    if ok:
        if prix_net > prix_brut:
            st.error("Le prix net ne peut pas être supérieur au prix brut.")
            return
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return

        ligne = {
            "nom_client": (nom or "").strip(),
            "plateforme": plateforme,
            "telephone": (tel or "").strip(),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": float(prix_brut),
            "prix_net": float(prix_net),
            "charges": round(charges_calc, 2),
            "%": round(pct_calc, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month,
            "ical_uid": ""
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        df2 = _trier_et_recoller_totaux(df2)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = _trier_et_recoller_totaux(ensure_schema(df))
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

    with st.form("form_modif"):
        nom = st.text_input("Nom du client", df.at[i, "nom_client"])
        plateformes = ["Booking","Airbnb","Autre"]
        index_pf = plateformes.index(df.at[i,"plateforme"]) if df.at[i,"plateforme"] in plateformes else 2
        plateforme = st.selectbox("Plateforme", plateformes, index=index_pf)
        tel = st.text_input("Téléphone", df.at[i, "telephone"] if "telephone" in df.columns else "")
        arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"] if isinstance(df.at[i, "date_arrivee"], date) else date.today())
        depart = st.date_input("Départ", df.at[i, "date_depart"] if isinstance(df.at[i, "date_depart"], date) else arrivee + timedelta(days=1))
        brut = st.number_input("Prix brut (€)", value=float(df.at[i, "prix_brut"]) if pd.notna(df.at[i, "prix_brut"]) else 0.0, format="%.2f")
        net = st.number_input("Prix net (€)", value=float(df.at[i, "prix_net"]) if pd.notna(df.at[i, "prix_net"]) else 0.0, max_value=max(0.0,float(brut)), format="%.2f")
        c1, c2 = st.columns(2)
        b_modif = c1.form_submit_button("💾 Enregistrer")
        b_del = c2.form_submit_button("🗑 Supprimer")

    if b_modif:
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[i, "nom_client"] = nom.strip()
        df.at[i, "plateforme"] = plateforme
        df.at[i, "telephone"] = tel.strip()
        df.at[i, "date_arrivee"] = arrivee
        df.at[i, "date_depart"] = depart
        df.at[i, "prix_brut"] = float(brut)
        df.at[i, "prix_net"] = float(net)
        df.at[i, "charges"] = round(brut - net, 2)
        df.at[i, "%"] = round(((brut - net) / brut * 100) if brut else 0, 2)
        df.at[i, "nuitees"] = (depart - arrivee).days
        df.at[i, "AAAA"] = arrivee.year
        df.at[i, "MM"] = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df)
        st.success("✅ Réservation modifiée")
        st.rerun()

    if b_del:
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("🗑 Réservation supprimée")
        st.rerun()

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier mensuel")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, (date.today().month - 1)))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = st.selectbox("Année", annees, index=max(0, len(annees) - 1))
    mois_index = list(calendar.month_name).index(mois_nom)

    jours = [date(annee, mois_index, j+1) for j in range(calendar.monthrange(annee, mois_index)[1])]
    planning = {j: [] for j in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        d1 = row.get("date_arrivee")
        d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        for j in jours:
            if d1 <= j < d2:
                icone = couleurs.get(row.get("plateforme", "Autre"), "⬜")
                nom = str(row.get("nom_client", ""))
                planning[j].append(f"{icone} {nom}")

    table = []
    for semaine in calendar.monthcalendar(annee, mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                d = date(annee, mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning.get(d, []))
                ligne.append(contenu)
        table.append(ligne)

    st.table(pd.DataFrame(table, columns=["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]))

# ---------- Rapport : pipeline propre ----------

def _df_agreg_rapport(df: pd.DataFrame) -> pd.DataFrame:
    """ Nettoyage strict pour des chiffres fiables (exclut 'Total', na, etc.). """
    if df is None or df.empty:
        return pd.DataFrame()
    core = ensure_schema(df).copy()

    # Exclure 'Total' / lignes sans dates
    is_total = _marque_totaux(core)
    core = core[~is_total].copy()

    # Garder lignes avec arrivee valide
    core = core[core["date_arrivee"].apply(lambda d: isinstance(d, date))].copy()

    # Numériques sûrs
    for c in ["prix_brut","prix_net","charges","nuitees"]:
        core[c] = pd.to_numeric(core[c], errors="coerce").fillna(0)

    # AAAA/MM sûrs
    core["AAAA"] = pd.to_numeric(core["AAAA"], errors="coerce")
    core["MM"]   = pd.to_numeric(core["MM"], errors="coerce")
    core = core.dropna(subset=["AAAA","MM"])
    core["AAAA"] = core["AAAA"].astype(int)
    core["MM"]   = core["MM"].astype(int)

    # Plateforme propre
    core["plateforme"] = core["plateforme"].fillna("Autre").astype(str)

    return core

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport (une année à la fois) — chiffres fiables")
    core = _df_agreg_rapport(df)
    if core.empty:
        st.info("Aucune donnée exploitable.")
        return

    # Filtres
    annees = sorted(core["AAAA"].unique().tolist())
    annee = st.selectbox("Année", annees, index=len(annees)-1, key="rapport_annee")

    data = core[core["AAAA"] == int(annee)].copy()
    plateformes = ["Toutes"] + sorted(data["plateforme"].dropna().unique().tolist())
    col1, col2 = st.columns(2)
    with col1:
        filtre_plateforme = st.selectbox("Plateforme", plateformes, key="rapport_pf")
    with col2:
        filtre_mois_label = st.selectbox("Mois (01–12)", ["Tous"] + [f"{i:02d}" for i in range(1,13)], key="rapport_mois")

    if filtre_plateforme != "Toutes":
        data = data[data["plateforme"] == filtre_plateforme]
    if filtre_mois_label != "Tous":
        data = data[data["MM"] == int(filtre_mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # Agrégation
    stats = (
        data.groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 charges=("charges","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
    )

    # Compléter pour les GRAPHIQUES (12 mois) mais garder un tableau "nettoyé"
    plats = sorted(stats["plateforme"].unique().tolist())
    full_rows = []
    for m in range(1, 13):
        for p in plats:
            row = stats[(stats["MM"] == m) & (stats["plateforme"] == p)]
            if row.empty:
                full_rows.append({"MM": m, "plateforme": p, "prix_brut": 0.0, "prix_net": 0.0, "charges": 0.0, "nuitees": 0})
            else:
                full_rows.append(row.iloc[0].to_dict())
    stats_full = pd.DataFrame(full_rows).sort_values(["MM","plateforme"]).reset_index(drop=True)

    # Tableau sans lignes à zéro
    stats_table = stats_full[
        ~(
            (stats_full["prix_brut"].round(2) == 0) &
            (stats_full["prix_net"].round(2) == 0) &
            (stats_full["charges"].round(2)  == 0) &
            (stats_full["nuitees"].round(2) == 0)
        )
    ].copy()

    # Tableau
    st.subheader(f"Détail {annee}")
    affiche = stats_table.rename(columns={"MM": "Mois"})[["Mois","plateforme","prix_brut","prix_net","charges","nuitees"]]
    st.dataframe(affiche, use_container_width=True)

    # Totaux (calcul direct)
    tot_ctrl = {
        "prix_brut": float(data["prix_brut"].sum()),
        "prix_net":  float(data["prix_net"].sum()),
        "charges":   float(data["charges"].sum()),
        "nuitees":   float(data["nuitees"].sum()),
    }

    st.markdown("#### Totaux (calcul direct)")
    colA, colB, colC, colD = st.columns(4)
    colA.metric("Prix brut (€)", f"{tot_ctrl['prix_brut']:.2f}")
    colB.metric("Prix net (€)",  f"{tot_ctrl['prix_net']:.2f}")
    colC.metric("Charges (€)",   f"{tot_ctrl['charges']:.2f}")
    colD.metric("Nuitées",       f"{int(tot_ctrl['nuitees'])}")

    # Graphes matplotlib : X = 1..12
    def plot_grouped_bars(metric: str, title: str, ylabel: str):
        months = list(range(1, 13))
        base_x = np.arange(len(months), dtype=float)
        plats_sorted = sorted(plats)
        width = 0.8 / max(1, len(plats_sorted))

        fig, ax = plt.subplots(figsize=(10, 4))
        for i, p in enumerate(plats_sorted):
            sub = stats_full[stats_full["plateforme"] == p]
            vals = {int(mm): float(v) for mm, v in zip(sub["MM"], sub[metric])}
            y = np.array([vals.get(m, 0.0) for m in months], dtype=float)
            x = base_x + (i - (len(plats_sorted)-1)/2) * width
            ax.bar(x, y, width=width, label=p)

        ax.set_xlim(-0.5, 11.5)
        ax.set_xticks(base_x)
        ax.set_xticklabels([f"{m:02d}" for m in months])
        ax.set_xlabel(f"Mois ({annee})")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(loc="upper left", frameon=False)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        st.pyplot(fig); plt.close(fig)

    st.markdown("---")
    plot_grouped_bars("prix_brut", "💰 Revenus bruts", "€")
    plot_grouped_bars("charges", "💸 Charges", "€")
    plot_grouped_bars("nuitees", "🛌 Nuitées", "Nuitées")

def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = st.selectbox("Année", annees) if annees else None
    mois = st.selectbox("Mois", ["Tous"] + list(range(1,13)))

    data = df.copy()
    if annee:
        data = data[data["AAAA"] == annee]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]
    if data.empty:
        st.info("Aucune donnée pour cette période.")
        return

    with pd.option_context('mode.use_inf_as_na', True):
        if "nuitees" in data.columns and "prix_brut" in data.columns:
            data["prix_brut/nuit"] = (data["prix_brut"] / data["nuitees"]).replace([np.inf,-np.inf], np.nan).fillna(0).round(2)
        if "nuitees" in data.columns and "prix_net" in data.columns:
            data["prix_net/nuit"] = (data["prix_net"] / data["nuitees"]).replace([np.inf,-np.inf], np.nan).fillna(0).round(2)

    cols = ["nom_client","plateforme","date_arrivee","date_depart","nuitees",
            "prix_brut","prix_net","charges","%","prix_brut/nuit","prix_net/nuit","telephone"]
    cols = [c for c in cols if c in data.columns]

    show = data.copy()
    for c in ["date_arrivee","date_depart"]:
        if c in show.columns:
            show[c] = show[c].apply(format_date_str)

    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger la liste (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

# =========================  SMS (préparation)  ==============================

def sms_message(row: pd.Series) -> str:
    arrivee = format_date_str(row.get("date_arrivee"))
    depart = format_date_str(row.get("date_depart"))
    nuitees = int(row.get("nuitees") or 0)
    plateforme = str(row.get("plateforme") or "")
    nom = str(row.get("nom_client") or "")
    tel = str(row.get("telephone") or "")
    msg = (
        "VILLA TOBIAS\n"
        f"Plateforme : {plateforme}\n"
        f"Date d'arrivee : {arrivee}  Date depart : {depart}  Nombre de nuitées : {nuitees}\n\n"
        f"Bonjour {nom}\n"
        f"Telephone : {tel}\n\n"
        "Nous sommes heureux de vous accueillir prochainement et vous prions de bien vouloir nous communiquer votre heure d'arrivee. "
        "Nous vous attendrons sur place pour vous remettre les cles de l'appartement et vous indiquer votre emplacement de parking. "
        "Nous vous souhaitons un bon voyage et vous disons a demain.\n\n"
        "Annick & Charley"
    )
    return msg

def log_sms(nom, telephone, message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ligne = {"nom": nom, "telephone": telephone, "message": message, "horodatage": now}
    try:
        if os.path.exists(SMS_LOG):
            old = pd.read_csv(SMS_LOG)
            df_out = pd.concat([old, pd.DataFrame([ligne])], ignore_index=True)
        else:
            df_out = pd.DataFrame([ligne])
        df_out.to_csv(SMS_LOG, index=False)
    except Exception:
        pass

def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS (préparation)")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune réservation pour SMS.")
        return

    demain = date.today() + timedelta(days=1)
    arrivees_demain = df[df["date_arrivee"] == demain]
    mode = st.radio("Sélection", ["Arrivées demain", "Choisir une réservation"])

    if mode == "Arrivées demain":
        if arrivees_demain.empty:
            st.info("Aucune arrivée demain.")
            return
        cible = st.selectbox("Réservation", arrivees_demain.index, format_func=lambda i: f"{arrivees_demain.at[i,'nom_client']} | {format_date_str(arrivees_demain.at[i,'date_arrivee'])}")
        row = arrivees_demain.loc[cible]
    else:
        cible = st.selectbox("Réservation", df.index, format_func=lambda i: f"{df.at[i,'nom_client']} | {format_date_str(df.at[i,'date_arrivee'])}")
        row = df.loc[cible]

    message = sms_message(row)
    st.text_area("Message SMS", value=message, height=220)
    tel = str(row.get("telephone") or "").strip()

    col1, col2 = st.columns(2)
    with col1:
        if tel:
            url = f"sms:{tel}?&body={quote(message)}"
            st.markdown(f"[📲 Ouvrir SMS sur votre mobile]({url})", unsafe_allow_html=True)
        else:
            st.warning("Pas de numéro de téléphone enregistré.")
    with col2:
        if st.button("✅ Marquer comme envoyé (journal)"):
            log_sms(str(row.get("nom_client") or ""), tel, message)
            st.success("Journal SMS mis à jour.")

    st.divider()
    st.subheader("Historique SMS (CSV)")
    if os.path.exists(SMS_LOG):
        try:
            st.dataframe(pd.read_csv(SMS_LOG))
        except Exception:
            st.info("Historique non lisible.")

# =========================  iCal : multi-calendriers  =======================

def load_calendars() -> list[dict]:
    if os.path.exists(ICAL_STORE):
        try:
            return json.load(open(ICAL_STORE, "r", encoding="utf-8"))
        except Exception:
            return []
    return []

def save_calendars(cals: list[dict]):
    try:
        json.dump(cals, open(ICAL_STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        st.success("📒 Liste de calendriers sauvegardée.")
    except Exception as e:
        st.error(f"Impossible d'enregistrer la liste des calendriers : {e}")

def parse_ics(text: str):
    """Parse minimal : DTSTART/DTEND, SUMMARY, UID -> {uid,start,end,summary}."""
    events = []
    blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, flags=re.S)
    for b in blocks:
        dtstart = re.search(r"DTSTART(?:;[^:\n]*)?:(.+)", b)
        dtend   = re.search(r"DTEND(?:;[^:\n]*)?:(.+)", b)
        summary = re.search(r"SUMMARY:(.+)", b)
        uid     = re.search(r"UID:(.+)", b)

        def _to_date(s):
            s = s.strip()
            try:
                if "T" in s:
                    return pd.to_datetime(s).date()
                else:
                    return datetime.strptime(s, "%Y%m%d").date()
            except Exception:
                try:
                    return pd.to_datetime(s).date()
                except Exception:
                    return None

        start = _to_date(dtstart.group(1)) if dtstart else None
        end   = _to_date(dtend.group(1)) if dtend else None
        summ  = summary.group(1).strip() if summary else ""
        uidv  = uid.group(1).strip() if uid else ""
        if isinstance(start, date) and isinstance(end, date) and start < end:
            events.append({"uid": uidv, "start": start, "end": end, "summary": summ})
    return events

def import_events_into_df(df: pd.DataFrame, events: list[dict], plateforme: str) -> tuple[pd.DataFrame, int, int]:
    """Ajoute les événements dans df (zéro prix), skip si ical_uid déjà présent."""
    df = ensure_schema(df).copy()
    existing_uids = set(str(x) for x in df.get("ical_uid", pd.Series([], dtype=str)).fillna(""))

    rows = []
    added = 0
    skipped = 0
    for e in events:
        uid = str(e.get("uid", "") or "")
        if uid and uid in existing_uids:
            skipped += 1
            continue
        start = e["start"]; end = e["end"]
        rows.append({
            "nom_client": e.get("summary", "") or "",
            "plateforme": plateforme,
            "telephone": "",
            "date_arrivee": start,
            "date_depart": end,
            "prix_brut": 0.0,
            "prix_net": 0.0,
            "charges": 0.0,
            "%": 0.0,
            "nuitees": (end - start).days,
            "AAAA": start.year,
            "MM": start.month,
            "ical_uid": uid
        })
        added += 1

    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
        df = _trier_et_recoller_totaux(df)
    return df, added, skipped

def vue_sync_ical(df: pd.DataFrame):
    st.title("🔄 Synchroniser iCal (multi-calendriers)")
    st.caption("Gérez plusieurs calendriers (Booking, Airbnb, etc.). Ajoutez un calendrier puis importez-le. Les UID iCal existants sont ignorés pour éviter les doublons.")

    # ---- Gestion de la liste des calendriers
    cals = load_calendars()
    with st.expander("📒 Mes calendriers configurés", expanded=True):
        if not cals:
            st.info("Aucun calendrier configuré pour le moment.")
        else:
            for i, c in enumerate(cals):
                col1, col2, col3 = st.columns([2,5,1])
                col1.write(f"**{c.get('plateforme','?')}**")
                col2.code(c.get("url",""), language="text")
                if col3.button("🗑️", key=f"del_cal_{i}", help="Supprimer ce calendrier"):
                    del cals[i]
                    save_calendars(cals)
                    st.rerun()

    with st.expander("➕ Ajouter un calendrier", expanded=False):
        new_pf = st.text_input("Nom de la plateforme (ex. Booking, Airbnb, Autre)", key="new_pf")
        new_url = st.text_input("URL iCal (.ics)", key="new_url")
        if st.button("Ajouter ce calendrier"):
            if not new_pf or not new_url:
                st.warning("Veuillez compléter la plateforme et l’URL.")
            else:
                cals.append({"plateforme": new_pf.strip(), "url": new_url.strip()})
                save_calendars(cals)
                st.success("Calendrier ajouté.")
                st.rerun()

    st.divider()

    # ---- Import global
    col_all1, col_all2 = st.columns(2)
    with col_all1:
        if st.button("📥 Tout importer (tous les calendriers)"):
            if not cals:
                st.warning("Aucun calendrier à importer.")
            else:
                total_new, total_skip = 0, 0
                df_work = df.copy()
                for c in cals:
                    try:
                        r = requests.get(c["url"], timeout=20)
                        r.raise_for_status()
                        events = parse_ics(r.text)
                        df_work, added, skipped = import_events_into_df(df_work, events, c["plateforme"])
                        total_new += added; total_skip += skipped
                    except Exception as e:
                        st.error(f"Erreur import {c.get('plateforme','?')}: {e}")
                sauvegarder_donnees(df_work)
                st.success(f"Import terminé : +{total_new} ajoutés, {total_skip} ignorés (UID déjà présents).")
                st.rerun()

    with col_all2:
        st.caption("Astuce : utilisez les boutons d’action à côté de chaque calendrier pour importer individuellement.")

    # ---- Import individuel
    st.subheader("Importer un calendrier")
    if not cals:
        st.info("Ajoutez d’abord un calendrier ci-dessus.")
        return

    choix = st.selectbox("Calendrier à importer", list(range(len(cals))), format_func=lambda i: f"{cals[i]['plateforme']} — {cals[i]['url']}")
    if st.button("Importer ce calendrier"):
        c = cals[choix]
        try:
            r = requests.get(c["url"], timeout=20)
            r.raise_for_status()
            events = parse_ics(r.text)
            df2, added, skipped = import_events_into_df(df, events, c["plateforme"])
            sauvegarder_donnees(df2)
            st.success(f"{added} ajoutés, {skipped} ignorés (UID déjà présents).")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur d’import : {e}")

# =========================  APP (main)  =====================================

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

    # Gestion cache côté utilisateur
    if "cache_buster" not in st.session_state:
        st.session_state.cache_buster = 0

    st.sidebar.markdown("## 🧰 Maintenance")
    c1, c2 = st.sidebar.columns([3, 1])
    c1.caption(f"Cache buster : {st.session_state.cache_buster}")
    if c2.button("♻️ Vider"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state.cache_buster += 1
        st.sidebar.success("Cache vidé ✅")
        st.rerun()

    # Kill-switch URL ?clear=1
    params = st.query_params
    clear_val = params.get("clear", ["0"])[0] if isinstance(params.get("clear"), list) else params.get("clear")
    if clear_val == "1":
        st.cache_data.clear()
        st.cache_resource.clear()
        st.session_state.cache_buster += 1
        if "clear" in st.query_params:
            del st.query_params["clear"]
        st.query_params["_"] = str(time.time())
        st.success("Cache vidé via l’URL ✅")
        st.rerun()

    st.sidebar.title("📁 Fichier")
    bouton_restaurer()
    df = charger_donnees(st.session_state.cache_buster)
    bouton_telecharger(df)

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","✉️ SMS","🔄 Synchroniser iCal"]
    )

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
    elif onglet == "✉️ SMS":
        vue_sms(df)
    elif onglet == "🔄 Synchroniser iCal":
        vue_sync_ical(df)

if __name__ == "__main__":
    main()