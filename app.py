import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

# ----------------------------
# CONFIG
# ----------------------------

st.set_page_config(
    page_title="📋 Réservations",
    page_icon="📅",
    layout="wide"
)

DATA_FILE = "reservations.xlsx"
LOGO_FILE = "logo.png"

# ----------------------------
# CHARGEMENT DES DONNÉES
# ----------------------------
@st.cache_data
def load_data():
    if os.path.exists(DATA_FILE):
        df = pd.read_excel(DATA_FILE)
        # Vérifie colonnes essentielles
        colonnes_obligatoires = [
            "plateforme", "num_resa", "nom_client", "date_arrivee", "date_depart",
            "personnes", "prix_brut", "commission", "frais_cb", "prix_net",
            "menage", "taxe_sejour", "base", "pourcentage", "sms", "paye"
        ]
        for col in colonnes_obligatoires:
            if col not in df.columns:
                df[col] = None
        return df
    else:
        return pd.DataFrame(columns=[
            "plateforme", "num_resa", "nom_client", "date_arrivee", "date_depart",
            "personnes", "prix_brut", "commission", "frais_cb", "prix_net",
            "menage", "taxe_sejour", "base", "pourcentage", "sms", "paye"
        ])

def save_data(df):
    df.to_excel(DATA_FILE, index=False)

# ----------------------------
# KPI
# ----------------------------
def afficher_kpi(df):
    total_brut = df["prix_brut"].sum()
    total_net = df["prix_net"].sum()
    total_base = df["base"].sum()
    total_charges = (df["commission"].sum() + df["frais_cb"].sum())
    commissions_moy = (total_charges / total_brut * 100) if total_brut > 0 else 0
    nuitees = df["nuitees"].sum() if "nuitees" in df.columns else 0
    prix_moyen_nuitee = (total_brut / nuitees) if nuitees > 0 else 0

    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6, kpi7 = st.columns(7)
    kpi1.metric("💰 Total Brut", f"{total_brut:,.2f} €")
    kpi2.metric("✅ Total Net", f"{total_net:,.2f} €")
    kpi3.metric("📊 Base", f"{total_base:,.2f} €")
    kpi4.metric("💸 Charges", f"{total_charges:,.2f} €")
    kpi5.metric("📉 Com. Moy.", f"{commissions_moy:.2f} %")
    kpi6.metric("🛏️ Nuitées", f"{nuitees}")
    kpi7.metric("🏷️ Prix moy/nuitée", f"{prix_moyen_nuitee:,.2f} €")

# ----------------------------
# VUE RÉSERVATIONS
# ----------------------------
def vue_reservations(df):
    st.subheader("📋 Liste des réservations")
    afficher_kpi(df)

    # Options d'affichage
    with st.expander("⚙️ Options d'affichage"):
        colonnes_affichage = st.multiselect(
            "Colonnes à afficher",
            df.columns.tolist(),
            default=[
                "plateforme", "num_resa", "nom_client", "date_arrivee", "date_depart",
                "prix_brut", "commission", "frais_cb", "prix_net", "menage",
                "taxe_sejour", "base", "pourcentage", "sms", "paye"
            ]
        )
        tri = st.selectbox("Trier par :", df.columns.tolist(), index=3)

    st.dataframe(
        df[colonnes_affichage].sort_values(by=tri),
        use_container_width=True,
        height=420
    )

# ----------------------------
# OUTILS DATES / CALCULS
# ----------------------------
def as_dt(d):
    if pd.isna(d):
        return pd.NaT
    try:
        return pd.to_datetime(d)
    except Exception:
        return pd.NaT

