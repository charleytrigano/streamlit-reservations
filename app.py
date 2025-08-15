# app.py — Villa Tobias (COMPLET, nouveaux champs + couleurs plateformes)
# Compatible avec l'ancien schéma (prix_brut/prix_net/charges/%) et le nouveau
# (montant_net, commissions, frais_cb, montant_brut, menage, taxes_sejour, base, %)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime
from io import BytesIO
import os
import matplotlib.pyplot as plt

FICHIER = "reservations.xlsx"

# ==============================  COULEURS PLATEFORMES  ==============================

DEFAULT_PLATFORM_COLORS = {
    "Booking": "#1e90ff",
    "Airbnb": "#00b894",
    "Autre": "#ff9f43",
}

def get_platform_colors():
    if "platform_colors" not in st.session_state:
        st.session_state.platform_colors = DEFAULT_PLATFORM_COLORS.copy()
    return st.session_state.platform_colors

def platform_color(name: str) -> str:
    colors = get_platform_colors()
    return colors.get(name, "#888888")

def platform_manager_sidebar():
    st.sidebar.markdown("## 🎨 Plateformes & couleurs")
    colors = get_platform_colors()
    # Affichage existant
    if colors:
        for k, v in colors.items():
            st.sidebar.markdown(f"- <span style='display:inline-block;width:12px;height:12px;background:{v};border-radius:3px;margin-right:6px'></span>**{k}**", unsafe_allow_html=True)

    with st.sidebar.expander("Ajouter / modifier une plateforme"):
        new_name = st.text_input("Nom de la plateforme", key="pf_new_name")
        new_col = st.color_picker("Couleur", value="#888888", key="pf_new_color")
        if st.button("Ajouter / Mettre à jour la plateforme"):
            if new_name.strip():
                st.session_state.platform_colors[new_name.strip()] = new_col
                st.success(f"Plateforme '{new_name.strip()}' mise à jour.")
            else:
                st.warning("Nom de plateforme vide.")

# ==============================  MAINTENANCE / CACHE  ==============================

def render_cache_section_sidebar():
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.sidebar.success("Cache vidé. Redémarrage…")
        st.rerun()

