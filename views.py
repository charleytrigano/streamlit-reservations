from pathlib import Path

# Contenu complet du fichier views.py avec afficher_rapport corrigé
views_py_content = """
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import calendar
import io
from openpyxl import Workbook

# 📋 Afficher les réservations
def afficher_reservations(df):
    st.subheader("📋 Réservations")
    st.dataframe(df)

    st.markdown("### 💾 Télécharger le fichier de réservations")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    st.download_button(
        label="📥 Télécharger reservations.xlsx",
        data=output,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ➕ Ajouter une réservation
def ajouter_reservation(df):
    st.subheader("➕ Nouvelle Réservation")
    with st.form("ajout"):
        nom = st.text_input("Nom")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date arrivée")
        depart = st.date_input("Date départ", min_value=arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut", min_value=0.0)
        prix_net = st.number_input("Prix net", min_value=0.0, max_value=prix_brut)
        submit = st.form_submit_button("Enregistrer")
        if submit:
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": tel,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": round(prix_brut, 2),
                "prix_net": round(prix_net, 2),
                "charges": round(prix_brut - prix_net, 2),
                "%": round((prix_brut - prix_net) / prix_brut * 100, 2) if prix_brut else 0,
                "nuitees": (depart - arrivee).days,
                "annee": arrivee.year,
                "mois": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df.to_excel("reservations.xlsx", index=False)
            st.success("✅ Réservation enregistrée")

# ✏️ Modifier / Supprimer une réservation
def modifier_reservation(df):
    st.subheader("✏️ Modifier / Supprimer")
    if df.empty:
        st.info("Aucune réservation enregistrée.")
        return

    df["identifiant"] = df["nom_client"] + " | " + pd.to_datetime(df["date_arrivee"]).astype(str)
    selection = st.selectbox("Choisissez une réservation", df["identifiant"])
    i = df[df["identifiant"] == selection].index[0]
    with st.form("modif"):
        nom = st.text_input("Nom", df.at[i, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"], index=["Booking", "Airbnb", "Autre"].index(df.at[i, "plateforme"]))
        tel = st.text_input("Téléphone", df.at[i, "telephone"])
        arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"])
        depart = st.date_input("Départ", df.at[i, "date_depart"])
        brut = st.number_input("Prix brut", value=float(df.at[i, "prix_brut"]))
        net = st.number_input("Prix net", value=float(df.at[i, "prix_net"]))
        submit = st.form_submit_button("Modifier")
        delete = st.form_submit_button("Supprimer")
        if submit:
            df.at[i, "nom_client"] = nom
            df.at[i, "plateforme"] = plateforme
            df.at[i, "telephone"] = tel
            df.at[i, "date_arrivee"] = arrivee
            df.at[i, "date_depart"] = depart
            df.at[i, "prix_brut"] = round(brut, 2)
            df.at[i, "prix_net"] = round(net, 2)
            df.at[i, "charges"] = round(brut - net, 2)
            df.at[i, "%"] = round((brut - net) / brut * 100, 2) if brut else 0
            df.at[i, "nuitees"] = (depart - arrivee).days
            df.at[i, "annee"] = arrivee.year
            df.at[i, "mois"] = arrivee.month
            df.to_excel("reservations.xlsx", index=False)
            st.success("✅ Réservation modifiée")
        if delete:
            df.drop(index=i, inplace=True)
            df.to_excel("reservations.xlsx", index=False)
            st.warning("🗑 Réservation supprimée")

# 📅 Calendrier mensuel
def afficher_calendrier(df):
    st.subheader("📅 Calendrier")
    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    annees_disponibles = sorted([int(a) for a in df["annee"].dropna().unique() if str(a).isdigit()])
    if not annees_disponibles:
        st.warning("Aucune année valide disponible dans les données.")
        return
    annee = st.selectbox("Année", annees_disponibles)
    mois_index = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, mois_index)[1]
    jours = [date(annee, mois_index, i+1) for i in range(nb_jours)]
    planning = {jour: [] for jour in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}
    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        for jour in jours:
            if debut <= jour < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
                planning[jour].append(f"{icone} {row['nom_client']}")
    table = []
    for semaine in calendar.monthcalendar(annee, mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                jour_date = date(annee, mois_index, jour)
                contenu = f"{jour}\\n" + "\\n".join(planning[jour_date])
                ligne.append(contenu)
        table.append(ligne)
    st.table(pd.DataFrame(table, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

# 📊 Rapport mensuel corrigé
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel par plateforme")
    if df.empty:
        st.info("Aucune donnée disponible.")
        return
    plateformes = df["plateforme"].dropna().unique().tolist()
    selected_plateformes = st.multiselect("Filtrer par plateforme", plateformes, default=plateformes)
    df_filtre = df[df["plateforme"].isin(selected_plateformes)]
    stats = df_filtre.groupby(["annee", "mois", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()
    stats = stats[stats["mois"].notna()]
    stats["mois"] = stats["mois"].astype(int)
    stats["mois_texte"] = stats["mois"].apply(lambda x: calendar.month_abbr[x] if 1 <= x <= 12 else "??")
    stats["période"] = stats["mois_texte"] + " " + stats["annee"].astype(str)
    st.markdown("### 📅 Données groupées")
    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])
    st.markdown("### 💰 Revenus bruts")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))
    st.markdown("### 💵 Revenus nets")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="prix_net").fillna(0))
    st.markdown("### 🛌 Nuitées")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))
    st.markdown("### 💸 Charges")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

# 👥 Liste des clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    annee = st.selectbox("Année", sorted(df["annee"].unique()), key="annee_clients")
    mois = st.selectbox("Mois", ["Tous"] + list(range(1, 13)), key="mois_clients")
    data = df[df["annee"] == annee]
    if mois != "Tous":
        data = data[data["mois"] == mois]
    if not data.empty:
        data["prix_brut/nuit"] = (data["prix_brut"] / data["nuitees"]).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        data["prix_net/nuit"] = (data["prix_net"] / data["nuitees"]).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        colonnes = [
            "nom_client", "plateforme", "date_arrivee", "date_depart",
            "nuitees", "prix_brut", "prix_net", "charges", "%",
            "prix_brut/nuit", "prix_net/nuit"
        ]
        st.dataframe(data[colonnes])
        st.download_button(
            "📥 Télécharger en CSV",
            data=data[colonnes].to_csv(index=False).encode("utf-8"),
            file_name="liste_clients.csv",
            mime="text/csv"
        )
    else:
        st.info("Aucune donnée pour cette période.")
"""

# Sauvegarder dans un fichier
file_path = "/mnt/data/views.py"
Path(file_path).write_text(views_py_content)

file_path
