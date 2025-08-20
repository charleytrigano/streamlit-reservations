import os
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ----------------------------
# Constantes globales
# ----------------------------
EXCEL_FILE = "reservations.xlsx"
LOGO_FILE = "logo.png"

# Couleurs par plateforme
PLATFORM_COLORS_DEFAULT = {
    "Booking": "#ffcccb",
    "Airbnb": "#add8e6",
    "Abritel": "#90ee90",
    "Autres": "#d3d3d3",
}

# ----------------------------
# Utilitaires
# ----------------------------
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """S'assure que les colonnes nécessaires existent."""
    colonnes = [
        "nom_client","plateforme","AAAA","MM","JJ",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net",
        "menage","taxe_sejour","base",
        "paye","sms_envoye"
    ]
    for c in colonnes:
        if c not in df.columns:
            if c in ["paye","sms_envoye"]:
                df[c] = False
            else:
                df[c] = 0
    return df

def load_data():
    if os.path.exists(EXCEL_FILE):
        df = pd.read_excel(EXCEL_FILE)
        df = ensure_schema(df)
        return df
    else:
        return pd.DataFrame()

def save_data(df: pd.DataFrame):
    df.to_excel(EXCEL_FILE, index=False)

# ----------------------------
# Vues
# ----------------------------
def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")
    df = ensure_schema(df)

    # Totaux
    total_brut = df["prix_brut"].sum()
    total_net = df["prix_net"].sum()
    total_base = df["base"].sum()
    total_comm = df["commissions"].sum()
    total_cb = df["frais_cb"].sum()
    total_charges = total_comm + total_cb
    total_nuits = df["nuitees"].sum()

    comm_moy = (total_charges / total_brut * 100) if total_brut else 0
    prix_moy_nuit = (total_brut / total_nuits) if total_nuits else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total brut", f"{total_brut:,.2f} €")
    c2.metric("Total net", f"{total_net:,.2f} €")
    c3.metric("Total base", f"{total_base:,.2f} €")

    c4, c5, c6 = st.columns(3)
    c4.metric("Total charges", f"{total_charges:,.2f} €")
    c5.metric("Commission moy.", f"{comm_moy:.2f} %")
    c6.metric("Prix moyen nuitées", f"{prix_moy_nuit:,.2f} €")

    # Tableau
    st.dataframe(df, use_container_width=True, hide_index=True)

# ----------------------------
# Aides de saisie / normalisation
# ----------------------------
def _to_date(x):
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def _fmt_date(d):
    return d.strftime("%Y/%m/%d") if pd.notna(d) and d else ""

def _normalize_phone(x):
    if pd.isna(x) or x is None:
        return ""
    s = str(x).strip()
    s = s.replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

