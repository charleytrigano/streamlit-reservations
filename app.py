import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta, datetime
from io import BytesIO
from urllib.parse import quote
import requests
import base64
import json
import os
import re

FICHIER = "reservations.xlsx"

# ==================== Utils généraux ====================

def to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        # gère 'YYYYMMDD', 'YYYY-MM-DD', datetimes, etc.
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoie/complète : dates -> date(); montants 2 décimales; charges/% ; nuitées; AAAA/MM; colonnes minimales."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()

    # Dates -> date
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = df["date_arrivee"].apply(to_date_only)
    if "date_depart" in df.columns:
        df["date_depart"] = df["date_depart"].apply(to_date_only)

    # Numériques
    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Calculs charges / %
    if "prix_brut" in df.columns and "prix_net" in df.columns:
        if "charges" not in df.columns:
            df["charges"] = df["prix_brut"] - df["prix_net"]
        if "%" not in df.columns:
            with pd.option_context("mode.use_inf_as_na", True):
                df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    # Nuitées
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else None
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

    # AAAA / MM (depuis date_arrivee)
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
        df["MM"] = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)
        df["AAAA"] = pd.to_numeric(df["AAAA"], errors="coerce").astype("Int64")
        df["MM"] = pd.to_numeric(df["MM"], errors="coerce").astype("Int64")

    # Colonnes minimales
    defaults = {
        "plateforme": "Autre",
        "nom_client": "",
        "telephone": "",
    }
    for k, v in defaults.items():
        if k not in df.columns:
            df[k] = v

    # Nettoyer téléphone : enlever éventuelle apostrophe utilisée pour forcer Excel à garder le '+'
    if "telephone" in df.columns:
        def _clean_tel(x):
            s = "" if pd.isna(x) else str(x).strip()
            if s.startswith("'"):
                s = s[1:]
            return s
        df["telephone"] = df["telephone"].apply(_clean_tel)

    cols_order = ["nom_client","plateforme","telephone","date_arrivee","date_depart","nuitees",
                  "prix_brut","prix_net","charges","%","AAAA","MM","ical_uid"]
    ordered = [c for c in cols_order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

def _marque_totaux(df: pd.DataFrame) -> pd.Series:
    """Détecte une ligne 'total' pour la repousser en bas (nom/plateforme == 'total' ou montants sans dates)."""
    if df is None or df.empty:
        return pd.Series([], dtype=bool)
    mask = pd.Series(False, index=df.index)
    for col in ["nom_client", "plateforme"]:
        if col in df.columns:
            m = df[col].astype(str).str.strip().str.lower().eq("total")
            mask = mask | m
    has_no_dates = pd.Series(True, index=df.index)
    if "date_arrivee" in df.columns:
        has_no_dates &= df["date_arrivee"].isna()
    if "date_depart" in df.columns:
        has_no_dates &= df["date_depart"].isna()
    has_money = pd.Series(False, index=df.index)
    for c in ["prix_brut","prix_net","charges"]:
        if c in df.columns:
            has_money |= df[c].notna()
    return mask | (has_no_dates & has_money)

def _trier_et_recoller_totaux(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    tot_mask = _marque_totaux(df)
    df_total = df[tot_mask].copy()
    df_core = df[~tot_mask].copy()
    by_cols = [c for c in ["date_arrivee","nom_client"] if c in df_core.columns]
    if by_cols:
        df_core = df_core.sort_values(by=by_cols, na_position="last").reset_index(drop=True)
    out = pd.concat([df_core, df_total], ignore_index=True)
    return out

# ==================== Excel I/O ====================

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return pd.DataFrame()
    try:
        df = pd.read_excel(FICHIER)
        df = ensure_schema(df)
        df = _trier_et_recoller_totaux(df)
        return df
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return pd.DataFrame()

def sauvegarder_donnees(df: pd.DataFrame):
    """Sauvegarde en Excel; force colonne téléphone en texte grâce à l'apostrophe (préserve le '+')."""
    df = _trier_et_recoller_totaux(ensure_schema(df))
    df_to_save = df.copy()
    if "telephone" in df_to_save.columns:
        def _to_excel_text(s):
            s = "" if pd.isna(s) else str(s).strip()
            if s and not s.startswith("'"):
                s = "'" + s
            return s
        df_to_save["telephone"] = df_to_save["telephone"].apply(_to_excel_text)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as writer:
            df_to_save.to_excel(writer, index=False)
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer un fichier Excel", type=["xlsx"])
    if up is not None:
        try:
            df_new = pd.read_excel(up)
            df_new = _trier_et_recoller_totaux(ensure_schema(df_new))
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            _trier_et_recoller_totaux(ensure_schema(df)).to_excel(writer, index=False)
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = None

    st.sidebar.download_button(
        "📥 Télécharger le fichier Excel",
        data=data_xlsx if data_xlsx else b"",
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(data_xlsx is None),
    )

# ==================== GitHub Save ====================

def _github_headers(token: str):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

def github_save_file(binary: bytes):
    """Enregistre reservations.xlsx dans un repo GitHub via l'API. Nécessite st.secrets:
       GITHUB_TOKEN, GITHUB_REPO (owner/repo), GITHUB_BRANCH, GITHUB_PATH
    """
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo = st.secrets["GITHUB_REPO"]
        branch = st.secrets.get("GITHUB_BRANCH", "main")
        path = st.secrets.get("GITHUB_PATH", "reservations.xlsx")
    except Exception:
        st.error("Secrets GitHub manquants. Ajoute GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH, GITHUB_PATH dans Settings > Secrets.")
        return False

    api_base = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = _github_headers(token)

    # 1) Récupérer le SHA si le fichier existe
    params = {"ref": branch}
    r_get = requests.get(api_base, headers=headers, params=params)
    sha = None
    if r_get.status_code == 200:
        sha = r_get.json().get("sha")

    # 2) PUT
    content_b64 = base64.b64encode(binary).decode("utf-8")
    payload = {
        "message": f"Update {path} via Streamlit",
        "content": content_b64,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r_put = requests.put(api_base, headers=headers, data=json.dumps(payload))
    if r_put.status_code in (200, 201):
        st.success("✅ Sauvegarde GitHub réussie.")
        return True
    else:
        st.error(f"❌ Échec GitHub : {r_put.status_code}: {r_put.text}")
        return False

def sidebar_github_controls(df: pd.DataFrame):
    st.sidebar.markdown("---")
    st.sidebar.subheader("☁️ Sauvegarde GitHub (optionnel)")
    c1, c2 = st.sidebar.columns(2)
    if c1.button("Tester GitHub"):
        # test simple : envoie un petit fichier texte
        test_bytes = b"Streamlit test " + datetime.now().isoformat().encode("utf-8")
        # on n'écrase pas le XLSX en test, on tente juste un PUT sur le chemin défini
        ok = github_save_file(test_bytes)
        if ok:
            st.sidebar.success("Test : OK (le contenu du fichier du repo a été remplacé par un test).")
        else:
            st.sidebar.error("Test : échec.")
    if c2.button("Sauvegarder XLSX -> GitHub"):
        buf = BytesIO()
        try:
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                _trier_et_recoller_totaux(ensure_schema(df)).to_excel(writer, index=False)
            ok = github_save_file(buf.getvalue())
        except Exception as e:
            st.sidebar.error(f"Erreur export: {e}")

# ==================== Vues ====================

def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")
    show = _trier_et_recoller_totaux(ensure_schema(df)).copy()
    for col in ["date_arrivee","date_depart"]:
        if col in show.columns:
            show[col] = show[col].apply(format_date_str)
    st.dataframe(show, use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    with st.form("ajout_resa"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone (format +33...)")

        # DATES persistantes
        if "ajout_arrivee" not in st.session_state:
            st.session_state.ajout_arrivee = date.today()

        arrivee = st.date_input("Date d’arrivée", key="ajout_arrivee")
        min_dep = st.session_state.ajout_arrivee + timedelta(days=1)

        if "ajout_depart" not in st.session_state or not isinstance(st.session_state.ajout_depart, date):
            st.session_state.ajout_depart = min_dep
        elif st.session_state.ajout_depart < min_dep:
            st.session_state.ajout_depart = min_dep

        depart = st.date_input("Date de départ", key="ajout_depart", min_value=min_dep)

        prix_brut = st.number_input("Prix brut (€)", min_value=0.0, step=1.0, format="%.2f")
        prix_net = st.number_input("Prix net (€)", min_value=0.0, step=1.0, format="%.2f",
                                   help="Doit être ≤ prix brut.")
        charges_calc = max(prix_brut - prix_net, 0.0)
        pct_calc = (charges_calc / prix_brut * 100) if prix_brut > 0 else 0.0

        st.number_input("Charges (€)", value=round(charges_calc, 2), step=0.01, format="%.2f", disabled=True)
        st.number_input("Commission (%)", value=round(pct_calc, 2), step=0.01, format="%.2f", disabled=True)

        ok = st.form_submit_button("Enregistrer")

    if ok:
        if prix_net > prix_brut:
            st.error("Le prix net ne peut pas être supérieur au prix brut.")
            return
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return

        ligne = {
            "nom_client": (nom or "").strip(),
            "plateforme": plateforme,
            "telephone": (tel or "").strip(),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": float(prix_brut),
            "prix_net": float(prix_net),
            "charges": round(charges_calc, 2),
            "%": round(pct_calc, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        df2 = _trier_et_recoller_totaux(df2)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune réservation.")
        return

    df["identifiant"] = df["nom_client"].astype(str) + " | " + df["date_arrivee"].apply(format_date_str)
    choix = st.selectbox("Choisir une réservation", df["identifiant"])
    idx = df.index[df["identifiant"] == choix]
    if len(idx) == 0:
        st.warning("Sélection invalide.")
        return
    i = idx[0]

    with st.form("form_modif"):
        nom = st.text_input("Nom du client", df.at[i, "nom_client"])
        plateformes = ["Booking","Airbnb","Autre"]
        index_pf = plateformes.index(df.at[i,"plateforme"]) if df.at[i,"plateforme"] in plateformes else 2
        plateforme = st.selectbox("Plateforme", plateformes, index=index_pf)
        tel = st.text_input("Téléphone", df.at[i, "telephone"] if "telephone" in df.columns else "")
        arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"] if isinstance(df.at[i, "date_arrivee"], date) else date.today())
        depart = st.date_input("Départ", df.at[i, "date_depart"] if isinstance(df.at[i, "date_depart"], date) else arrivee + timedelta(days=1))
        brut = st.number_input("Prix brut (€)", value=float(df.at[i, "prix_brut"]) if pd.notna(df.at[i, "prix_brut"]) else 0.0, format="%.2f")
        net = st.number_input("Prix net (€)", value=float(df.at[i, "prix_net"]) if pd.notna(df.at[i, "prix_net"]) else 0.0, max_value=max(0.0,float(brut)), format="%.2f")
        c1, c2 = st.columns(2)
        b_modif = c1.form_submit_button("💾 Enregistrer")
        b_del = c2.form_submit_button("🗑 Supprimer")

    if b_modif:
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[i, "nom_client"] = nom.strip()
        df.at[i, "plateforme"] = plateforme
        df.at[i, "telephone"] = tel.strip()
        df.at[i, "date_arrivee"] = arrivee
        df.at[i, "date_depart"] = depart
        df.at[i, "prix_brut"] = float(brut)
        df.at[i, "prix_net"] = float(net)
        df.at[i, "charges"] = round(brut - net, 2)
        df.at[i, "%"] = round(((brut - net) / brut * 100) if brut else 0, 2)
        df.at[i, "nuitees"] = (depart - arrivee).days
        df.at[i, "AAAA"] = arrivee.year
        df.at[i, "MM"] = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df)
        st.success("✅ Réservation modifiée")
        st.rerun()

    if b_del:
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("🗑 Réservation supprimée")
        st.rerun()

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier mensuel")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, (date.today().month - 1)))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = st.selectbox("Année", annees, index=max(0, len(annees) - 1))
    mois_index = list(calendar.month_name).index(mois_nom)

    jours = [date(annee, mois_index, j+1) for j in range(calendar.monthrange(annee, mois_index)[1])]
    planning = {j: [] for j in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

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

    st.table(pd.DataFrame(table, columns=["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]))

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    col1, col2, col3 = st.columns(3)
    plateformes = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    with col1:
        filtre_plateforme = st.selectbox("Plateforme", plateformes)
    annees_uniques = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annees = ["Toutes"] + annees_uniques
    with col2:
        filtre_annee = st.selectbox("Année", annees)
    mois_map = {i: calendar.month_name[i] for i in range(1, 13)}
    mois_options = ["Tous"] + [f"{i:02d} - {mois_map[i]}" for i in range(1, 13)]
    with col3:
        filtre_mois_label = st.selectbox("Mois", mois_options)

    data = df.copy()
    if filtre_plateforme != "Toutes":
        data = data[data["plateforme"] == filtre_plateforme]
    if filtre_annee != "Toutes":
        data = data[data["AAAA"] == int(filtre_annee)]
    if filtre_mois_label != "Tous":
        mois_num = int(filtre_mois_label.split(" - ")[0])
        data = data[data["MM"] == mois_num]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    stats = (
        data.dropna(subset=["AAAA", "MM"])
            .groupby(["AAAA", "MM", "plateforme"], dropna=True)
            .agg(
                prix_brut=("prix_brut", "sum"),
                prix_net=("prix_net", "sum"),
                charges=("charges", "sum"),
                nuitees=("nuitees", "sum"),
            ).reset_index()
    )
    if stats.empty:
        st.info("Aucune statistique à afficher avec ces filtres.")
        return

    stats["mois_txt"] = stats["MM"].astype(int).apply(lambda x: calendar.month_abbr[x])
    stats["periode"] = stats["mois_txt"] + " " + stats["AAAA"].astype(int).astype(str)

    st.dataframe(
        stats[["AAAA", "MM", "periode", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]],
        use_container_width=True
    )
    st.markdown("### 💰 Revenus bruts")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="prix_brut").fillna(0))
    st.markdown("### 💸 Charges")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="charges").fillna(0))
    st.markdown("### 🛌 Nuitées")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="nuitees").fillna(0))

    out = BytesIO()
    try:
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            stats.to_excel(writer, index=False, sheet_name="Rapport")
        data_xlsx = out.getvalue()
    except Exception as e:
        st.error(f"Export XLSX indisponible : {e}")
        data_xlsx = None

    if data_xlsx:
        st.download_button(
            "📥 Exporter le rapport (XLSX)",
            data=data_xlsx,
            file_name="rapport_filtre.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = st.selectbox("Année", annees) if annees else None
    mois = st.selectbox("Mois", ["Tous"] + list(range(1,13)))

    data = df.copy()
    if annee:
        data = data[data["AAAA"] == annee]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]
    if data.empty:
        st.info("Aucune donnée pour cette période.")
        return

    with pd.option_context('mode.use_inf_as_na', True):
        if "nuitees" in data.columns and "prix_brut" in data.columns:
            data["prix_brut/nuit"] = (data["prix_brut"] / data["nuitees"]).round(2).fillna(0)
        if "nuitees" in data.columns and "prix_net" in data.columns:
            data["prix_net/nuit"] = (data["prix_net"] / data["nuitees"]).round(2).fillna(0)

    cols = ["nom_client","plateforme","date_arrivee","date_depart","nuitees",
            "prix_brut","prix_net","charges","%","prix_brut/nuit","prix_net/nuit","telephone"]
    cols = [c for c in cols if c in data.columns]

    show = data.copy()
    for c in ["date_arrivee","date_depart"]:
        if c in show.columns:
            show[c] = show[c].apply(format_date_str)

    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger la liste (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

def vue_sms(df: pd.DataFrame):
    st.title("📱 Envoyer des SMS (via ton téléphone)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    today = date.today()
    data = df[(df["date_arrivee"].apply(lambda d: isinstance(d, date) and d >= today))].copy()
    if data.empty:
        st.info("Aucune réservation à venir.")
        return

    st.caption("Clique sur 📲 pour ouvrir l'appli Messages de ton Google Pixel avec le SMS pré-rempli.")

    # Modèle robuste pour SMS (évite espaces multiples compressés par les apps SMS)
    TEMPLATE_SMS = (
        "VILLA TOBIAS\n"
        "Plateforme : {plateforme}\n"
        "Date d'arrivee : {date_arrivee}\n"
        "Date depart : {date_depart}\n"
        "Nombre de nuitees : {nuitees}\n"
        "\n"
        "Bonjour {nom_client}\n"
        "Telephone : {telephone}\n"
        "\n"
        "Nous sommes heureux de vous accueillir prochainement et vous prions de bien vouloir nous communiquer votre heure d'arrivee. "
        "Nous vous attendrons sur place pour vous remettre les cles de l'appartement et vous indiquer votre emplacement de parking. "
        "Nous vous souhaitons un bon voyage et vous disons a demain.\n"
        "\n"
        "Annick & Charley"
    )

    def build_sms(r):
        return TEMPLATE_SMS.format(
            plateforme=(r.get("plateforme") or ""),
            date_arrivee=format_date_str(r.get("date_arrivee")),
            date_depart=format_date_str(r.get("date_depart")),
            nuitees=(r.get("nuitees") or 0),
            nom_client=(r.get("nom_client") or ""),
            telephone=(r.get("telephone") or "")
        )

    for _, r in data.sort_values(by=["date_arrivee","nom_client"]).iterrows():
        nom = str(r.get("nom_client","")).strip() or "—"
        plate = str(r.get("plateforme","")).strip() or "—"
        d1 = format_date_str(r.get("date_arrivee"))
        d2 = format_date_str(r.get("date_depart"))
        nuit = r.get("nuitees") or 0
        tel = str(r.get("telephone") or "").strip()

        message = build_sms(r)

        cols = st.columns([3,2,2,2,2,2])
        cols[0].markdown(f"**{nom}**")
        cols[1].markdown(f"**Plateforme**<br>{plate}", unsafe_allow_html=True)
        cols[2].markdown(f"**Arrivée**<br>{d1}", unsafe_allow_html=True)
        cols[3].markdown(f"**Départ**<br>{d2}", unsafe_allow_html=True)
        cols[4].markdown(f"**Nuitées**<br>{nuit}", unsafe_allow_html=True)

        if tel:
            # smsto: + body= + encodage complet -> préremplit Messages
            lien = f"smsto:{tel}?body={quote(message)}"
            cols[5].markdown(f'<a href="{lien}">📲 Envoyer SMS</a>', unsafe_allow_html=True)
        else:
            cols[5].write("📵 N° manquant")

        with st.expander(f"Aperçu du message pour {nom}"):
            st.text(message)

def _parse_ics_datetime(val: str):
    """Convertit DTSTART/DTEND ICS vers date() (UTC ignoré volontairement, on garde jour civil)."""
    if not val:
        return None
    # Formats courants : 20250102, 20250102T150000Z, 20250102T150000
    m = re.match(r"(\d{4})(\d{2})(\d{2})", val)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except Exception:
        return None

def _parse_ics(text: str):
    """Renvoie une liste de dicts {uid, start, end, summary} pour chaque VEVENT."""
    events = []
    if not text:
        return events
    # gestion des lignes repliées (ICS: si une ligne commence par espace/Tab, c'est la suite)
    unfolded = []
    prev = ""
    for raw_line in text.splitlines():
        if raw_line.startswith((" ", "\t")):
            prev += raw_line.strip()
        else:
            if prev:
                unfolded.append(prev)
            prev = raw_line.strip()
    if prev:
        unfolded.append(prev)

    current = {}
    in_event = False
    for line in unfolded:
        if line == "BEGIN:VEVENT":
            current = {}
            in_event = True
            continue
        if line == "END:VEVENT":
            if in_event and ("DTSTART" in current or "DTEND" in current):
                events.append({
                    "uid": current.get("UID", ""),
                    "start": _parse_ics_datetime(current.get("DTSTART","")),
                    "end": _parse_ics_datetime(current.get("DTEND","")),
                    "summary": current.get("SUMMARY",""),
                })
            in_event = False
            current = {}
            continue
        if in_event:
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.split(";")[0]  # retirer params type TZID
                current[k] = v.strip()
    return events

def vue_sync_ical(df: pd.DataFrame):
    st.title("🔄 Synchroniser iCal (Booking, Airbnb, autres)")
    st.caption("Colle une ou plusieurs URLs .ics. Nous détectons les événements (UID) et évitons les doublons.")

    with st.form("ical_form"):
        plateforme = st.text_input("Nom de la plateforme (ex. Booking, Airbnb, Abritel…)", value="Booking")
        url = st.text_input("URL du calendrier iCal")
        submitted = st.form_submit_button("Charger & Prévisualiser")

    if not submitted:
        st.info("Renseigne une URL iCal pour commencer.")
        return

    if not url:
        st.warning("Veuillez fournir une URL .ics valide.")
        return

    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            st.error(f"Impossible de récupérer l'ICS : {r.status_code}")
            return
        ics_text = r.text
    except Exception as e:
        st.error(f"Erreur réseau : {e}")
        return

    events = _parse_ics(ics_text)
    if not events:
        st.info("Aucun événement trouvé dans ce calendrier.")
        return

    st.success(f"{len(events)} événements trouvés.")
    # UID existants
    uids_existants = set((df["ical_uid"].dropna().astype(str).unique()) if "ical_uid" in df.columns else [])
    a_importer = [ev for ev in events if ev.get("uid") and ev["uid"] not in uids_existants]

    # Aperçu
    apercu = []
    for ev in a_importer:
        arrivee = ev.get("start")
        depart = ev.get("end")
        summary = (ev.get("summary") or "").strip()
        # Heuristique pour extraire un nom depuis SUMMARY
        # Exemples : "John Doe - Booking", "Réservation: Alice", etc.
        nom = summary
        # Nettoyage sommaire
        nom = re.sub(r"(booking|airbnb|reservation|réservation)\W*", "", nom, flags=re.I)
        nom = nom.strip(" -:•|")

        apercu.append({
            "ical_uid": ev.get("uid",""),
            "nom_client": nom,
            "plateforme": plateforme,
            "telephone": "",
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": None,
            "prix_net": None,
        })
    if not apercu:
        st.info("Aucun nouvel événement (tous les UID sont déjà importés).")
        return

    df_prev = pd.DataFrame(apercu)
    df_prev = ensure_schema(df_prev)
    for col in ["date_arrivee","date_depart"]:
        if col in df_prev.columns:
            df_prev[col] = df_prev[col].apply(format_date_str)

    st.markdown("**Aperçu des nouvelles réservations à importer**")
    st.dataframe(df_prev[["nom_client","plateforme","date_arrivee","date_depart","ical_uid"]], use_container_width=True)

    if st.button(f"➡️ Importer {len(apercu)} réservation(s)"):
        # Convertir dates string -> date à l’insertion
        for row in apercu:
            d1, d2 = row.get("date_arrivee"), row.get("date_depart")
            # d1/d2 sont déjà des date() via _parse_ics
            a = {
                "nom_client": row["nom_client"],
                "plateforme": row["plateforme"],
                "telephone": "",
                "date_arrivee": d1,
                "date_depart": d2,
                "prix_brut": None,
                "prix_net": None,
                "charges": None,
                "%": None,
                "nuitees": (d2 - d1).days if isinstance(d1, date) and isinstance(d2, date) else None,
                "AAAA": d1.year if isinstance(d1, date) else None,
                "MM": d1.month if isinstance(d1, date) else None,
                "ical_uid": row["ical_uid"]
            }
            df.loc[len(df)] = a
        df2 = _trier_et_recoller_totaux(ensure_schema(df))
        sauvegarder_donnees(df2)
        st.success("✅ Import iCal effectué.")
        st.rerun()

# ==================== App ====================

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

    st.sidebar.title("📁 Fichier")
    bouton_restaurer()
    df = charger_donnees()
    bouton_telecharger(df)
    sidebar_github_controls(df)

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","📱 SMS","🔄 Synchroniser iCal"]
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
    elif onglet == "📱 SMS":
        vue_sms(df)
    elif onglet == "🔄 Synchroniser iCal":
        vue_sync_ical(df)

if __name__ == "__main__":
    main()