def add_computed_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Dates en datetime (si ce n'est pas déjà le cas)
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = df["date_arrivee"].apply(as_dt)
    if "date_depart" in df.columns:
        df["date_depart"] = df["date_depart"].apply(as_dt)

    # Nuitées
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = (
            (df["date_depart"].dt.date - df["date_arrivee"].dt.date)
            .apply(lambda x: x.days if pd.notna(x) else 0)
        )

    # Champs manquants en 0 pour les totaux
    for c in ["prix_brut", "commission", "frais_cb", "prix_net", "menage", "taxe_sejour", "base"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Booléens
    for b in ["sms", "paye"]:
        if b in df.columns:
            df[b] = df[b].fillna(False).astype(bool)

    return df

# ----------------------------
# CALENDRIER (mois)
# ----------------------------
def vue_calendrier(df):
    st.subheader("📅 Calendrier (occupations par jour)")
    if df.empty:
        st.info("Aucune réservation.")
        return

    c1, c2 = st.columns(2)
    # Années disponibles depuis les dates d'arrivée
    if "date_arrivee" in df.columns and df["date_arrivee"].notna().any():
        annees = sorted(df["date_arrivee"].dropna().dt.year.unique().tolist())
    else:
        annees = [datetime.today().year]
    annee = c1.selectbox("Année", annees, index=len(annees)-1)

    mois_map = {1:"Jan",2:"Fév",3:"Mar",4:"Avr",5:"Mai",6:"Jun",7:"Jui",8:"Aoû",9:"Sep",10:"Oct",11:"Nov",12:"Déc"}
    mois = c2.selectbox("Mois", list(range(1,13)), format_func=lambda m: f"{m:02d} - {mois_map[m]}",
                        index=(datetime.today().month-1))

    # fenêtre du mois
    start = pd.Timestamp(year=annee, month=mois, day=1)
    end = (start + pd.offsets.MonthEnd(0)) + pd.Timedelta(days=1)  # exclusif
    days = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")

    # Calcul des occupations / jour
    occ = pd.Series(0, index=days)
    for _, r in df.iterrows():
        d1 = r.get("date_arrivee")
        d2 = r.get("date_depart")
        if pd.isna(d1) or pd.isna(d2):
            continue
        # pour chaque jour du séjour
        stay_days = pd.date_range(d1.normalize(), d2.normalize() - pd.Timedelta(days=1), freq="D")
        for d in stay_days:
            if d in occ.index:
                occ.loc[d] += 1

    # Affichage simple
    st.bar_chart(occ)

    # Détail des réservations du mois
    in_month = df[(df["date_arrivee"] < end) & (df["date_depart"] >= start)].copy()
    if not in_month.empty:
        show = in_month.copy()
        show["date_arrivee"] = show["date_arrivee"].dt.strftime("%Y-%m-%d")
        show["date_depart"]  = show["date_depart"].dt.strftime("%Y-%m-%d")
        cols = [c for c in ["plateforme","num_resa","nom_client","date_arrivee","date_depart","nuitees","prix_brut","prix_net","paye","sms"] if c in show.columns]
        st.dataframe(show[cols].sort_values(by=["date_arrivee","nom_client"]), use_container_width=True)

# ----------------------------
# RAPPORT
# ----------------------------
def vue_rapport(df):
    st.subheader("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée.")
        return

    # Filtres
    c1, c2, c3 = st.columns(3)
    years = sorted(df["date_arrivee"].dropna().dt.year.unique().tolist()) if df["date_arrivee"].notna().any() else [datetime.today().year]
    annee = c1.selectbox("Année", years, index=len(years)-1)

    mois = c2.selectbox("Mois", ["Tous"] + list(range(1,13)), index=0)
    plateformes = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist()) if "plateforme" in df.columns else ["Toutes"]
    pf = c3.selectbox("Plateforme", plateformes, index=0)

    data = df[df["date_arrivee"].dt.year == annee].copy()
    if mois != "Tous":
        data = data[data["date_arrivee"].dt.month == int(mois)]
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # Détail
    detail = data.copy()
    detail["date_arrivee"] = detail["date_arrivee"].dt.strftime("%Y-%m-%d")
    detail["date_depart"]  = detail["date_depart"].dt.strftime("%Y-%m-%d")
    cols = [c for c in ["plateforme","num_resa","nom_client","date_arrivee","date_depart","nuitees","prix_brut","commission","frais_cb","prix_net","menage","taxe_sejour","base","paye","sms"] if c in detail.columns]
    st.dataframe(detail[cols].sort_values(by=["date_arrivee","nom_client"]), use_container_width=True)

    # KPI récap (réutilise la fonction partie 1)
    afficher_kpi(data)

    # Groupé par mois / plateforme
    grp = (
        data.assign(MM=data["date_arrivee"].dt.month)
            .groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 base=("base","sum"),
                 charges=("commission","sum"),   # commissions seules
                 frais_cb=("frais_cb","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
            .sort_values(["MM","plateforme"])
    )
    st.markdown("**Synthèse par mois & plateforme**")
    st.dataframe(grp, use_container_width=True)

    # Petits graphiques
    if not grp.empty:
        pvt_brut = grp.pivot(index="MM", columns="plateforme", values="prix_brut").fillna(0).sort_index()
        pvt_net  = grp.pivot(index="MM", columns="plateforme", values="prix_net").fillna(0).sort_index()
        pvt_nuit = grp.pivot(index="MM", columns="plateforme", values="nuitees").fillna(0).sort_index()

        st.markdown("**Brut**")
        st.bar_chart(pvt_brut)
        st.markdown("**Net**")
        st.bar_chart(pvt_net)
        st.markdown("**Nuitées**")
        st.bar_chart(pvt_nuit)

# ----------------------------
# SMS (affichage simple)
# ----------------------------
def sms_arrivee_message(r):
    d1 = r.get("date_arrivee")
    d2 = r.get("date_depart")
    nom = r.get("nom_client","")
    nuitees = int(r.get("nuitees") or 0)
    d1s = d1.strftime("%Y-%m-%d") if isinstance(d1, pd.Timestamp) and not pd.isna(d1) else ""
    d2s = d2.strftime("%Y-%m-%d") if isinstance(d2, pd.Timestamp) and not pd.isna(d2) else ""
    return (
        f"Bonjour {nom},\n"
        f"Rappel de votre séjour : {d1s} → {d2s} ({nuitees} nuitées).\n"
        "Merci de nous indiquer votre heure d'arrivée. À bientôt !"
    )

def sms_depart_message(r):
    nom = r.get("nom_client","")
    return (
        f"Bonjour {nom},\n"
        "Merci pour votre séjour. Nous espérons vous revoir très bientôt !"
    )

def vue_sms(df):
    st.subheader("✉️ SMS")
    if df.empty:
        st.info("Aucune donnée.")
        return

    today = pd.Timestamp(datetime.today().date())
    demain = today + pd.Timedelta(days=1)
    hier   = today - pd.Timedelta(days=1)

    c1, c2 = st.columns(2)
    # Arrivées demain
    with c1:
        st.markdown("**📆 Arrivées demain**")
        arrivals = df[df["date_arrivee"].dt.date == demain.date()]
        if arrivals.empty:
            st.info("Aucune arrivée demain.")
        else:
            for _, r in arrivals.iterrows():
                st.write(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}  \n"
                         f"{r['date_arrivee'].strftime('%Y-%m-%d')} → {r['date_depart'].strftime('%Y-%m-%d')} • {int(r.get('nuitees') or 0)} nuitées")
                st.code(sms_arrivee_message(r))

    # Départs hier (relance)
    with c2:
        st.markdown("**🕒 Relance (départs hier)**")
        departs = df[df["date_depart"].dt.date == hier.date()]
        if departs.empty:
            st.info("Aucun départ hier.")
        else:
            for _, r in departs.iterrows():
                st.write(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.code(sms_depart_message(r))

    # Composeur simple
    st.markdown("---")
    st.markdown("**✍️ Composer un SMS manuel**")
    if "nom_client" in df.columns:
        df_pick = df.copy()
        df_pick["id_aff"] = (
            df_pick.get("nom_client","").astype(str) + " | " +
            df_pick.get("plateforme","").astype(str) + " | " +
            df_pick.get("date_arrivee").dt.strftime("%Y-%m-%d")
        )
        choix = st.selectbox("Réservation", df_pick["id_aff"])
        r = df_pick.loc[df_pick["id_aff"] == choix].iloc[0]
        body = st.text_area("Message", value=sms_arrivee_message(r), height=160)
        st.code(body)

# ----------------------------
# MAIN
# ----------------------------
def main():
    # Logo discret s'il existe
    if os.path.exists(LOGO_FILE):
        st.sidebar.image(LOGO_FILE, caption=None, use_container_width=True)

    # Charger + colonnes calculées
    df_raw = load_data()
    df = add_computed_columns(df_raw)

    # Filtres globaux dans la sidebar (sans toucher aux vues)
    st.sidebar.markdown("### 🔎 Filtres")
    # Années
    if "date_arrivee" in df.columns and df["date_arrivee"].notna().any():
        years = sorted(df["date_arrivee"].dropna().dt.year.unique().tolist())
    else:
        years = [datetime.today().year]
    year = st.sidebar.selectbox("Année", years, index=len(years)-1)

    # Mois
    mois_options = ["Tous"] + list(range(1,13))
    mois = st.sidebar.selectbox("Mois", mois_options, index=0, format_func=lambda m: f"{m:02d}" if isinstance(m,int) else m)

    # Plateforme
    plateformes = ["Toutes"] + sorted([p for p in df["plateforme"].dropna().unique().tolist()] if "plateforme" in df.columns else [])
    pf = st.sidebar.selectbox("Plateforme", plateformes, index=0)

    # Payé
    paye_filtre = st.sidebar.selectbox("Payé ?", ["Tous", "Payé", "Non payé"], index=0)

    # Appliquer filtres
    data = df[df["date_arrivee"].dt.year == year].copy()
    if mois != "Tous":
        data = data[data["date_arrivee"].dt.month == int(mois)]
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]
    if paye_filtre == "Payé":
        data = data[data["paye"] == True]
    elif paye_filtre == "Non payé":
        data = data[data["paye"] == False]

    # Navigation
    st.sidebar.markdown("---")
    onglet = st.sidebar.radio("Aller à", ["📋 Réservations", "📅 Calendrier", "📊 Rapport", "✉️ SMS"], index=0)

    # Boutons fichier
    st.sidebar.markdown("---")
    col_dl, col_sv = st.sidebar.columns(2)
    with col_dl:
        st.download_button(
            "⬇️ Export XLSX",
            data=data.to_excel(index=False, engine="openpyxl") if hasattr(data, "to_excel_bytes") else None,
            file_name="export_filtre.xlsx",
            disabled=True, help="Export direct désactivé (utilise le bouton ci-dessous)"
        )
    # Sauvegarde (écriture du fichier de travail)
    if st.sidebar.button("💾 Sauvegarder (XLSX)"):
        save_data(df_raw)
        st.sidebar.success("Données sauvegardées dans reservations.xlsx")

    # Vues
    st.title("📖 Réservations")
    if onglet == "📋 Réservations":
        vue_reservations(data)
    elif onglet == "📅 Calendrier":
        vue_calendrier(data)
    elif onglet == "📊 Rapport":
        vue_rapport(data)
    elif onglet == "✉️ SMS":
        vue_sms(data)

if __name__ == "__main__":
    main()
