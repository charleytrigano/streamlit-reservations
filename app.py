import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta, date
from io import BytesIO

FICHIER = "reservations.xlsx"

# ✅ Fonction de restauration
def restaurer_fichier_excel():
    uploaded_file = st.sidebar.file_uploader("📤 Restaurer un fichier Excel", type=["xlsx"])
    if uploaded_file:
        df_restored = pd.read_excel(uploaded_file)
        df_restored.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier restauré avec succès.")
        return df_restored
    elif Path(FICHIER).exists():
        return pd.read_excel(FICHIER)
    else:
        st.warning("Aucun fichier de réservation disponible.")
        return pd.DataFrame()

# 💾 Fonction de téléchargement
def telecharger_fichier_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    st.download_button(
        label="📥 Télécharger le fichier Excel",
        data=buffer.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 📋 Affichage des réservations
def afficher_reservations(df):
    st.subheader("📋 Réservations")
    df_affiche = df.copy()
    df_affiche["date_arrivee"] = pd.to_datetime(df_affiche["date_arrivee"]).dt.strftime("%Y/%m/%d")
    df_affiche["date_depart"] = pd.to_datetime(df_affiche["date_depart"]).dt.strftime("%Y/%m/%d")
    colonnes = ["nom_client", "plateforme", "telephone", "date_arrivee", "date_depart", "nuitees",
                "prix_brut", "prix_net", "charges", "%", "aaaa", "mm"]
    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df_affiche.columns:
            df_affiche[col] = df_affiche[col].apply(lambda x: f"{x:.2f}")
    st.dataframe(df_affiche[colonnes])

# ➕ Ajout d’une réservation
def ajouter_reservation(df):
    st.subheader("➕ Ajouter une réservation")
    with st.form("ajout"):
        nom = st.text_input("Nom")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d'arrivée", value=date.today())
        depart = st.date_input("Date de départ", value=arrivee + timedelta(days=1))
        brut = st.number_input("Prix brut", min_value=0.0, step=1.0)
        net = st.number_input("Prix net", min_value=0.0, step=1.0, value=brut)
        submit = st.form_submit_button("Enregistrer")

    if submit:
        nuitees = (depart - arrivee).days
        charges = brut - net
        pourcent = (charges / brut * 100) if brut > 0 else 0
        nouvelle = {
            "nom_client": nom,
            "plateforme": plateforme,
            "telephone": tel,
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": round(brut, 2),
            "prix_net": round(net, 2),
            "charges": round(charges, 2),
            "%": round(pourcent, 2),
            "nuitees": nuitees,
            "aaaa": arrivee.year,
            "mm": arrivee.month
        }
        df = pd.concat([df, pd.DataFrame([nouvelle])], ignore_index=True)
        df.to_excel(FICHIER, index=False)
        st.success("✅ Réservation ajoutée avec succès")

# 📅 Calendrier
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")
    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    mois_index = list(calendar.month_name).index(mois_nom)
    annees = sorted(df["aaaa"].dropna().unique())
    annee = st.selectbox("Année", annees)

    jours = [date(int(annee), mois_index, j+1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {j: [] for j in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = pd.to_datetime(row["date_arrivee"]).date()
        fin = pd.to_datetime(row["date_depart"]).date()
        for j in jours:
            if debut <= j < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
                planning[j].append(f"{icone} {row['nom_client']}")

    tableau = []
    for semaine in calendar.monthcalendar(int(annee), mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                d = date(int(annee), mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning[d])
                ligne.append(contenu)
        tableau.append(ligne)

    st.table(pd.DataFrame(tableau, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

# 📊 Rapport
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")
    if df.empty:
        st.info("Aucune donnée.")
        return

    stats = df.groupby(["aaaa", "mm", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois"] = stats["mm"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["periode"] = stats["mois"] + " " + stats["aaaa"].astype(str)

    st.dataframe(stats[["periode", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.markdown("### 💰 Revenus bruts")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 💸 Charges")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="charges").fillna(0))

# ▶️ Point d’entrée principal
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    df = restaurer_fichier_excel()

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "➕ Ajouter",
        "📅 Calendrier",
        "📊 Rapport"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
        telecharger_fichier_excel(df)

    elif onglet == "➕ Ajouter":
        ajouter_reservation(df)

    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)

    elif onglet == "📊 Rapport":
        afficher_rapport(df)

if __name__ == "__main__":
    main()