# ==============================  OUTILS  ==============================

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
    """Lecture du téléphone en texte, enlève .0, garde le +, supprime espaces."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

def is_total_row(row: pd.Series) -> bool:
    name_is_total = str(row.get("nom_client","")).strip().lower() == "total"
    pf_is_total   = str(row.get("plateforme","")).strip().lower() == "total"
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    no_dates = not isinstance(d1, date) and not isinstance(d2, date)
    has_money = any(pd.notna(row.get(c)) and float(row.get(c) or 0) != 0 for c in ["prix_brut","prix_net","charges"])
    return name_is_total or pf_is_total or (no_dates and has_money)

def split_totals(df: pd.DataFrame):
    if df is None or df.empty:
        return df, df
    mask = df.apply(is_total_row, axis=1)
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    by = [c for c in ["date_arrivee","nom_client"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)

# ==============================  SCHEMA (Compat ancien+nouv.)  ==============================

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Supporte l'ancien schéma (prix_brut/prix_net/charges/%) et le nouveau
    (montant_net, commissions, frais_cb, montant_brut, menage, taxes_sejour, base, %).
    Ne supprime rien ; complète ce qui manque ; garde la compat pour rapports/calendrier.
    """
    base_cols = [
        "nom_client","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        # ancien schéma:
        "prix_brut","prix_net","charges","%",
        # nouveau schéma:
        "montant_net","commissions","frais_cb","montant_brut","menage","taxes_sejour","base",
        # horodatage / extra:
        "AAAA","MM","ical_uid","commentaire"
    ]

    if df is None or df.empty:
        return pd.DataFrame(columns=base_cols)

    df = df.copy()

    # Dates -> date
    for c in ["date_arrivee","date_depart"]:
        if c in df.columns:
            df[c] = df[c].apply(to_date_only)

    # Téléphone
    if "telephone" in df.columns:
        df["telephone"] = df["telephone"].apply(normalize_tel)

    # Créer colonnes manquantes
    for c in base_cols:
        if c not in df.columns:
            df[c] = pd.NA

    # Numériques
    num_cols = ["prix_brut","prix_net","charges","%",
                "montant_net","commissions","frais_cb","montant_brut","menage","taxes_sejour","base","nuitees"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # AAAA/MM depuis date_arrivee
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)

    # Nuité(e)s
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else pd.NA
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

    # === MAPPAGE ANCIEN -> NOUVEAU si nécessaire ===
    need_new = df["montant_net"].isna() & df["montant_brut"].isna()
    if need_new.any():
        # montant_net ≈ ancien prix_brut (brut côté plateforme)
        df.loc[need_new & df["prix_brut"].notna(), "montant_net"] = df.loc[need_new, "prix_brut"]
        # commissions+frais_cb ≈ charges (si pas détaillé)
        df.loc[need_new & df["charges"].notna(), "commissions"] = df.loc[need_new, "charges"]
        df.loc[need_new, "frais_cb"] = df.loc[need_new, "frais_cb"].fillna(0)
        # montant_brut ≈ ancien prix_net (net reçu)
        df.loc[need_new & df["prix_net"].notna(), "montant_brut"] = df.loc[need_new, "prix_net"]
        # menage/taxes par défaut 0
        df.loc[need_new & df["menage"].isna(), "menage"] = 0.0
        df.loc[need_new & df["taxes_sejour"].isna(), "taxes_sejour"] = 0.0

    # Compléter nouveau schéma
    mask_mb = df["montant_brut"].isna() & df["montant_net"].notna()
    df.loc[mask_mb, "montant_brut"] = (
        df.loc[mask_mb, "montant_net"].fillna(0)
        - df.loc[mask_mb, "commissions"].fillna(0)
        - df.loc[mask_mb, "frais_cb"].fillna(0)
    )

    mask_base = df["base"].isna() & df["montant_brut"].notna()
    df.loc[mask_base, "base"] = (
        df.loc[mask_base, "montant_brut"].fillna(0)
        - df.loc[mask_base, "menage"].fillna(0)
        - df.loc[mask_base, "taxes_sejour"].fillna(0)
    )

    # % nouveau = (commissions+frais_cb)/montant_net*100
    mask_pct_new = df["montant_net"].notna() & (df["montant_net"] != 0)
    df.loc[mask_pct_new, "%"] = (
        (df.loc[mask_pct_new, "commissions"].fillna(0) + df.loc[mask_pct_new, "frais_cb"].fillna(0))
        / df.loc[mask_pct_new, "montant_net"].replace(0, pd.NA) * 100
    )

    # === MAPPAGE NOUVEAU -> ANCIEN pour compat ===
    # prix_brut ≈ montant_net ; prix_net ≈ montant_brut ; charges ≈ commissions+frais_cb
    if df["prix_brut"].isna().any() and df["montant_net"].notna().any():
        df.loc[df["prix_brut"].isna(), "prix_brut"] = df.loc[df["prix_brut"].isna(), "montant_net"]
    if df["prix_net"].isna().any() and df["montant_brut"].notna().any():
        df.loc[df["prix_net"].isna(), "prix_net"] = df.loc[df["prix_net"].isna(), "montant_brut"]
    mask_ch = df["charges"].isna() & (df["commissions"].notna() | df["frais_cb"].notna())
    df.loc[mask_ch, "charges"] = df.loc[mask_ch, ["commissions","frais_cb"]].fillna(0).sum(axis=1)

    # % ancien si vide → charges/prix_brut*100
    mask_pct_old = df["%"].isna() & df["prix_brut"].notna() & (df["prix_brut"] != 0)
    df.loc[mask_pct_old, "%"] = (df.loc[mask_pct_old, "charges"].fillna(0) / df.loc[mask_pct_old, "prix_brut"]) * 100

    # Arrondis
    for c in ["prix_brut","prix_net","charges","%","montant_net","commissions","frais_cb","montant_brut","menage","taxes_sejour","base"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round(2)

    ordered = [c for c in base_cols if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

# ==============================  EXCEL I/O  ==============================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, converters={"telephone": normalize_tel})

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="Sheet1")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            df_new = pd.read_excel(up, converters={"telephone": normalize_tel})
            df_new = ensure_schema(df_new)
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    try:
        ensure_schema(df).to_excel(buf, index=False, engine="openpyxl")
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = None
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx if data_xlsx else b"",
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(data_xlsx is None),
    )