def upgrade_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Aligne les noms & types (garde ce que tu avais)."""
    df = df.copy()

    # Harmonisation nom de colonne (si 'taxe_sejour' existait)
    if "taxe_sejour" in df.columns and "taxes_sejour" not in df.columns:
        df.rename(columns={"taxe_sejour": "taxes_sejour"}, inplace=True)

    # Colonnes de base attendues
    base_cols = [
        "nom_client","plateforme","AAAA","MM","JJ",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net",
        "menage","taxes_sejour","base",
        "paye","sms_envoye","telephone"
    ]
    for c in base_cols:
        if c not in df.columns:
            df[c] = np.nan

    # Booléens
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    # Dates
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = df["date_arrivee"].apply(_to_date)
    if "date_depart" in df.columns:
        df["date_depart"] = df["date_depart"].apply(_to_date)

    # AAAA/MM/JJ (depuis date_arrivee)
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if d else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if d else np.nan).astype("Int64")
    df["JJ"]   = df["date_arrivee"].apply(lambda d: d.day if d else np.nan).astype("Int64")

    # Nuitées
    df["nuitees"] = [
        (d2 - d1).days if (d1 and d2) else np.nan
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]

    # Téléphone
    if "telephone" in df.columns:
        df["telephone"] = df["telephone"].apply(_normalize_phone)

    # Numériques
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Recalcules cohérents (sans casser tes chiffres si déjà là)
    # prix_net = brut - commissions - frais_cb
    calc_net = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    # on met à jour si vide
    df["prix_net"] = np.where(df["prix_net"].isna() | (df["prix_net"] == 0), calc_net, df["prix_net"])
    # base = net - ménage - taxes
    calc_base = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["base"] = np.where(df["base"].isna() | (df["base"] == 0), calc_base, df["base"])

    # Valeurs par défaut
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autres")

    return df

# ----------------------------
# Vues (suite)
# ----------------------------
def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")

    with st.form("add_form", clear_on_submit=True):
        c0, c1, c2 = st.columns([1,2,2])
        paye = c0.checkbox("Payé", value=False)
        nom = c1.text_input("Nom client")
        tel = c2.text_input("Téléphone (+33…)", value="")

        c3, c4 = st.columns(2)
        plateforme = c3.selectbox("Plateforme", ["Booking","Airbnb","Abritel","Autres"], index=0)
        sms_envoye = c4.checkbox("SMS envoyé", value=False)

        c5, c6 = st.columns(2)
        d1 = c5.date_input("Arrivée")
        d2 = c6.date_input("Départ", min_value=d1 + timedelta(days=1), value=d1 + timedelta(days=1))

        c7, c8, c9 = st.columns(3)
        brut = c7.number_input("Prix brut (€)", min_value=0.0, step=1.0, format="%.2f")
        comm = c8.number_input("Commissions (€)", min_value=0.0, step=1.0, format="%.2f")
        cb   = c9.number_input("Frais CB (€)", min_value=0.0, step=1.0, format="%.2f")

        net_calc = max(brut - comm - cb, 0.0)

        c10, c11, c12 = st.columns(3)
        menage = c10.number_input("Ménage (€)", min_value=0.0, step=1.0, format="%.2f")
        taxes  = c11.number_input("Taxes séjour (€)", min_value=0.0, step=1.0, format="%.2f")
        base_calc = max(net_calc - menage - taxes, 0.0)
        c12.metric("Prix net (calculé)", f"{net_calc:.2f} €")

        submit = st.form_submit_button("Enregistrer")
        if submit:
            if d2 <= d1:
                st.error("La date de départ doit être après la date d’arrivée.")
                return

            ligne = {
                "paye": bool(paye),
                "nom_client": nom.strip(),
                "sms_envoye": bool(sms_envoye),
                "plateforme": plateforme,
                "telephone": _normalize_phone(tel),
                "date_arrivee": d1,
                "date_depart": d2,
                "nuitees": (d2 - d1).days,
                "prix_brut": float(brut),
                "commissions": float(comm),
                "frais_cb": float(cb),
                "prix_net": float(net_calc),
                "menage": float(menage),
                "taxes_sejour": float(taxes),
                "base": float(base_calc),
                "AAAA": d1.year,
                "MM": d1.month,
                "JJ": d1.day
            }
            df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            save_data(df2)
            st.success("✅ Réservation ajoutée")

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    if df.empty:
        st.info("Aucune réservation.")
        return

    work = df.copy()
    work["id_aff"] = work["nom_client"].astype(str) + " | " + work["date_arrivee"].apply(lambda d: _fmt_date(d) if pd.notna(d) else "")

    choix = st.selectbox("Choisir la réservation", work["id_aff"])
    if not len(work.index):
        st.warning("Sélection invalide.")
        return
    row = work[work["id_aff"] == choix].iloc[0]
    i = row.name

    c0, c1, c2 = st.columns([1,2,2])
    paye = c0.checkbox("Payé", value=bool(df.at[i, "paye"]))
    nom  = c1.text_input("Nom client", value=str(df.at[i, "nom_client"]))
    tel  = c2.text_input("Téléphone", value=_normalize_phone(df.at[i, "telephone"]))

    c3, c4 = st.columns(2)
    plateforme = c3.selectbox("Plateforme", ["Booking","Airbnb","Abritel","Autres"],
                              index=["Booking","Airbnb","Abritel","Autres"].index(df.at[i,"plateforme"]) if df.at[i,"plateforme"] in ["Booking","Airbnb","Abritel","Autres"] else 3)
    sms_envoye = c4.checkbox("SMS envoyé", value=bool(df.at[i, "sms_envoye"]))

    c5, c6 = st.columns(2)
    d1 = c5.date_input("Arrivée", value=df.at[i,"date_arrivee"])
    d2 = c6.date_input("Départ", value=df.at[i,"date_depart"], min_value=d1 + timedelta(days=1))

    c7, c8, c9 = st.columns(3)
    brut = c7.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"]), step=1.0, format="%.2f")
    comm = c8.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i,"commissions"]), step=1.0, format="%.2f")
    cb   = c9.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"]), step=1.0, format="%.2f")

    net_calc = max(brut - comm - cb, 0.0)

    c10, c11, c12 = st.columns(3)
    menage = c10.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i,"menage"]), step=1.0, format="%.2f")
    taxes  = c11.number_input("Taxes séjour (€)", min_value=0.0, value=float(df.at[i,"taxes_sejour"]), step=1.0, format="%.2f")
    base_calc = max(net_calc - menage - taxes, 0.0)
    c12.metric("Prix net (calculé)", f"{net_calc:.2f} €")

    c_save, c_del = st.columns(2)
    if c_save.button("💾 Enregistrer"):
        if d2 <= d1:
            st.error("La date de départ doit être après la date d’arrivée.")
            return

        df.at[i,"paye"] = bool(paye)
        df.at[i,"nom_client"] = nom.strip()
        df.at[i,"sms_envoye"] = bool(sms_envoye)
        df.at[i,"plateforme"] = plateforme
        df.at[i,"telephone"] = _normalize_phone(tel)
        df.at[i,"date_arrivee"] = d1
        df.at[i,"date_depart"]  = d2
        df.at[i,"nuitees"] = (d2 - d1).days
        df.at[i,"prix_brut"] = float(brut)
        df.at[i,"commissions"] = float(comm)
        df.at[i,"frais_cb"] = float(cb)
        df.at[i,"prix_net"] = float(net_calc)
        df.at[i,"menage"] = float(menage)
        df.at[i,"taxes_sejour"] = float(taxes)
        df.at[i,"base"] = float(base_calc)
        df.at[i,"AAAA"] = d1.year
        df.at[i,"MM"] = d1.month
        df.at[i,"JJ"] = d1.day

        save_data(df)
        st.success("✅ Modifications enregistrées")

    if c_del.button("🗑 Supprimer"):
        df2 = df.drop(index=i).reset_index(drop=True)
        save_data(df2)
        st.warning("Réservation supprimée")

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier (simple)")
    if df.empty:
        st.info("Aucune donnée.")
        return

    # Sélection période
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = st.selectbox("Année", annees, index=len(annees)-1)
    mois  = st.selectbox("Mois", list(range(1,13)), index=min(max(0, datetime.today().month-1), 11))

    data = df[(df["AAAA"] == annee) & (df["MM"] == mois)].copy()
    if data.empty:
        st.info("Aucune réservation pour ce mois.")
        return

    # Vue textuelle compacte
    data["periode"] = data["date_arrivee"].apply(_fmt_date) + " → " + data["date_depart"].apply(_fmt_date)
    st.dataframe(
        data[["nom_client","plateforme","periode","nuitees","prix_brut","prix_net","base","paye","sms_envoye"]],
        use_container_width=True, hide_index=True
    )

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = st.selectbox("Année", annees, index=len(annees)-1)
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = st.selectbox("Plateforme", pf_opt)

    data = df[df["AAAA"] == annee].copy()
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # Détail
    show = data.copy()
    show["date_arrivee"] = show["date_arrivee"].apply(_fmt_date)
    show["date_depart"]  = show["date_depart"].apply(_fmt_date)
    st.dataframe(
        show[["paye","nom_client","sms_envoye","plateforme","telephone",
              "date_arrivee","date_depart","nuitees",
              "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base"]],
        use_container_width=True, hide_index=True
    )

    # KPI Totaux
    tot_brut = data["prix_brut"].sum()
    tot_net  = data["prix_net"].sum()
    tot_base = data["base"].sum()
    tot_comm = data["commissions"].sum()
    tot_cb   = data["frais_cb"].sum()
    tot_ch   = tot_comm + tot_cb
    tot_nuit = data["nuitees"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total brut", f"{tot_brut:,.2f} €")
    c2.metric("Total net", f"{tot_net:,.2f} €")
    c3.metric("Total base", f"{tot_base:,.2f} €")

    c4, c5, c6 = st.columns(3)
    c4.metric("Total charges", f"{tot_ch:,.2f} €")
    c5.metric("Commission moy.", f"{(tot_ch/tot_brut*100) if tot_brut else 0:.2f} %")
    c6.metric("Prix moyen/nuit", f"{(tot_brut/tot_nuit) if tot_nuit else 0:,.2f} €")

def vue_clients(df: pd.DataFrame):
    st.title("👥 Clients")
    if df.empty:
        st.info("Aucune donnée.")
        return

    work = df.copy()
    # prix par nuit
    work["prix_brut/nuit"] = work.apply(lambda r: round((r["prix_brut"]/r["nuitees"]) if r["nuitees"] else 0,2), axis=1)
    work["prix_net/nuit"]  = work.apply(lambda r: round((r["prix_net"]/r["nuitees"])  if r["nuitees"] else 0,2), axis=1)

    show = work.copy()
    show["date_arrivee"] = show["date_arrivee"].apply(_fmt_date)
    show["date_depart"]  = show["date_depart"].apply(_fmt_date)

    st.dataframe(
        show[["paye","nom_client","sms_envoye","plateforme","telephone",
              "date_arrivee","date_depart","nuitees",
              "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base",
              "prix_brut/nuit","prix_net/nuit"]],
        use_container_width=True, hide_index=True
    )

def vue_ratios(df: pd.DataFrame):
    st.title("📈 Ratios")
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = st.selectbox("Année", annees, index=len(annees)-1)
    data = df[df["AAAA"] == annee].copy()
    if data.empty:
        st.info("Aucune donnée pour cette année.")
        return

    # Ratios par plateforme et par mois
    agg = (
        data.assign(charges=lambda x: x["commissions"] + x["frais_cb"])
            .groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 base=("base","sum"),
                 charges=("charges","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
    )
    if agg.empty:
        st.info("Aucune donnée agrégée.")
        return

    # Ratios
    agg["ratio_charges_sur_brut_%"] = np.where(agg["prix_brut"]>0, agg["charges"]/agg["prix_brut"]*100, 0.0).round(2)
    agg["ratio_net_sur_brut_%"]     = np.where(agg["prix_brut"]>0, agg["prix_net"]/agg["prix_brut"]*100, 0.0).round(2)
    agg["pm_brut_par_nuit"]         = np.where(agg["nuitees"]>0, agg["prix_brut"]/agg["nuitees"], 0.0).round(2)
    agg["pm_net_par_nuit"]          = np.where(agg["nuitees"]>0, agg["prix_net"]/agg["nuitees"], 0.0).round(2)

    # Affichage
    st.dataframe(
        agg.sort_values(["MM","plateforme"])[
            ["MM","plateforme","prix_brut","prix_net","base","charges","nuitees",
             "ratio_charges_sur_brut_%","ratio_net_sur_brut_%","pm_brut_par_nuit","pm_net_par_nuit"]
        ],
        use_container_width=True, hide_index=True
    )

    # Petites barres comparatives
    st.markdown("**Ratio des charges / brut (%) par mois (somme de toutes plateformes)**")
    tot_mois = agg.groupby("MM", as_index=True).agg(charges=("charges","sum"), brut=("prix_brut","sum")).assign(
        ratio=lambda x: np.where(x["brut"]>0, x["charges"]/x["brut"]*100, 0.0).round(2)
    )["ratio"]
    st.bar_chart(tot_mois)

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

    # Logo (si présent)
    if os.path.exists(LOGO_FILE):
        st.sidebar.image(LOGO_FILE, width=140)

    # Chargement + normalisation
    df_raw = load_data()
    df = upgrade_schema(df_raw)

    # Barre latérale : export / backup simple
    with st.sidebar:
        st.header("📁 Fichier")
        if st.button("💾 Sauvegarder maintenant"):
            save_data(df)
            st.success("Données sauvegardées")

        up = st.file_uploader("📤 Importer un .xlsx (remplace)", type=["xlsx"])
        if up is not None:
            try:
                new_df = pd.read_excel(up)
                new_df = upgrade_schema(new_df)
                save_data(new_df)
                st.success("Import réussi — recharge l’app.")
            except Exception as e:
                st.error(f"Erreur import: {e}")

    # Navigation
    onglet = st.sidebar.radio(
        "Navigation",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Clients","📈 Ratios"]
    )

    # Router
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
    elif onglet == "👥 Clients":
        vue_clients(df)
    elif onglet == "📈 Ratios":
        vue_ratios(df)

if __name__ == "__main__":
    main()