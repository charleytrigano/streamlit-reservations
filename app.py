# app.py — Réservations Villa Tobias (présentation améliorée)
import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta
from io import BytesIO
import os
import re
import matplotlib.pyplot as plt
from urllib.parse import quote

FICHIER = "reservations.xlsx"

# ==============================  UI HELPERS  ===============================

def header(titre: str, sous_titre: str = ""):
    st.markdown(
        f"""
        <div style="padding:8px 0 4px 0">
          <h2 style="margin:0">{titre}</h2>
          <div style="color:#666;margin-top:2px">{sous_titre}</div>
        </div>
        <hr style="margin:8px 0 16px 0; opacity:.25">
        """,
        unsafe_allow_html=True,
    )

def inject_css():
    st.markdown(
        """
        <style>
          .stTable td, .stTable th { font-size: 0.92rem; }
          h2, h3 { letter-spacing: 0.2px; }
          section[data-testid="stSidebar"] button { padding: .3rem .55rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def metrics_bar_compact(df: pd.DataFrame, prefix: str = ""):
    """Barre de totaux compacte (petite), avec unités € et %."""
    if df is None or df.empty:
        return
    tmp = df.copy()
    for c in ["prix_brut", "prix_net", "charges", "nuitees", "%"]:
        tmp[c] = pd.to_numeric(tmp.get(c, 0), errors="coerce").fillna(0)

    brut = float(tmp["prix_brut"].sum())
    net = float(tmp["prix_net"].sum())
    ch = float(tmp["charges"].sum())
    nts = float(tmp["nuitees"].sum())
    pct_mean = (
        float((tmp["%"] * tmp["prix_brut"]).sum() / tmp["prix_brut"].replace(0, np.nan).sum())
        if tmp["prix_brut"].sum()
        else 0.0
    )
    brut_nuit = (brut / nts) if nts else 0.0
    net_nuit = (net / nts) if nts else 0.0

    def chip(label, value, sub=None):
        sub = f"<div style='opacity:.7'>{sub}</div>" if sub else ""
        return (
            f"<div style='padding:.35rem .55rem;border:1px solid #E6E6E6;border-radius:.5rem;"
            f"font-size:.9rem;line-height:1.2;background:#FAFAFA'>"
            f"<div style='font-weight:600'>{label}</div>"
            f"<div style='font-variant-numeric: tabular-nums;'>{value}</div>"
            f"{sub}</div>"
        )

    cA, cB, cC, cD, cE = st.columns(5)
    cA.markdown(
        chip(prefix + "Brut", f"{brut:,.2f} €".replace(",", " "), f"{brut_nuit:,.2f} €/nuit".replace(",", " ")),
        unsafe_allow_html=True,
    )
    cB.markdown(
        chip(prefix + "Net", f"{net:,.2f} €".replace(",", " "), f"{net_nuit:,.2f} €/nuit".replace(",", " ")),
        unsafe_allow_html=True,
    )
    cC.markdown(chip(prefix + "Charges", f"{ch:,.2f} €".replace(",", " ")), unsafe_allow_html=True)
    cD.markdown(chip(prefix + "Nuitées", f"{int(nts)}"), unsafe_allow_html=True)
    cE.markdown(chip(prefix + "Commission moy.", f"{pct_mean:.2f} %"), unsafe_allow_html=True)

# Compat : si ailleurs tu utilises metrics_bar_from_df(...)
metrics_bar_from_df = metrics_bar_compact

def render_cache_button_sidebar():
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.sidebar.success("Cache vidé. Redémarrage…")
        st.rerun()

# ==============================  UTILS / SCHEMA  ===========================

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
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()

    # Dates pures
    for col in ["date_arrivee", "date_depart"]:
        if col in df.columns:
            df[col] = df[col].apply(to_date_only)

    # Numériques
    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Calcul charges / %
    if "prix_brut" in df.columns and "prix_net" in df.columns:
        if "charges" not in df.columns:
            df["charges"] = df["prix_brut"] - df["prix_net"]
        if "%" not in df.columns:
            with pd.option_context("mode.use_inf_as_na", True):
                df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    # Nuitées
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else None
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

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

    # Téléphone : on enlève une éventuelle apostrophe Excel (on la remettra à l’export)
    if "telephone" in df.columns:
        def _clean_tel(x):
            s = "" if pd.isna(x) else str(x).strip()
            if s.startswith("'"):
                s = s[1:]
            return s
        df["telephone"] = df["telephone"].apply(_clean_tel)

    if "ical_uid" not in df.columns:
        df["ical_uid"] = ""

    cols_order = [
        "nom_client",
        "plateforme",
        "telephone",
        "date_arrivee",
        "date_depart",
        "nuitees",
        "prix_brut",
        "prix_net",
        "charges",
        "%",
        "AAAA",
        "MM",
        "ical_uid",
    ]
    ordered = [c for c in cols_order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

def _marque_totaux(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series([], dtype=bool)
    mask = pd.Series(False, index=df.index)
    for col in ["nom_client", "plateforme"]:
        if col in df.columns:
            mask |= df[col].astype(str).str.strip().str.lower().eq("total")
    has_no_dates = pd.Series(True, index=df.index)
    for c in ["date_arrivee", "date_depart"]:
        if c in df.columns:
            has_no_dates &= df[c].isna()
    has_money = pd.Series(False, index=df.index)
    for c in ["prix_brut", "prix_net", "charges"]:
        if c in df.columns:
            has_money |= df[c].notna()
    return mask | (has_no_dates & has_money)

def _trier_et_recoller_totaux(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    tot_mask = _marque_totaux(df)
    df_total = df[tot_mask].copy()
    df_core = df[~tot_mask].copy()
    by_cols = [c for c in ["date_arrivee", "nom_client"] if c in df_core.columns]
    if by_cols:
        df_core = df_core.sort_values(by=by_cols, na_position="last").reset_index(drop=True)
    return pd.concat([df_core, df_total], ignore_index=True)

# ==============================  EXCEL I/O  ================================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path)

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return pd.DataFrame()
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        df = ensure_schema(df)
        df = _trier_et_recoller_totaux(df)
        return df
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return pd.DataFrame()

def sauvegarder_donnees(df: pd.DataFrame):
    df = _trier_et_recoller_totaux(ensure_schema(df))
    df_to_save = df.copy()
    if "telephone" in df_to_save.columns:
        def _to_excel_text(s):
            s = "" if pd.isna(s) else str(s).strip()
            if s and not s.startswith("'"):
                s = "'" + s
            return s
        df_to_save["telephone"] = df_to_save["telephone"].apply(_to_excel_text)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as writer:
            df_to_save.to_excel(writer, index=False)
        st.cache_data.clear()
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

# ==============================  LIENS / SMS UTILS  ========================

def clean_tel_display(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^\d\+ ]", "", s)
    return s

def tel_to_uri(s: str) -> str:
    s = clean_tel_display(s)
    if not s:
        return ""
    s_uri = re.sub(r"[ \-\.]", "", s)
    return f"tel:{s_uri}"

def sms_message(row: pd.Series) -> str:
    """Modèle d’SMS d’accueil (utilisé pour lien SMS)."""
    nom = str(row.get("nom_client") or "").strip()
    plateforme = str(row.get("plateforme") or "").strip()
    d1 = row.get("date_arrivee")
    d2 = row.get("date_depart")
    nuitees = row.get("nuitees")
    d1s = d1.strftime("%Y/%m/%d") if isinstance(d1, date) else ""
    d2s = d2.strftime("%Y/%m/%d") if isinstance(d2, date) else ""
    txt = (
        f"VILLA TOBIAS - Plateforme : {plateforme}\n"
        f"Date d'arrivee : {d1s}  Date depart : {d2s}  Nombre de nuitees : {nuitees}\n\n"
        f"Bonjour {nom}\n\n"
        "Nous sommes heureux de vous accueillir prochainement et vous prions de bien vouloir nous communiquer votre heure d'arrivee. "
        "Nous vous attendrons sur place pour vous remettre les cles de l'appartement et vous indiquer votre emplacement de parking. "
        "Nous vous souhaitons un bon voyage et vous disons a demain.\n\n"
        "Annick & Charley"
    )
    return txt

# ==============================  VUES  =====================================

def vue_en_cours_banner(df: pd.DataFrame):
    """Séjours en cours aujourd’hui (une seule fois chaque colonne)."""
    if df is None or df.empty:
        return
    dft = ensure_schema(df).copy()
    if dft.empty:
        return

    mask_total = _marque_totaux(dft)
    today = date.today()
    def _is_date(x): return isinstance(x, date)

    en_cours = dft[
        (~mask_total)
        & dft["date_arrivee"].apply(_is_date)
        & dft["date_depart"].apply(_is_date)
        & (dft["date_arrivee"] <= today)
        & (dft["date_depart"] > today)
    ].copy()

    st.markdown("### 🟢 En cours aujourd’hui")
    if en_cours.empty:
        st.info(f"Aucun séjour en cours aujourd’hui ({today.strftime('%Y/%m/%d')}).")
        return

    en_cours = en_cours.sort_values(["date_depart", "nom_client"]).copy()
    en_cours["date_arrivee"] = en_cours["date_arrivee"].apply(lambda d: d.strftime("%Y/%m/%d"))
    en_cours["date_depart"] = en_cours["date_depart"].apply(lambda d: d.strftime("%Y/%m/%d"))

    def _make_links(row):
        tel_raw = str(row.get("telephone") or "").strip()
        tel_ui = tel_to_uri(tel_raw)
        sms_txt = sms_message(row)
        tel_clean = re.sub(r"[ \-\.]", "", clean_tel_display(tel_raw))
        sms_uri = f"sms:{tel_clean}?&body={quote(sms_txt)}" if tel_clean else ""
        link_tel = f'<a href="{tel_ui}">📞 Appeler</a>' if tel_ui else ""
        link_sms = f'<a href="{sms_uri}">📲 SMS</a>' if sms_uri else ""
        return link_tel, link_sms

    links = en_cours.apply(_make_links, axis=1, result_type="expand")
    en_cours["📞 Appeler"] = links[0]
    en_cours["📲 SMS"] = links[1]

    colonnes = ["plateforme", "nom_client", "date_arrivee", "date_depart", "nuitees", "📞 Appeler", "📲 SMS"]
    colonnes = [c for c in colonnes if c in en_cours.columns]
    out = en_cours.loc[:, colonnes].copy()
    st.markdown(out.to_html(index=False, escape=False), unsafe_allow_html=True)

def vue_reservations(df: pd.DataFrame):
    header("📋 Réservations", "Filtrez, exportez, modifiez en un clin d’œil")
    vue_en_cours_banner(df)

    show = _trier_et_recoller_totaux(ensure_schema(df)).copy()
    if show.empty:
        st.info("Aucune réservation.")
        return

    for col in ["date_arrivee", "date_depart"]:
        if col in show.columns:
            show[col] = show[col].apply(format_date_str)

    st.dataframe(show, use_container_width=True)
    metrics_bar_compact(show, prefix="Total ")

def vue_ajouter(df: pd.DataFrame):
    header("➕ Ajouter une réservation", "Saisie rapide avec calcul auto des charges et %")
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
            "ical_uid": "",
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        df2 = _trier_et_recoller_totaux(df2)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    header("✏️ Modifier / Supprimer", "Mettez à jour vos réservations")
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
        plateformes = ["Booking", "Airbnb", "Autre"]
        index_pf = plateformes.index(df.at[i, "plateforme"]) if df.at[i, "plateforme"] in plateformes else 2
        plateforme = st.selectbox("Plateforme", plateformes, index=index_pf)
        tel = st.text_input("Téléphone", df.at[i, "telephone"] if "telephone" in df.columns else "")
        arrivee = st.date_input(
            "Arrivée", df.at[i, "date_arrivee"] if isinstance(df.at[i, "date_arrivee"], date) else date.today()
        )
        depart = st.date_input(
            "Départ",
            df.at[i, "date_depart"] if isinstance(df.at[i, "date_depart"], date) else arrivee + timedelta(days=1),
        )
        brut = st.number_input(
            "Prix brut (€)", value=float(df.at[i, "prix_brut"]) if pd.notna(df.at[i, "prix_brut"]) else 0.0, format="%.2f"
        )
        net = st.number_input(
            "Prix net (€)",
            value=float(df.at[i, "prix_net"]) if pd.notna(df.at[i, "prix_net"]) else 0.0,
            max_value=max(0.0, float(brut)),
            format="%.2f",
        )
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
    header("📅 Calendrier", "Vue mensuelle avec repérage rapide des séjours")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    # Filtres compacts sur une seule ligne
    c_mois, c_annee = st.columns([2, 1])
    with c_mois:
        mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, (date.today().month - 1)))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    with c_annee:
        annee = st.selectbox("Année", annees, index=max(0, len(annees) - 1))

    mois_index = list(calendar.month_name).index(mois_nom)

    # Génération des jours du mois
    jours = [date(annee, mois_index, j + 1) for j in range(calendar.monthrange(annee, mois_index)[1])]
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

    # Tableau semainier
    table = []
    for semaine in calendar.monthcalendar(annee, mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                d = date(annee, mois_index, jour)
                contenu = f"**{jour:02d}**\n" + "\n".join(planning.get(d, []))
                ligne.append(contenu)
        table.append(ligne)

    st.table(pd.DataFrame(table, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

def vue_rapport(df: pd.DataFrame):
    header("📊 Rapport (1 année)", "Filtres et graphiques triés 01 → 12")
    df = _trier_et_recoller_totaux(ensure_schema(df)).copy()
    if df.empty:
        st.info("Aucune donnée.")
        return

    if "AAAA" not in df.columns or "MM" not in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
        df["MM"] = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)

    df["AAAA"] = pd.to_numeric(df["AAAA"], errors="coerce")
    df["MM"] = pd.to_numeric(df["MM"], errors="coerce")
    df = df.dropna(subset=["AAAA", "MM"]).copy()
    df["AAAA"] = df["AAAA"].astype(int)
    df["MM"] = df["MM"].astype(int)

    annees = sorted(df["AAAA"].unique().tolist())
    if not annees:
        st.info("Aucune année disponible.")
        return
    annee = st.selectbox("Année", annees, index=len(annees) - 1, key="rapport_annee")

    data = df[df["AAAA"] == int(annee)].copy()

    plateformes = ["Toutes"] + sorted(data["plateforme"].dropna().unique().tolist())
    col1, col2 = st.columns(2)
    with col1:
        filtre_plateforme = st.selectbox("Plateforme", plateformes, key="rapport_pf")
    with col2:
        filtre_mois_label = st.selectbox("Mois (01–12)", ["Tous"] + [f"{i:02d}" for i in range(1, 13)], key="rapport_mois")

    if filtre_plateforme != "Toutes":
        data = data[data["plateforme"] == filtre_plateforme]
    if filtre_mois_label != "Tous":
        data = data[data["MM"] == int(filtre_mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    data = data[(data["MM"] >= 1) & (data["MM"] <= 12)]
    # Ajouter prix/nuit pour l’aperçu tabulaire
    data["prix_brut/nuit"] = (pd.to_numeric(data["prix_brut"], errors="coerce") / data["nuitees"]).replace([np.inf, -np.inf], np.nan).fillna(0).round(2)
    data["prix_net/nuit"] = (pd.to_numeric(data["prix_net"], errors="coerce") / data["nuitees"]).replace([np.inf, -np.inf], np.nan).fillna(0).round(2)

    stats = (
        data.groupby(["MM", "plateforme"], dropna=True)
        .agg(
            prix_brut=("prix_brut", "sum"),
            prix_net=("prix_net", "sum"),
            charges=("charges", "sum"),
            nuitees=("nuitees", "sum"),
        )
        .reset_index()
    )
    if stats.empty:
        st.info("Aucune donnée après agrégation.")
        return

    plats = sorted(stats["plateforme"].unique().tolist())
    full = []
    for m in range(1, 13):
        for p in plats:
            row = stats[(stats["MM"] == m) & (stats["plateforme"] == p)]
            if row.empty:
                full.append({"MM": m, "plateforme": p, "prix_brut": 0.0, "prix_net": 0.0, "charges": 0.0, "nuitees": 0})
            else:
                full.append(row.iloc[0].to_dict())
    stats = pd.DataFrame(full).sort_values(["MM", "plateforme"]).reset_index(drop=True)

    # Tableau des stats (avec suppression des lignes tout à 0)
    stats_view = stats.copy()
    mask_non_zero = (stats_view[["prix_brut", "prix_net", "charges", "nuitees"]].sum(axis=1) != 0)
    stats_view = stats_view[mask_non_zero]
    st.dataframe(
        stats_view.rename(columns={"MM": "Mois"})[["Mois", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]],
        use_container_width=True,
    )

    metrics_bar_compact(data, prefix="Total ")

    # Graphes matplotlib : X = 1..12 (toujours ordonné)
    def plot_grouped_bars(metric: str, title: str, ylabel: str):
        months = list(range(1, 13))
        base_x = np.arange(len(months), dtype=float)
        plats_sorted = sorted(plats)
        width = 0.8 / max(1, len(plats_sorted))

        fig, ax = plt.subplots(figsize=(10, 4))
        for i, p in enumerate(plats_sorted):
            sub = stats[stats["plateforme"] == p]
            vals = {int(mm): float(v) for mm, v in zip(sub["MM"], sub[metric])}
            y = np.array([vals.get(m, 0.0) for m in months], dtype=float)
            x = base_x + (i - (len(plats_sorted) - 1) / 2) * width
            ax.bar(x, y, width=width, label=p)

        ax.set_xlim(-0.5, 11.5)
        ax.set_xticks(base_x)
        ax.set_xticklabels([f"{m:02d}" for m in months])
        ax.set_xlabel(f"Mois ({annee})")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(loc="upper left", frameon=False)
        ax.grid(axis="y", linestyle="--", alpha=0.3)

        st.pyplot(fig)
        plt.close(fig)

    plot_grouped_bars("prix_brut", "💰 Revenus bruts", "€")
    plot_grouped_bars("charges", "💸 Charges", "€")
    plot_grouped_bars("nuitees", "🛌 Nuitées", "Nuitées")

def vue_clients(df: pd.DataFrame):
    header("👥 Liste des clients", "Export et calculs par nuitée")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = st.selectbox("Année", annees) if annees else None
    mois = st.selectbox("Mois", ["Tous"] + list(range(1, 13)))

    data = df.copy()
    if annee:
        data = data[data["AAAA"] == annee]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]
    if data.empty:
        st.info("Aucune donnée pour cette période.")
        return

    with pd.option_context("mode.use_inf_as_na", True):
        if "nuitees" in data.columns and "prix_brut" in data.columns:
            data["prix_brut/nuit"] = (data["prix_brut"] / data["nuitees"]).round(2).fillna(0)
        if "nuitees" in data.columns and "prix_net" in data.columns:
            data["prix_net/nuit"] = (data["prix_net"] / data["nuitees"]).round(2).fillna(0)

    cols = [
        "nom_client",
        "plateforme",
        "date_arrivee",
        "date_depart",
        "nuitees",
        "prix_brut",
        "prix_net",
        "charges",
        "%",
        "prix_brut/nuit",
        "prix_net/nuit",
        "telephone",
    ]
    cols = [c for c in cols if c in data.columns]

    show = data.copy()
    for c in ["date_arrivee", "date_depart"]:
        if c in show.columns:
            show[c] = show[c].apply(format_date_str)

    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger la liste (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv",
    )

# ==============================  APP  ======================================

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    inject_css()
    render_cache_button_sidebar()

    st.sidebar.title("📁 Fichier")
    bouton_restaurer()
    df = charger_donnees()
    bouton_telecharger(df)

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations", "➕ Ajouter", "✏️ Modifier / Supprimer", "📅 Calendrier", "📊 Rapport", "👥 Liste clients"],
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

if __name__ == "__main__":
    main()