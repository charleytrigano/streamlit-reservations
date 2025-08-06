import pandas as pd

FICHIER = "reservations.xlsx"

def charger_donnees():
    # Charger le fichier Excel
    df = pd.read_excel(FICHIER)

    # ✅ Supprimer les colonnes en double
    df = df.loc[:, ~df.columns.duplicated()]

    # ✅ Convertir les dates correctement
    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["date_depart"] = pd.to_datetime(df["date_depart"], errors="coerce")

    # ✅ Nettoyer les lignes sans dates valides
    df = df[df["date_arrivee"].notna() & df["date_depart"].notna()]

    # ✅ Forcer les colonnes numériques
    df["prix_brut"] = pd.to_numeric(df["prix_brut"], errors="coerce").round(2)
    df["prix_net"] = pd.to_numeric(df["prix_net"], errors="coerce").round(2)

    # ✅ Recalculer colonnes nécessaires
    df["charges"] = (df["prix_brut"] - df["prix_net"]).round(2)
    df["%"] = ((df["charges"] / df["prix_brut"]) * 100).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
    df["nuitees"] = (df["date_depart"] - df["date_arrivee"]).dt.days
    df["annee"] = df["date_arrivee"].dt.year
    df["mois"] = df["date_arrivee"].dt.month

    return df
