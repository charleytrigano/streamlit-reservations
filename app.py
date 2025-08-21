import streamlit as st
import pandas as pd
import numpy as np
import os
import calendar
from datetime import datetime, timedelta
import openpyxl

# ==========================
# 📌 Constantes
# ==========================
DATA_FILE = "reservations.xlsx"
LOGO_FILE = "logo.png"

# couleurs par plateforme
PLATFORM_COLORS = {
    "Booking": "#1e90ff",
    "Airbnb": "#ff5a5f",
    "Abritel": "#f08080",
    "Autre": "#f59e0b",
}

# ==========================
# 📌 Fonctions utilitaires
# ==========================
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_excel(DATA_FILE)
    else:
        return pd.DataFrame(columns=[
            "Plateforme", "Nom du client", "Date arrivée", "Date départ",
            "Prix brut", "Commission", "Frais CB", "Prix net",
            "Ménage", "Taxe séjour", "Base", "%", "Payé", "SMS"
        ])

def save_data(df):
    df.to_excel(DATA_FILE, index=False)

# formater une date
def format_date(d):
    if pd.isna(d):
        return ""
    return pd.to_datetime(d).strftime("%d/%m/%Y")

# ==========================
# 📌 Vue : Réservations
# ==========================
def vue_reservations(df: pd.DataFrame):
    st.header("📋 Réservations")

    filtre_paye = st.radio("Filtrer payé", ["Tous", "Payé", "Non payé"], horizontal=True)
    if filtre_paye == "Payé":
        df = df[df["Payé"] == True]
    elif filtre_paye == "Non payé":
        df = df[df["Payé"] == False]

    plateforme_filtre = st.multiselect("Plateformes", options=df["Plateforme"].unique(), default=df["Plateforme"].unique())
    df = df[df["Plateforme"].isin(plateforme_filtre)]

    st.dataframe(df, use_container_width=True)

# ==========================
# 📌 Vue : Calendrier
# ==========================
def vue_calendrier(df: pd.DataFrame):
    st.header("📅 Calendrier")

    # Sélection du mois et de l'année
    today = datetime.today()
    col1, col2 = st.columns(2)
    mois = col1.selectbox("Mois", list(calendar.month_name)[1:], index=today.month-1)
    annee = col2.number_input("Année", value=today.year, step=1)

    mois_num = list(calendar.month_name).index(mois)
    cal = calendar.Calendar(firstweekday=0)

    jours = cal.monthdatescalendar(annee, mois_num)

    # Construire la grille
    grille = []
    for semaine in jours:
        ligne = []
        for jour in semaine:
            if jour.month != mois_num:
                ligne.append("")
            else:
                resa_jour = df[(pd.to_datetime(df["Date arrivée"]) <= jour) & (pd.to_datetime(df["Date départ"]) > jour)]
                if not resa_jour.empty:
                    contenu = ""
                    color = PLATFORM_COLORS.get(resa_jour.iloc[0]["Plateforme"], "#cccccc")
                    for _, r in resa_jour.iterrows():
                        contenu += f"<div style='background:{color};color:white;padding:2px;border-radius:4px;margin:1px'>{r['Nom du client']}</div>"
                    ligne.append(f"<b>{jour.day}</b><br>{contenu}")
                else:
                    ligne.append(str(jour.day))
        grille.append(ligne)

    # Afficher la grille avec st.markdown (HTML)
    table_html = "<table style='width:100%;border-collapse:collapse;text-align:center'>"
    jours_sem = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    table_html += "<tr>" + "".join([f"<th style='border:1px solid #ccc;padding:4px'>{j}</th>" for j in jours_sem]) + "</tr>"
    for semaine in grille:
        table_html += "<tr>" + "".join([f"<td style='border:1px solid #ccc;vertical-align:top;height:80px'>{c}</td>" for c in semaine]) + "</tr>"
    table_html += "</table>"

    st.markdown(table_html, unsafe_allow_html=True)

    # Légende
    st.subheader("🎨 Légende plateformes")
    legende = ""
    for pf, color in PLATFORM_COLORS.items():
        legende += f"<span style='background:{color};color:white;padding:4px;border-radius:4px;margin-right:8px'>{pf}</span>"
    st.markdown(legende, unsafe_allow_html=True)


