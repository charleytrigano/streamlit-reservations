def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rend le DataFrame cohérent en supportant l'ancien schéma (prix_brut / prix_net / charges / %)
    et le nouveau schéma (montant_net, commissions, frais_cb, montant_brut, menage, taxes_sejour, base, %).
    Ne supprime rien ; complète ce qui manque ; aligne les colonnes.
    """
    # Colonnes de base attendues
    base_cols = [
        "nom_client","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        # ancien schéma:
        "prix_brut","prix_net","charges","%",
        # nouveau schéma:
        "montant_net","commissions","frais_cb","montant_brut","menage","taxes_sejour","base",
        # horodatage / clés / extra:
        "AAAA","MM","ical_uid","commentaire"
    ]

    if df is None or df.empty:
        return pd.DataFrame(columns=base_cols)

    df = df.copy()

    # --- Normalisation dates -> date (sans heure)
    def _to_date_only(x):
        if pd.isna(x) or x is None:
            return None
        try:
            return pd.to_datetime(x).date()
        except Exception:
            return None

    for c in ["date_arrivee","date_depart"]:
        if c in df.columns:
            df[c] = df[c].apply(_to_date_only)

    # --- Téléphone (conserver + et éviter ".0")
    def _normalize_tel(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        s = str(x).strip().replace(" ", "")
        if s.endswith(".0"):
            s = s[:-2]
        return s
    if "telephone" in df.columns:
        df["telephone"] = df["telephone"].apply(_normalize_tel)

    # --- Créer colonnes manquantes (sans écraser l’existant)
    for c in base_cols:
        if c not in df.columns:
            df[c] = pd.NA

    # --- Types numériques sûrs
    num_cols = ["prix_brut","prix_net","charges","%",
                "montant_net","commissions","frais_cb","montant_brut","menage","taxes_sejour","base","nuitees"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # --- AAAA / MM (dérivés de date_arrivee)
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)

    # --- Nuité(e)s
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else pd.NA
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

    # ========== MAPPAGE ANCIEN -> NOUVEAU si nécessaire ==========
    # Si nouveau schéma incomplet, on dérive à partir de l’ancien
    # Hypothèse : ancien charges = prix_brut - prix_net (commission plateforme globale)
    need_new = df["montant_net"].isna() & df["montant_brut"].isna()
    if need_new.any():
        # montant_net (Brut plateforme) ≈ ancien prix_brut
        df.loc[need_new & df["prix_brut"].notna(), "montant_net"] = df.loc[need_new, "prix_brut"]
        # commissions + frais_cb ≈ charges si on n’a pas le détail
        df.loc[need_new & df["charges"].notna(), "commissions"] = df.loc[need_new, "charges"]
        df.loc[need_new & df["charges"].notna(), "frais_cb"] = 0.0
        # montant_brut (Net reçu) ≈ ancien prix_net
        df.loc[need_new & df["prix_net"].notna(), "montant_brut"] = df.loc[need_new, "prix_net"]
        # menage / taxes_sejour à 0 si absents
        df.loc[need_new & df["menage"].isna(), "menage"] = 0.0
        df.loc[need_new & df["taxes_sejour"].isna(), "taxes_sejour"] = 0.0

    # Compléter les dérivations manquantes du NOUVEAU schéma
    # montant_brut = montant_net - commissions - frais_cb
    mask_mb = df["montant_brut"].isna() & df["montant_net"].notna()
    df.loc[mask_mb, "montant_brut"] = (
        df.loc[mask_mb, "montant_net"].fillna(0)
        - df.loc[mask_mb, "commissions"].fillna(0)
        - df.loc[mask_mb, "frais_cb"].fillna(0)
    )

    # base = montant_brut - menage - taxes_sejour
    mask_base = df["base"].isna() & df["montant_brut"].notna()
    df.loc[mask_base, "base"] = (
        df.loc[mask_base, "montant_brut"].fillna(0)
        - df.loc[mask_base, "menage"].fillna(0)
        - df.loc[mask_base, "taxes_sejour"].fillna(0)
    )

    # % = (commissions + frais_cb) / montant_net * 100
    mask_pct_new = df["montant_net"].notna() & (df["montant_net"] != 0)
    df.loc[mask_pct_new, "%"] = (
        (df.loc[mask_pct_new, "commissions"].fillna(0) + df.loc[mask_pct_new, "frais_cb"].fillna(0))
        / df.loc[mask_pct_new, "montant_net"].replace(0, pd.NA)
        * 100
    )

    # ========== MAPPAGE NOUVEAU -> ANCIEN pour compat rapports ==========
    # prix_brut ≈ montant_net ; prix_net ≈ montant_brut ; charges ≈ commissions+frais_cb
    if df["prix_brut"].isna().any() and df["montant_net"].notna().any():
        df.loc[df["prix_brut"].isna(), "prix_brut"] = df.loc[df["prix_brut"].isna(), "montant_net"]
    if df["prix_net"].isna().any() and df["montant_brut"].notna().any():
        df.loc[df["prix_net"].isna(), "prix_net"] = df.loc[df["prix_net"].isna(), "montant_brut"]
    # charges (ancien) si vide = commissions + frais_cb
    mask_ch = df["charges"].isna() & (df["commissions"].notna() | df["frais_cb"].notna())
    df.loc[mask_ch, "charges"] = df.loc[mask_ch, ["commissions","frais_cb"]].fillna(0).sum(axis=1)

    # % (ancien) si absent → charges / prix_brut * 100
    mask_pct_old = df["%"].isna() & df["prix_brut"].notna() & (df["prix_brut"] != 0)
    df.loc[mask_pct_old, "%"] = (df.loc[mask_pct_old, "charges"].fillna(0) / df.loc[mask_pct_old, "prix_brut"]) * 100

    # Arrondis finaux
    for c in ["prix_brut","prix_net","charges","%","montant_net","commissions","frais_cb","montant_brut","menage","taxes_sejour","base"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round(2)

    # Ordre de colonnes propre (on garde les extras à la fin)
    ordered = [c for c in base_cols if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]