# ==============================  TOTAUX UI  ==============================

def totaux_chips(total_brut, total_net, total_chg, total_nuits, pct_moy):
    return f"""
<style>
.chips-wrap {{ display:flex; flex-wrap:wrap; gap:12px; margin:8px 0 16px 0; }}
.chip {{ padding:10px 12px; border-radius:10px; background: rgba(127,127,127,0.12); border: 1px solid rgba(127,127,127,0.25); }}
.chip b {{ display:block; margin-bottom:4px; }}
</style>
<div class="chips-wrap">
  <div class="chip"><b>Total Brut</b><div>{total_brut:,.2f} €</div></div>
  <div class="chip"><b>Total Net</b><div>{total_net:,.2f} €</div></div>
  <div class="chip"><b>Total Charges</b><div>{total_chg:,.2f} €</div></div>
  <div class="chip"><b>Total Nuitées</b><div>{int(total_nuits) if pd.notna(total_nuits) else 0}</div></div>
  <div class="chip"><b>Commission moy.</b><div>{pct_moy:.2f} %</div></div>
</div>
"""

# ==============================  VUES  ==============================

def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)

    # Totaux (sur core)
    if not core.empty:
        total_brut   = core["prix_brut"].sum(skipna=True)
        total_net    = core["prix_net"].sum(skipna=True)
        total_chg    = core["charges"].sum(skipna=True)
        total_nuits  = core["nuitees"].sum(skipna=True)
        pct_moy = (core["charges"].sum() / core["prix_brut"].sum() * 100) if core["prix_brut"].sum() else 0
        st.markdown(totaux_chips(total_brut, total_net, total_chg, total_nuits, pct_moy), unsafe_allow_html=True)

    show = pd.concat([core, totals], ignore_index=True)
    for c in ["date_arrivee","date_depart"]:
        show[c] = show[c].apply(format_date_str)
    st.dataframe(show, use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    st.caption("Saisie rapide")

    c1, c2 = st.columns(2)
    nom = c1.text_input("Nom du client")
    tel = c2.text_input("Téléphone (+33...)", value="")

    colors = get_platform_colors()
    pf_list = sorted(colors.keys())
    c3, c4 = st.columns(2)
    plateforme = c3.selectbox("Plateforme", pf_list, index=pf_list.index("Autre") if "Autre" in pf_list else 0)
    # Option pour écrire un nom non listé
    pf_new = c4.text_input("Ou autre plateforme (nouvelle)")
    if pf_new.strip():
        plateforme = pf_new.strip()
        if plateforme not in colors:
            st.session_state.platform_colors[plateforme] = "#888888"

    c5, c6 = st.columns(2)
    arrivee = c5.date_input("Date d’arrivée", value=date.today())
    depart  = c6.date_input("Date de départ", value=arrivee + timedelta(days=1), min_value=arrivee + timedelta(days=1))

    st.markdown("#### 💶 Détails financiers (nouveau schéma)")
    g1, g2, g3 = st.columns(3)
    montant_net = g1.number_input("Montant NET (plateforme)", min_value=0.0, step=1.0, format="%.2f")
    commissions = g2.number_input("Commissions", min_value=0.0, step=0.5, format="%.2f")
    frais_cb    = g3.number_input("Frais CB", min_value=0.0, step=0.5, format="%.2f")

    # Dérivés
    montant_brut = max(montant_net - commissions - frais_cb, 0.0)

    h1, h2 = st.columns(2)
    menage = h1.number_input("Ménage", min_value=0.0, step=1.0, format="%.2f", value=0.0)
    taxes  = h2.number_input("Taxes de séjour", min_value=0.0, step=0.5, format="%.2f", value=0.0)

    base_calc = max(montant_brut - menage - taxes, 0.0)
    pct_calc  = ((commissions + frais_cb) / montant_net * 100) if montant_net > 0 else 0.0

    st.markdown(f"- **Montant BRUT (reçu)** : {montant_brut:.2f} €  \n- **Base (après ménage + taxes)** : {base_calc:.2f} €  \n- **% Commission** : {pct_calc:.2f} %")

    if st.button("Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return

        # Remplir aussi l'ancien schéma (compat)
        prix_brut = montant_net
        prix_net  = montant_brut
        charges   = commissions + frais_cb

        ligne = {
            "nom_client": (nom or "").strip(),
            "plateforme": plateforme,
            "telephone": normalize_tel(tel),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "nuitees": (depart - arrivee).days,
            # ancien schéma (compat)
            "prix_brut": prix_brut,
            "prix_net": prix_net,
            "charges": round(charges, 2),
            "%": round((charges / prix_brut * 100) if prix_brut else 0, 2),
            # nouveau schéma
            "montant_net": montant_net,
            "commissions": commissions,
            "frais_cb": frais_cb,
            "montant_brut": montant_brut,
            "menage": menage,
            "taxes_sejour": taxes,
            "base": base_calc,
            # extra
            "AAAA": arrivee.year,
            "MM": arrivee.month,
            "ical_uid": "",
            "commentaire": ""
        }

        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
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

    # Identité
    c1, c2 = st.columns(2)
    nom = c1.text_input("Nom du client", df.at[i, "nom_client"])
    tel = c2.text_input("Téléphone", normalize_tel(df.at[i, "telephone"]))

    # Plateforme
    colors = get_platform_colors()
    pf_list = sorted(colors.keys())
    pf_current = df.at[i, "plateforme"] if pd.notna(df.at[i, "plateforme"]) else "Autre"
    pf_idx = pf_list.index(pf_current) if pf_current in pf_list else 0
    c3, c4 = st.columns(2)
    plateforme = c3.selectbox("Plateforme", pf_list, index=pf_idx)
    pf_new = c4.text_input("Ou autre plateforme (nouvelle)")
    if pf_new.strip():
        plateforme = pf_new.strip()
        if plateforme not in colors:
            st.session_state.platform_colors[plateforme] = "#888888"

    # Dates
    d1, d2 = st.columns(2)
    arrivee = d1.date_input("Arrivée", df.at[i,"date_arrivee"] if isinstance(df.at[i,"date_arrivee"], date) else date.today())
    depart  = d2.date_input("Départ",  df.at[i,"date_depart"] if isinstance(df.at[i,"date_depart"], date) else arrivee + timedelta(days=1),
                            min_value=arrivee + timedelta(days=1))

    # Nouveau schéma
    st.markdown("#### 💶 Détails financiers (nouveau schéma)")
    g1, g2, g3 = st.columns(3)
    montant_net = g1.number_input("Montant NET (plateforme)", min_value=0.0, step=1.0, format="%.2f",
                                  value=float(df.at[i,"montant_net"]) if pd.notna(df.at[i,"montant_net"]) else 0.0)
    commissions = g2.number_input("Commissions", min_value=0.0, step=0.5, format="%.2f",
                                  value=float(df.at[i,"commissions"]) if pd.notna(df.at[i,"commissions"]) else 0.0)
    frais_cb    = g3.number_input("Frais CB", min_value=0.0, step=0.5, format="%.2f",
                                  value=float(df.at[i,"frais_cb"]) if pd.notna(df.at[i,"frais_cb"]) else 0.0)

    montant_brut = max(montant_net - commissions - frais_cb, 0.0)
    h1, h2 = st.columns(2)
    menage = h1.number_input("Ménage", min_value=0.0, step=1.0, format="%.2f",
                             value=float(df.at[i,"menage"]) if pd.notna(df.at[i,"menage"]) else 0.0)
    taxes  = h2.number_input("Taxes de séjour", min_value=0.0, step=0.5, format="%.2f",
                             value=float(df.at[i,"taxes_sejour"]) if pd.notna(df.at[i,"taxes_sejour"]) else 0.0)

    base_calc = max(montant_brut - menage - taxes, 0.0)
    pct_calc  = ((commissions + frais_cb) / montant_net * 100) if montant_net > 0 else 0.0

    st.markdown(f"- **Montant BRUT (reçu)** : {montant_brut:.2f} €  \n- **Base** : {base_calc:.2f} €  \n- **% Commission** : {pct_calc:.2f} %")

    csave, cdel = st.columns(2)
    if csave.button("💾 Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return

        # Ancien schéma (compat)
        prix_brut = montant_net
        prix_net  = montant_brut
        charges   = commissions + frais_cb

        df.at[i,"nom_client"] = nom.strip()
        df.at[i,"plateforme"] = plateforme
        df.at[i,"telephone"]  = normalize_tel(tel)
        df.at[i,"date_arrivee"] = arrivee
        df.at[i,"date_depart"]  = depart
        df.at[i,"nuitees"] = (depart - arrivee).days

        # ancien
        df.at[i,"prix_brut"] = prix_brut
        df.at[i,"prix_net"]  = prix_net
        df.at[i,"charges"]   = round(charges, 2)
        df.at[i,"%"]         = round((charges / prix_brut * 100) if prix_brut else 0, 2)

        # nouveau
        df.at[i,"montant_net"]  = montant_net
        df.at[i,"commissions"]  = commissions
        df.at[i,"frais_cb"]     = frais_cb
        df.at[i,"montant_brut"] = montant_brut
        df.at[i,"menage"]       = menage
        df.at[i,"taxes_sejour"] = taxes
        df.at[i,"base"]         = base_calc

        df.at[i,"AAAA"] = arrivee.year
        df.at[i,"MM"]   = arrivee.month

        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df)
        st.success("✅ Réservation modifiée")
        st.rerun()

    if cdel.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("🗑 Réservation supprimée")
        st.rerun()

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier mensuel")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    cols = st.columns(2)
    mois_nom = cols[0].selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = cols[1].selectbox("Année", annees, index=len(annees)-1)

    mois_index = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, mois_index)[1]
    jours = [date(annee, mois_index, j+1) for j in range(nb_jours)]
    planning = {j: [] for j in jours}

    core, _ = split_totals(df)
    for _, row in core.iterrows():
        d1 = row["date_arrivee"]; d2 = row["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        for j in jours:
            if d1 <= j < d2:
                planning[j].append((row['plateforme'], row['nom_client']))

    # Rendu HTML simple avec pastilles couleur
    grid = "<style>.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}.day{border:1px solid rgba(127,127,127,.3);border-radius:8px;padding:6px;min-height:72px}.dt{font-weight:600}.tag{display:inline-flex;align-items:center;gap:6px;margin:2px 0}.dot{width:8px;height:8px;border-radius:50%}</style>"
    grid += "<div class='cal'>"
    for lab in ["L","M","M","J","V","S","D"]:
        grid += f"<div class='day' style='background:rgba(127,127,127,.06)'><div class='dt'>{lab}</div></div>"
    cal_weeks = calendar.monthcalendar(annee, mois_index)
    # Alignement sur Lundi=0
    for week in cal_weeks:
        for j in week:
            if j == 0:
                grid += "<div class='day'></div>"
            else:
                d = date(annee, mois_index, j)
                items = planning.get(d, [])
                inner = "".join([f"<div class='tag'><span class='dot' style='background:{platform_color(pf)}'></span><span>{pf} — {nm}</span></div>" for pf, nm in items])
                grid += f"<div class='day'><div class='dt'>{j}</div>{inner}</div>"
    grid += "</div>"
    st.markdown(grid, unsafe_allow_html=True)

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport (une année à la fois)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    if "AAAA" not in df.columns or "MM" not in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)

    df["AAAA"] = pd.to_numeric(df["AAAA"], errors="coerce")
    df["MM"]   = pd.to_numeric(df["MM"], errors="coerce")
    df = df.dropna(subset=["AAAA","MM"]).copy()
    df["AAAA"] = df["AAAA"].astype(int)
    df["MM"]   = df["MM"].astype(int)

    annees = sorted(df["AAAA"].unique().tolist())
    if not annees:
        st.info("Aucune année disponible.")
        return

    # Filtres alignés sur une ligne
    c1, c2, c3 = st.columns(3)
    annee = c1.selectbox("Année", annees, index=len(annees)-1, key="rapport_annee")
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    filtre_plateforme = c2.selectbox("Plateforme", pf_opt, key="rapport_pf")
    filtre_mois_label = c3.selectbox("Mois (01–12)", ["Tous"] + [f"{i:02d}" for i in range(1,13)], key="rapport_mois")

    data = df[df["AAAA"] == int(annee)].copy()
    if filtre_plateforme != "Toutes":
        data = data[data["plateforme"] == filtre_plateforme]
    if filtre_mois_label != "Tous":
        data = data[data["MM"] == int(filtre_mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # Détail (avec noms)
    detail = data.copy()
    for c in ["date_arrivee","date_depart"]:
        detail[c] = detail[c].apply(format_date_str)
    by = [c for c in ["date_arrivee","nom_client"] if c in detail.columns]
    if by:
        detail = detail.sort_values(by=by, na_position="last").reset_index(drop=True)

    cols_detail = [
        "nom_client","plateforme","telephone","date_arrivee","date_depart","nuitees",
        "montant_net","commissions","frais_cb","montant_brut","menage","taxes_sejour","base",
        "prix_brut","prix_net","charges","%"
    ]
    cols_detail = [c for c in cols_detail if c in detail.columns]
    st.dataframe(detail[cols_detail], use_container_width=True)

    # Totaux
    total_brut   = data["prix_brut"].sum(skipna=True)
    total_net    = data["prix_net"].sum(skipna=True)
    total_chg    = data["charges"].sum(skipna=True)
    total_nuits  = data["nuitees"].sum(skipna=True)
    pct_moy = (data["charges"].sum() / data["prix_brut"].sum() * 100) if data["prix_brut"].sum() else 0
    st.markdown(totaux_chips(total_brut, total_net, total_chg, total_nuits, pct_moy), unsafe_allow_html=True)

    # Agrégats par mois/plateforme
    stats = (
        data.groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 charges=("charges","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
    )
    stats = stats.sort_values(["MM","plateforme"]).reset_index(drop=True)

    plats = sorted(stats["plateforme"].unique().tolist())
    months = list(range(1, 13))
    base_x = np.arange(len(months), dtype=float)
    width = 0.8 / max(1, len(plats))

    def plot_grouped_bars(metric: str, title: str, ylabel: str):
        fig, ax = plt.subplots(figsize=(10, 4))
        for i, p in enumerate(plats):
            sub = stats[stats["plateforme"] == p]
            vals = {int(mm): float(v) for mm, v in zip(sub["MM"], sub[metric])}
            y = np.array([vals.get(m, 0.0) for m in months], dtype=float)
            x = base_x + (i - (len(plats)-1)/2) * width
            ax.bar(x, y, width=width, label=p, color=platform_color(p))
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
    st.title("👥 Liste des clients")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    c1, c2 = st.columns(2)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", annees, index=len(annees)-1) if annees else None
    mois  = c2.selectbox("Mois", ["Tous"] + [f"{i:02d}" for i in range(1,13)])

    data = df.copy()
    if annee:
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]

    if data.empty:
        st.info("Aucune donnée pour cette période.")
        return

    data["prix_brut/nuit"] = data.apply(lambda r: round((r["prix_brut"]/r["nuitees"]) if r["nuitees"] else 0,2), axis=1)
    data["prix_net/nuit"]  = data.apply(lambda r: round((r["prix_net"]/r["nuitees"])  if r["nuitees"] else 0,2), axis=1)

    show = data.copy()
    for c in ["date_arrivee","date_depart"]:
        show[c] = show[c].apply(format_date_str)

    cols = ["nom_client","plateforme","telephone","date_arrivee","date_depart",
            "nuitees","prix_brut","prix_net","charges","%","prix_brut/nuit","prix_net/nuit",
            "montant_net","commissions","frais_cb","montant_brut","menage","taxes_sejour","base"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)

    st.download_button(
        "📥 Télécharger (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

# ==============================  APP  ==============================

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

    # SECTION Fichier
    st.sidebar.title("📁 Fichier")
    df_tmp = charger_donnees()
    bouton_telecharger(df_tmp)
    bouton_restaurer()

    # Gestion plateformes/couleurs
    platform_manager_sidebar()

    # Navigation
    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients"]
    )

    # Maintenance (vider cache) SOUS la navigation
    render_cache_section_sidebar()

    # Charger données après éventuelle restauration
    df = charger_donnees()

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