# ==========================
# 📌 Normalisation & calculs
# ==========================
def to_date(x):
    if pd.isna(x) or x is None:
        return pd.NaT
    try:
        return pd.to_datetime(x).normalize()
    except Exception:
        return pd.NaT

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "Plateforme", "Nom du client", "Date arrivée", "Date départ",
        "Prix brut", "Commission", "Frais CB", "Prix net",
        "Ménage", "Taxe séjour", "Base", "%", "Payé", "SMS"
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan

    # Types
    df["Plateforme"] = df["Plateforme"].fillna("Autre").astype(str)
    df["Nom du client"] = df["Nom du client"].fillna("").astype(str)
    df["Date arrivée"] = df["Date arrivée"].apply(to_date)
    df["Date départ"] = df["Date départ"].apply(to_date)
    num_cols = ["Prix brut","Commission","Frais CB","Prix net","Ménage","Taxe séjour","Base","%"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Calculs
    df["Prix net"] = (df["Prix brut"] - df["Commission"] - df["Frais CB"]).clip(lower=0)
    df["Base"] = (df["Prix net"] - df["Ménage"] - df["Taxe séjour"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["Commission"] + df["Frais CB"]) / df["Prix brut"] * 100
    df["%"] = df["%"].fillna(0).round(2)

    # Bool
    df["Payé"] = df["Payé"].fillna(False).astype(bool)
    df["SMS"] = df["SMS"].fillna(False).astype(bool)

    # Tri par date
    df = df.sort_values(by=["Date arrivée","Nom du client"], na_position="last").reset_index(drop=True)
    return df


# ==========================
# 📌 Vue : Ajouter
# ==========================
def vue_ajouter(df: pd.DataFrame):
    st.header("➕ Ajouter une réservation")

    c1, c2 = st.columns(2)
    plateforme = c1.selectbox("Plateforme", options=list(PLATFORM_COLORS.keys()), index=0)
    nom = c2.text_input("Nom du client")

    c3, c4 = st.columns(2)
    d1 = c3.date_input("Date arrivée", value=datetime.today().date())
    d2 = c4.date_input("Date départ", value=(datetime.today() + timedelta(days=1)).date(), min_value=d1 + timedelta(days=1))

    c5, c6, c7 = st.columns(3)
    brut = c5.number_input("Prix brut (€)", min_value=0.0, step=1.0)
    commission = c6.number_input("Commission (€)", min_value=0.0, step=1.0)
    frais_cb = c7.number_input("Frais CB (€)", min_value=0.0, step=1.0)

    c8, c9 = st.columns(2)
    menage = c8.number_input("Ménage (€)", min_value=0.0, step=1.0)
    taxe = c9.number_input("Taxe séjour (€)", min_value=0.0, step=1.0)

    c10, c11 = st.columns(2)
    paye = c10.checkbox("Payé", value=False)
    sms = c11.checkbox("SMS envoyé", value=False)

    if st.button("Enregistrer"):
        new_row = {
            "Plateforme": plateforme,
            "Nom du client": nom.strip(),
            "Date arrivée": pd.to_datetime(d1),
            "Date départ": pd.to_datetime(d2),
            "Prix brut": float(brut),
            "Commission": float(commission),
            "Frais CB": float(frais_cb),
            "Prix net": 0.0,  # recalculé par ensure_schema
            "Ménage": float(menage),
            "Taxe séjour": float(taxe),
            "Base": 0.0,      # recalculé
            "%": 0.0,         # recalculé
            "Payé": bool(paye),
            "SMS": bool(sms)
        }
        df2 = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df2 = ensure_schema(df2)
        save_data(df2)
        st.success("✅ Réservation ajoutée.")
        st.experimental_rerun()


# ==========================
# 📌 Vue : Modifier / Supprimer
# ==========================
def vue_modifier(df: pd.DataFrame):
    st.header("✏️ Modifier / Supprimer une réservation")
    if df.empty:
        st.info("Aucune réservation.")
        return

    df_show = df.copy()
    df_show["Arrivée"] = df_show["Date arrivée"].dt.strftime("%d/%m/%Y").fillna("")
    options = (df_show["Nom du client"] + " — " + df_show["Plateforme"] + " — " + df_show["Arrivée"]).tolist()
    choix = st.selectbox("Choisir une réservation", options)

    idx = options.index(choix)
    r = df.iloc[idx]

    c1, c2 = st.columns(2)
    plateforme = c1.selectbox("Plateforme", options=list(PLATFORM_COLORS.keys()), index=list(PLATFORM_COLORS.keys()).index(r["Plateforme"]) if r["Plateforme"] in PLATFORM_COLORS else 0)
    nom = c2.text_input("Nom du client", value=r["Nom du client"])

    c3, c4 = st.columns(2)
    d1 = c3.date_input("Date arrivée", value=r["Date arrivée"].date() if not pd.isna(r["Date arrivée"]) else datetime.today().date())
    d2 = c4.date_input("Date départ", value=r["Date départ"].date() if not pd.isna(r["Date départ"]) else (datetime.today()+timedelta(days=1)).date(), min_value=d1 + timedelta(days=1))

    c5, c6, c7 = st.columns(3)
    brut = c5.number_input("Prix brut (€)", min_value=0.0, step=1.0, value=float(r["Prix brut"]))
    commission = c6.number_input("Commission (€)", min_value=0.0, step=1.0, value=float(r["Commission"]))
    frais_cb = c7.number_input("Frais CB (€)", min_value=0.0, step=1.0, value=float(r["Frais CB"]))

    c8, c9 = st.columns(2)
    menage = c8.number_input("Ménage (€)", min_value=0.0, step=1.0, value=float(r["Ménage"]))
    taxe = c9.number_input("Taxe séjour (€)", min_value=0.0, step=1.0, value=float(r["Taxe séjour"]))

    c10, c11 = st.columns(2)
    paye = c10.checkbox("Payé", value=bool(r["Payé"]))
    sms = c11.checkbox("SMS envoyé", value=bool(r["SMS"]))

    colA, colB = st.columns(2)
    if colA.button("💾 Enregistrer les modifications"):
        df.at[idx, "Plateforme"] = plateforme
        df.at[idx, "Nom du client"] = nom.strip()
        df.at[idx, "Date arrivée"] = pd.to_datetime(d1)
        df.at[idx, "Date départ"] = pd.to_datetime(d2)
        df.at[idx, "Prix brut"] = float(brut)
        df.at[idx, "Commission"] = float(commission)
        df.at[idx, "Frais CB"] = float(frais_cb)
        df.at[idx, "Ménage"] = float(menage)
        df.at[idx, "Taxe séjour"] = float(taxe)
        df.at[idx, "Payé"] = bool(paye)
        df.at[idx, "SMS"] = bool(sms)

        df = ensure_schema(df)
        save_data(df)
        st.success("✅ Modifications enregistrées.")
        st.experimental_rerun()

    if colB.button("🗑 Supprimer cette réservation"):
        df2 = df.drop(index=idx).reset_index(drop=True)
        save_data(ensure_schema(df2))
        st.warning("🗑 Réservation supprimée.")
        st.experimental_rerun()


# ==========================
# 📌 Vue : Rapport
# ==========================
def vue_rapport(df: pd.DataFrame):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée.")
        return

    df = ensure_schema(df)
    df["Année"] = df["Date arrivée"].dt.year
    df["Mois"] = df["Date arrivée"].dt.month

    c1, c2, c3 = st.columns(3)
    annees = sorted([int(x) for x in df["Année"].dropna().unique()])
    annee = c1.selectbox("Année", annees, index=len(annees)-1)
    pf_opt = ["Toutes"] + sorted(df["Plateforme"].dropna().unique().tolist())
    pf = c2.selectbox("Plateforme", pf_opt)
    mois_opt = ["Tous"] + [f"{i:02d}" for i in range(1,13)]
    mois_label = c3.selectbox("Mois", mois_opt)

    data = df[df["Année"] == int(annee)].copy()
    if pf != "Toutes":
        data = data[data["Plateforme"] == pf]
    if mois_label != "Tous":
        data = data[data["Mois"] == int(mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # Détail
    show = data[[
        "Payé","Nom du client","Plateforme","Date arrivée","Date départ",
        "Prix brut","Commission","Frais CB","Prix net","Ménage","Taxe séjour","Base","%"
    ]].copy()
    show["Date arrivée"] = show["Date arrivée"].dt.strftime("%d/%m/%Y")
    show["Date départ"] = show["Date départ"].dt.strftime("%d/%m/%Y")
    st.dataframe(show, use_container_width=True)

    # Totaux
    tot_brut = data["Prix brut"].sum()
    tot_net = data["Prix net"].sum()
    tot_base = data["Base"].sum()
    tot_com = (data["Commission"] + data["Frais CB"]).sum()
    colA, colB, colC, colD = st.columns(4)
    colA.metric("Total brut", f"{tot_brut:,.2f} €")
    colB.metric("Total net", f"{tot_net:,.2f} €")
    colC.metric("Base", f"{tot_base:,.2f} €")
    colD.metric("Commissions + CB", f"{tot_com:,.2f} €")

    # Export XLSX
    from io import BytesIO
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        show.to_excel(writer, index=False, sheet_name="Rapport")
    st.download_button(
        "⬇️ Export XLSX",
        data=buf.getvalue(),
        file_name=f"rapport_{annee}{'' if mois_label=='Tous' else '_'+mois_label}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ==========================
# 📌 Vue : Clients
# ==========================
def vue_clients(df: pd.DataFrame):
    st.header("👥 Liste des clients")
    if df.empty:
        st.info("Aucune donnée.")
        return

    df = ensure_schema(df)
    show = df[[
        "Nom du client","Plateforme","Date arrivée","Date départ",
        "Prix brut","Prix net","Base","Payé"
    ]].copy()
    show["Date arrivée"] = show["Date arrivée"].dt.strftime("%d/%m/%Y")
    show["Date départ"] = show["Date départ"].dt.strftime("%d/%m/%Y")
    st.dataframe(show, use_container_width=True)

    st.download_button(
        "⬇️ Export CSV",
        data=show.to_csv(index=False).encode("utf-8"),
        file_name="clients.csv",
        mime="text/csv"
    )


# ==========================
# 📌 Vue : Export ICS simple
# ==========================
def make_ics(df: pd.DataFrame) -> str:
    # ICS minimal (événements all-day)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//FR"
    ]
    for _, r in df.iterrows():
        if pd.isna(r["Date arrivée"]) or pd.isna(r["Date départ"]):
            continue
        d1 = pd.to_datetime(r["Date arrivée"]).strftime("%Y%m%d")
        d2 = pd.to_datetime(r["Date départ"]).strftime("%Y%m%d")
        title = f"{r['Plateforme']} - {r['Nom du client']}"
        lines += [
            "BEGIN:VEVENT",
            f"DTSTART;VALUE=DATE:{d1}",
            f"DTEND;VALUE=DATE:{d2}",
            f"SUMMARY:{title}",
            "END:VEVENT"