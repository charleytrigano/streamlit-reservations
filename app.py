import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
from io import BytesIO

FICHIER = "reservations.xlsx"

def formater_donnees(df):
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
    if "date_depart" in df.columns:
        df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
    if "prix_brut" in df.columns:
        df["prix_brut"] = df["prix_brut"].round(2)
    if "prix_net" in df.columns:
        df["prix_net"] = df["prix_net"].round(2)
    if "charges" in df.columns:
        df["charges"] = df["charges"].round(2)
    if "%" in df.columns:
        df["%"] = df["%"].round(2)
    if "AAAA" in df.columns:
        df["AAAA"] = df["AAAA"].astype("Int64")
    if "MM" in df.columns:
        df["MM"] = df["MM"].astype("Int64")
    return df

def charger_donnees():
    try:
        df = pd.read_excel(FICHIER)
        return formater_donnees(df)
    except:
        return pd.DataFrame()

def sauvegarder_donnees(df):
    df = formater_donnees(df)
    df.to_excel(FICHIER, index=False)

def uploader_excel():
    uploaded_file = st.sidebar.file_uploader("📤 Restaurer un fichier Excel", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        sauvegarder_donnees(df)
        st.sidebar.success("✅ Fichier restauré avec succès")

def telecharger_fichier_excel(df):
    buffer = BytesIO()
    formater_donnees(df).to_excel(buffer, index=False)
    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=buffer.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

def ajouter_reservation(df):
    st.subheader("➕ Ajouter une réservation")
    with st.form("ajouter"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d’arrivée", date.today())
        depart = st.date_input("Date de départ", date.today() + timedelta(days=1))
        brut = st.number_input("Prix brut (€)", 0.0)
        net = st.number_input("Prix net (€)", 0.0, brut)
        submit = st.form_submit_button("Enregistrer")

        if submit:
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": tel,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": round(brut, 2),
                "prix_net": round(net, 2),
                "charges": round(brut - net, 2),
                "%": round((brut - net) / brut * 100, 2) if brut else 0,
                "nuitees": (depart - arrivee).days,
                "AAAA": arrivee.year,
                "MM": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            sauvegarder_donnees(df)
            st.success("✅ Réservation enregistrée")

def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")
    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    plateformes = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    filtre = st.selectbox("Filtrer par plateforme", plateformes)
    if filtre != "Toutes":
        df = df[df["plateforme"] == filtre]

    stats = df.groupby(["AAAA", "MM", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["MM"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["AAAA"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.markdown("### 📈 Revenus bruts par mois")
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 🛌 Nuitées par mois")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))

    st.markdown("### 💸 Charges mensuelles")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")
    if df.empty or "AAAA" not in df.columns or "MM" not in df.columns:
        st.warning("Aucune donnée disponible.")
        return

    col1, col2 = st.columns(2)
    with col1:
        mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    with col2:
        annee = st.selectbox("Année", sorted(df["AAAA"].dropna().astype(int).unique()))

    mois_index = list(calendar.month_name).index(mois_nom)
    jours = [date(int(annee), mois_index, j+1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]

    planning = {jour: [] for jour in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        if pd.isna(row["date_arrivee"]) or pd.isna(row["date_depart"]):
            continue
        debut = pd.to_datetime(row["date_arrivee"]).date()
        fin = pd.to_datetime(row["date_depart"]).date()
        for jour in jours:
            if debut <= jour < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
                planning[jour].append(f"{icone} {row['nom_client']}")

    tableau = []
    for semaine in calendar.monthcalendar(int(annee), mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                jour_date = date(int(annee), mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning[jour_date])
                ligne.append(contenu)
        tableau.append(ligne)

    st.table(pd.DataFrame(tableau, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

# ▶️ Application principale
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    uploader_excel()
    df = charger_donnees()
    telecharger_fichier_excel(df)

    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "➕ Ajouter",
        "📅 Calendrier",
        "📊 Rapport"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
    elif onglet == "➕ Ajouter":
        ajouter_reservation(df)
    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)
    elif onglet == "📊 Rapport":
        afficher_rapport(df)

if __name__ == "__main__":
    main()
