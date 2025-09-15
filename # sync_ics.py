# sync_ics.py
import json
import pandas as pd
from app import charger_donnees, sauvegarder_donnees, synchroniser_plateformes

def main():
    df, _ = charger_donnees()
    df_updated = synchroniser_plateformes(df)
    sauvegarder_donnees(df_updated)
    print(f"[{datetime.now()}] Synchronisation ICS terminée.")

if __name__ == "__main__":
    main()
