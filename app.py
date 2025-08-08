# app.py — version complète et stable

import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta, datetime
from io import BytesIO
import os

FICHIER = "reservations.xlsx"

# ---------- Utils / Normalisation ----------
def _to_date(s):
    """Coerce vers datetime.date (ou None)."""
    if pd.isna(s):
        return None
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None

def _safe_round(x, nd=2):
    try:
        return round(float(x), nd)
    except Exception:
        return 0.0

def _ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise colonnes clés: dates, numériques, AAAA/MM, charges et % si besoin."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Dates -> date (pas datetime)
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = df["date_arrivee"].apply(_to_date)
    if "date_depart" in df.columns:
        df["date_depart"] = df["date_depart"].apply(_to_date)

    # Calcul nuitees si possible
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else None
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

    # Montants (deux décimales)
    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # charges/% si manquants
    if "prix_brut" in df.columns and "prix_net" in df.columns:
        if "charges" not in df.columns:
            df["charges"] = df["prix_brut"] - df["prix_net"]
        if "%" not in df.columns:
            with pd.option_context('mode.use_inf_as_na', True):
                df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    # AAAA / MM depuis date_arrivee
    if "date_arrivee" in df.columns:
        years = []
        months = []
        for d in df["date_arrivee"]:
            if isinstance(d, date):
                years.append(d.year)
                months.append(d.month)
            else:
                years.append(pd.NA)
                months.append(pd.NA)
        df["AAAA"] = years
        df["MM"] = months

    # Types int propres pour AAAA/MM
    if "AAAA" in df.columns:
        df["AAAA"] = pd.to_numeric(df["AAAA"], errors="coerce").astype("Int64")
    if "MM" in df.columns:
        df["MM"] = pd.to_numeric(df["MM"], errors="coerce").astype("Int64")

    # Defaults manquants
    if "plateforme" not in df.columns:
        df["plateforme"] = "Autre"
    if "nom_client" not in df.columns:
        df["nom_client"] = ""

    # Ordre conseillé de colonnes si présentes
    cols_order = [
        "nom_client", "plateforme", "telephone",
        "date_arrivee", "date_depart", "nuitees",
        "prix_brut", "prix_net", "charges", "%",
        "AAAA", "MM"
    ]
    # remettre ordre sans casser si tout n'existe pas
    ordered = [c for c in cols_order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

# ---------- IO Excel ----------
def charger_donnees() -> pd.DataFrame:
    if os.path.exists(FICHIER):
        try:
            df = pd.read_excel(FICHIER)
            return _ensure_schema(df)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def sauvegarder_donnees(df: pd.DataFrame):
    df = _ensure_schema(df)
    df.to_excel(FICHIER, index=False)

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    _ensure_schema(df).to_excel(buf, index=False)
    st.sidebar.download_button(
        "📥 Télécharger le fichier Excel",
        data=buf.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer un fichier .xlsx", type=["xlsx"])
    if up is not None:
        try:
            df_new = pd.read_excel(up)
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré et normalisé.")
            st.experimental_rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur à l'import : {e}")

# ---------- Vues ----------
def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")
    show = _ensure_schema(df).copy()
    # Affichage propre des dates
    for col in ["date_arrivee", "date_depart"]:
        if col in show.columns:
            show[col] = show[col].apply(lambda d: d.strftime("%Y/%m/%d") if isinstance(d, date) else "")
    st.dataframe(show, use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    with st.form("ajout_resa"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d’arrivée", value=date.today())
        depart = st.date_input("Date de départ", value=arrivee + timedelta(days=1), min_value=arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut (€)", min_value=0.0, step=1.0)
        prix_net = st.number_input("Prix net (€)", min_value=0.0, max_value=prix_brut, step=1.0)
        ok = st.form_submit_button("Enregistrer")
    if ok:
        ligne = {
            "nom_client": nom.strip(),
            "plateforme": plateforme,
            "telephone": tel.strip(),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": _safe_round(prix_brut),
            "prix_net": _safe_round(prix_net),
            "charges": _safe_round(prix_brut - prix_net),
            "%": _safe_round(((prix_brut - prix_net) / prix_brut * 100) if prix_brut else 0),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
        st.experimental_rerun()

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation.")
        return
    df["identifiant"] = df["nom_client"].astype(str) + " | " + df["date_arrivee"].apply(lambda d: d.strftime("%Y/%m/%d") if isinstance(d, date) else "")
    choix = st.selectbox("Choisir une réservation", df["identifiant"])
    idx = df.index[df["identifiant"] == choix]
    if len(idx) == 0:
        st.warning("Sélection invalide.")
        return
    i = idx[0]

    with st.form("form_modif"):
        nom = st.text_input("Nom", df.at[i, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"],
                                  index=["Booking", "Airbnb", "Autre"].index(df.at[i, "plateforme"]) if df.at[i, "plateforme"] in ["Booking", "Airbnb", "Autre"] else 2)
        tel = st.text_input("Téléphone", df.at[i, "telephone"] if "telephone" in df.columns else "")
        arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"] if isinstance(df.at[i, "date_arrivee"], date) else date.today())
        depart = st.date_input("Départ", df.at[i, "date_depart"] if isinstance(df.at[i, "date_depart"], date) else arrivee + timedelta(days=1))
        brut = st.number_input("Prix brut (€)", value=float(df.at[i, "prix_brut"]) if pd.notna(df.at[i, "prix_brut"]) else 0.0)
        net = st.number_input("Prix net (€)", value=float(df.at[i, "prix_net"]) if pd.notna(df.at[i, "prix_net"]) else 0.0, max_value=max(0.0, float(brut)))
        c1, c2 = st.columns(2)
        b_modif = c1.form_submit_button("💾 Enregistrer")
        b_del = c2.form_submit_button("🗑 Supprimer")

    if b_modif:
        df.at[i, "nom_client"] = nom.strip()
        df.at[i, "plateforme"] = plateforme
        df.at[i, "telephone"] = tel.strip()
        df.at[i, "date_arrivee"] = arrivee
        df.at[i, "date_depart"] = depart
        df.at[i, "prix_brut"] = _safe_round(brut)
        df.at[i, "prix_net"] = _safe_round(net)
        df.at[i, "charges"] = _safe_round(brut - net)
        df.at[i, "%"] = _safe_round(((brut - net) / brut * 100) if brut else 0)
        df.at[i, "nuitees"] = (depart - arrivee).days
        df.at[i, "AAAA"] = arrivee.year
        df.at[i, "MM"] = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df)
        st.success("✅ Réservation modifiée")
        st.experimental_rerun()

    if b_del:
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("🗑 Réservation supprimée")
        st.experimental_rerun()

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier mensuel")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    # Choix mois / année
    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:], index=(date.today().month - 1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = st.selectbox("Année", annees, index=max(0, len(annees) - 1))

    mois_index = list(calendar.month_name).index(mois_nom)  # 1..12
    # Créer jours du mois en objets date
    jours = [date(annee, mois_index, j+1) for j in range(calendar.monthrange(annee, mois_index)[1])]
    planning = {j: [] for j in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    # Remplir planning
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

    # Construire tableau calendrier
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

    st.table(pd.DataFrame(table, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    plateformes = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    filtre = st.selectbox("Filtrer par plateforme", plateformes)
    data = df if filtre == "Toutes" else df[df["plateforme"] == filtre]

    if data.empty:
        st.info("Aucune donnée pour ce filtre.")
        return

    # Groupby mensuel
    stats = (
        data
        .dropna(subset=["AAAA", "MM"])
        .groupby(["AAAA", "MM", "plateforme"], dropna=True)
        .agg(prix_brut=("prix_brut", "sum"),
             prix_net=("prix_net", "sum"),
             charges=("charges", "sum"),
             nuitees=("nuitees", "sum"))
        .reset_index()
    )

    if stats.empty:
        st.info("Aucune statistique à afficher.")
        return

    stats["mois_txt"] = stats["MM"].astype(int).apply(lambda x: calendar.month_abbr[x])
    stats["periode"] = stats["mois_txt"] + " " + stats["AAAA"].astype(int).astype(str)

    st.dataframe(stats[["periode", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]], use_container_width=True)

    st.markdown("### 💰 Revenus bruts par mois")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 💸 Charges par mois")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="charges").fillna(0))

    st.markdown("### 🛌 Nuitées par mois")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="nuitees").fillna(0))

def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = _ensure_schema(df)
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
        st.info("Aucun client pour cette période.")
        return

    # Prix/nuit (sécurisé)
    with pd.option_context('mode.use_inf_as_na', True):
        data["prix_brut/nuit"] = (data["prix_brut"] / data["nuitees"]).round(2).fillna(0)
        data["prix_net/nuit"] = (data["prix_net"] / data["nuitees"]).round(2).fillna(0)

    colonnes = ["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees",
                "prix_brut", "prix_net", "charges", "%", "prix_brut/nuit", "prix_net/nuit"]
    colonnes = [c for c in colonnes if c in data.columns]

    show = data.copy()
    for col in ["date_arrivee", "date_depart"]:
        if col in show.columns:
            show[col] = show[col].apply(lambda d: d.strftime("%Y/%m/%d") if isinstance(d, date) else "")
    st.dataframe(show[colonnes], use_container_width=True)

    # Export CSV rapide
    st.download_button(
        "📥 Télécharger la liste (CSV)",
        data=show[colonnes].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

def vue_sms():
    st.title("✉️ Historique SMS")
    st.info("Fonction à brancher selon ton fournisseur (Free Mobile, etc.).")

# ---------- App ----------
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Fichier")
    bouton_restaurer()          # Restaurer .xlsx
    df = charger_donnees()
    bouton_telecharger(df)      # Télécharger .xlsx

    st.sidebar.title("🧭 Menu")
    onglet = st.sidebar.radio(
        "Navigation",
        ["📋 Réservations", "➕ Ajouter", "✏️ Modifier / Supprimer",
         "📅 Calendrier", "📊 Rapport", "👥 Liste clients", "✉️ Historique SMS"]
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
    elif onglet == "✉️ Historique SMS":
        vue_sms()

if __name__ == "__main__":
    main()
