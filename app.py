import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta, datetime
from io import BytesIO
import os
import requests  # SMS
import re
from zoneinfo import ZoneInfo

FICHIER = "reservations.xlsx"

# ==================== CONFIG SMS ====================
# Idéalement, mets ces infos dans Streamlit Cloud → Settings → Secrets
FREE_USER = st.secrets.get("FREE_USER", "12026027")                  # <-- remplace si besoin
FREE_API_KEY = st.secrets.get("FREE_API_KEY", "MF7Qjs3C8KxKHz")      # <-- remplace si besoin
NUM_TELEPHONE_PERSO = st.secrets.get("NUM_TELEPHONE_PERSO", "+33617722379")
SMS_HISTO = "historique_sms.csv"
# ====================================================


# -------------------- Utils --------------------
def to_date_only(x):
    if pd.isna(x):
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise le DF sans changer le modèle de données d'origine."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Dates en 'date' (pas datetime)
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = df["date_arrivee"].apply(to_date_only)
    if "date_depart" in df.columns:
        df["date_depart"] = df["date_depart"].apply(to_date_only)

    # Colonnes montants
    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Calculs si manquants
    if "prix_brut" in df.columns and "prix_net" in df.columns:
        if "charges" not in df.columns:
            df["charges"] = df["prix_brut"] - df["prix_net"]
        if "%" not in df.columns:
            with pd.option_context('mode.use_inf_as_na', True):
                df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    # nuitees
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else None
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

    # AAAA / MM depuis date_arrivee si nécessaire
    if "date_arrivee" in df.columns:
        years, months = [], []
        for d in df["date_arrivee"]:
            if isinstance(d, date):
                years.append(d.year)
                months.append(d.month)
            else:
                years.append(pd.NA)
                months.append(pd.NA)
        df["AAAA"] = years
        df["MM"] = months

    if "AAAA" in df.columns:
        df["AAAA"] = pd.to_numeric(df["AAAA"], errors="coerce").astype("Int64")
    if "MM" in df.columns:
        df["MM"] = pd.to_numeric(df["MM"], errors="coerce").astype("Int64")

    # Valeurs par défaut
    if "plateforme" not in df.columns:
        df["plateforme"] = "Autre"
    if "nom_client" not in df.columns:
        df["nom_client"] = ""

    # Ordre conseillé (si colonnes présentes)
    order = ["nom_client","plateforme","telephone","date_arrivee","date_depart","nuitees",
             "prix_brut","prix_net","charges","%","AAAA","MM","uid_ical"]
    ordered = [c for c in order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

# -------- Détection & tri avec lignes "Total" --------
def _marque_totaux(df: pd.DataFrame) -> pd.Series:
    """Détecte les lignes de total (robuste) : 'total' dans nom_client/plateforme,
    ou lignes sans dates mais avec des montants."""
    if df is None or df.empty:
        return pd.Series([], dtype=bool)

    mask = pd.Series(False, index=df.index)

    # a) 'total' écrit dans nom_client ou plateforme
    for col in ["nom_client", "plateforme"]:
        if col in df.columns:
            m = df[col].astype(str).str.strip().str.lower().eq("total")
            mask = mask | m

    # b) lignes sans dates mais avec des montants => souvent un total
    has_no_dates = pd.Series(True, index=df.index)
    if "date_arrivee" in df.columns:
        has_no_dates = has_no_dates & df["date_arrivee"].isna()
    if "date_depart" in df.columns:
        has_no_dates = has_no_dates & df["date_depart"].isna()

    has_money = pd.Series(False, index=df.index)
    for col in ["prix_brut", "prix_net", "charges"]:
        if col in df.columns:
            has_money = has_money | df[col].notna()

    mask = mask | (has_no_dates & has_money)
    return mask

def _trier_et_recoller_totaux(df: pd.DataFrame) -> pd.DataFrame:
    """Sépare les totaux, trie le reste par date_arrivee puis recolle les totaux en bas."""
    if df is None or df.empty:
        return df

    df = df.copy()
    # Séparer totaux
    mask_total = _marque_totaux(df)
    df_tot = df[mask_total].copy()
    df_core = df[~mask_total].copy()

    # Trier le cœur par date_arrivee (+ nom pour stabiliser)
    by_cols = [c for c in ["date_arrivee", "nom_client"] if c in df_core.columns]
    if by_cols:
        df_core = df_core.sort_values(by=by_cols, na_position="last").reset_index(drop=True)

    # Recolle les totaux en bas (en conservant leur ordre d'origine)
    out = pd.concat([df_core, df_tot], ignore_index=True)
    return out


# -------------------- IO Excel --------------------
def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return pd.DataFrame()
    try:
        df = ensure_schema(pd.read_excel(FICHIER))
        df = _trier_et_recoller_totaux(df)  # tri au chargement
        return df
    except Exception:
        return pd.DataFrame()

def sauvegarder_donnees(df: pd.DataFrame):
    # ⚠️ Forcer openpyxl même pour un chemin disque + tri avant écriture
    df = ensure_schema(df)
    df = _trier_et_recoller_totaux(df)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
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
    # ⚠️ Forcer openpyxl pour BytesIO
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            _trier_et_recoller_totaux(ensure_schema(df)).to_excel(writer, index=False)
        data_xlsx = buf.getvalue()
    except Exception:
        st.sidebar.error("Export XLSX indisponible. Ajoute 'openpyxl' dans requirements.txt")
        data_xlsx = None

    st.sidebar.download_button(
        "📥 Télécharger le fichier Excel",
        data=data_xlsx if data_xlsx else b"",
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(data_xlsx is None),
    )


# -------------------- SMS --------------------
def envoyer_sms(message: str) -> bool:
    """Envoi un SMS via l’API Free Mobile (vers la ligne associée au compte Free)."""
    try:
        url = "https://smsapi.free-mobile.fr/sendmsg"
        params = {"user": FREE_USER, "pass": FREE_API_KEY, "msg": message}
        r = requests.get(url, params=params, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def enregistrer_sms(nom: str, tel: str, contenu: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ligne = {"nom": nom, "telephone": tel, "message": contenu, "horodatage": now}
    try:
        if os.path.exists(SMS_HISTO):
            dfh = pd.read_csv(SMS_HISTO)
            dfh = pd.concat([dfh, pd.DataFrame([ligne])], ignore_index=True)
        else:
            dfh = pd.DataFrame([ligne])
        dfh.to_csv(SMS_HISTO, index=False)
    except Exception:
        pass

def notifier_arrivees_prochaines(df: pd.DataFrame):
    """
    Envoie un SMS pour chaque arrivée prévue DEMAIN.
    Envoi sur la ligne Free Mobile (vous), et enregistre un historique.
    """
    if df is None or df.empty:
        return 0, 0
    demain = date.today() + timedelta(days=1)
    a_notifier = df[df["date_arrivee"] == demain]
    envoyes = 0
    erreurs = 0
    for _, row in a_notifier.iterrows():
        nom = str(row.get("nom_client", "")).strip()
        plate = str(row.get("plateforme", ""))
        d1 = row.get("date_arrivee")
        d2 = row.get("date_depart")
        d1txt = d1.strftime("%Y/%m/%d") if isinstance(d1, date) else str(d1)
        d2txt = d2.strftime("%Y/%m/%d") if isinstance(d2, date) else str(d2)
        message = (
            f"VILLA TOBIAS - {plate}\n"
            f"Bonjour {nom}. Votre séjour est prévu du {d1txt} au {d2txt}.\n"
            f"Afin de vous accueillir, merci de nous confirmer votre heure d’arrivée.\n"
            f"Un parking est à votre disposition sur place. À demain."
        )
        ok = envoyer_sms(message)
        if ok:
            envoyes += 1
        else:
            erreurs += 1
        enregistrer_sms(nom, str(row.get("telephone", "")), message)
    return envoyes, erreurs


# -------------------- iCal helpers --------------------
def _ics_get_field(lines, key):
    for ln in lines:
        if ln.startswith(key + ":") or ln.startswith(key + ";"):
            return ln.split(":", 1)[1].strip()
    return None

def _ics_unfold(text):
    out = []
    buf = ""
    for ln in text.splitlines():
        if ln.startswith(" ") or ln.startswith("\t"):
            buf += ln[1:]
        else:
            if buf:
                out.append(buf)
            buf = ln
    if buf:
        out.append(buf)
    return out

def _parse_ics_datetime(val: str) -> datetime | None:
    try:
        if re.fullmatch(r"\d{8}", val):
            return datetime.strptime(val, "%Y%m%d").replace(tzinfo=ZoneInfo("Europe/Paris"))
        dt = pd.to_datetime(val, utc=True, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.tz_convert(ZoneInfo("Europe/Paris")).to_pydatetime()
    except Exception:
        return None

def _to_local_date_only(val: str) -> date | None:
    dt = _parse_ics_datetime(val)
    if dt is None:
        return None
    return dt.date()

def fetch_ics(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return None

def parse_ics(text: str, plateforme: str) -> pd.DataFrame:
    """Retourne un DF avec: date_arrivee, date_depart, uid_ical, nom_client (si trouvé), plateforme, status."""
    if not text:
        return pd.DataFrame()

    lines = _ics_unfold(text)
    events = []
    cur = []
    inside = False
    for ln in lines:
        if ln.startswith("BEGIN:VEVENT"):
            inside = True
            cur = []
        elif ln.startswith("END:VEVENT"):
            inside = False
            uid = _ics_get_field(cur, "UID")
            status = (_ics_get_field(cur, "STATUS") or "").upper()
            summary = _ics_get_field(cur, "SUMMARY") or ""
            descr = _ics_get_field(cur, "DESCRIPTION") or ""
            dtstart = _ics_get_field(cur, "DTSTART")
            dtend = _ics_get_field(cur, "DTEND")

            # skip annulés / blocked
            if "CANCELLED" in status:
                continue
            if "BLOCK" in summary.upper():
                continue

            d1 = _to_local_date_only(dtstart) if dtstart else None
            d2 = _to_local_date_only(dtend) if dtend else None

            # essaie d’extraire un nom (heuristique simple)
            nom = ""
            m1 = re.search(r"(Guest|Client)\s*[:=-]\s*([^\n\r|]+)", descr, flags=re.I)
            if m1:
                nom = m1.group(2).strip()
            elif summary and summary.strip().lower() not in ("booked","reserved","reservation"):
                nom = summary.strip()

            events.append({
                "uid_ical": uid or "",
                "status": status or "CONFIRMED",
                "nom_client": nom,
                "plateforme": plateforme,
                "date_arrivee": d1,
                "date_depart": d2,
            })
        else:
            if inside:
                cur.append(ln)

    df = pd.DataFrame(events)
    if df.empty:
        return df

    # garde seulement les lignes avec dates valides
    df = df[(df["date_arrivee"].notna()) & (df["date_depart"].notna())].copy()

    # complète AAAA/MM
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)

    # initialise montants à 0.0 (tu compléteras ensuite)
    for c in ["prix_brut","prix_net","charges","%","nuitees"]:
        df[c] = pd.NA
    df["prix_brut"] = 0.0
    df["prix_net"]  = 0.0
    df["charges"]   = 0.0
    df["%"]         = 0.0
    df["nuitees"]   = (df["date_depart"] - df["date_arrivee"]).apply(lambda d: d.days)

    return df


# -------------------- Vues --------------------
def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")
    show = _trier_et_recoller_totaux(ensure_schema(df)).copy()
    for col in ["date_arrivee","date_depart"]:
        if col in show.columns:
            show[col] = show[col].apply(lambda d: d.strftime("%Y/%m/%d") if isinstance(d, date) else "")
    st.dataframe(show, use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    with st.form("ajout_resa"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking","Airbnb","Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d’arrivée", value=date.today())
        depart = st.date_input("Date de départ", value=arrivee + timedelta(days=1), min_value=arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut (€)", min_value=0.0, step=1.0, format="%.2f")
        prix_net = st.number_input("Prix net (€)", min_value=0.0, max_value=prix_brut, step=1.0, format="%.2f")
        ok = st.form_submit_button("Enregistrer")

    if ok:
        ligne = {
            "nom_client": nom.strip(),
            "plateforme": plateforme,
            "telephone": tel.strip(),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": float(prix_brut),
            "prix_net": float(prix_net),
            "charges": round(prix_brut - prix_net, 2),
            "%": round(((prix_brut - prix_net) / prix_brut * 100) if prix_brut else 0, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        df2 = _trier_et_recoller_totaux(df2)  # tri immédiat avant sauvegarde
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = _trier_et_recoller_totaux(ensure_schema(df))
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
        nom = st.text_input("Nom du client", df.at[i, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking","Airbnb","Autre"],
                                  index=["Booking","Airbnb","Autre"].index(df.at[i,"plateforme"]) if df.at[i,"plateforme"] in ["Booking","Airbnb","Autre"] else 2)
        tel = st.text_input("Téléphone", df.at[i, "telephone"] if "telephone" in df.columns else "")
        arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"] if isinstance(df.at[i, "date_arrivee"], date) else date.today())
        depart = st.date_input("Départ", df.at[i, "date_depart"] if isinstance(df.at[i, "date_depart"], date) else arrivee + timedelta(days=1))
        brut = st.number_input("Prix brut (€)", value=float(df.at[i, "prix_brut"]) if pd.notna(df.at[i, "prix_brut"]) else 0.0, format="%.2f")
        net = st.number_input("Prix net (€)", value=float(df.at[i, "prix_net"]) if pd.notna(df.at[i, "prix_net"]) else 0.0, max_value=max(0.0,float(brut)), format="%.2f")
        c1, c2 = st.columns(2)
        b_modif = c1.form_submit_button("💾 Enregistrer")
        b_del = c2.form_submit_button("🗑 Supprimer")

    if b_modif:
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
        df = _trier_et_recoller_totaux(df)
        sauvegarder_donnees(df)
        st.success("✅ Réservation modifiée")
        st.rerun()

    if b_del:
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        df2 = _trier_et_recoller_totaux(df2)
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
    mois_index = list(calendar.month_name).index(mois_nom)  # 1..12

    # Jours du mois
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

    # --- Filtres ---
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

    # --- Application des filtres ---
    data = df.copy()
    if filtre_plateforme != "Toutes":
        data = data[data["plateforme"] == filtre_plateforme]
    if filtre_annee != "Toutes":
        data = data[data["AAAA"] == int(filtre_annee)]
    if filtre_mois_label != "Tous":
        mois_num = int(filtre_mois_label.split(" - ")[0])  # "03 - March" -> 3
        data = data[data["MM"] == mois_num]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # --- Agrégation ---
    stats = (
        data
        .dropna(subset=["AAAA", "MM"])
        .groupby(["AAAA", "MM", "plateforme"], dropna=True)
        .agg(
            prix_brut=("prix_brut", "sum"),
            prix_net=("prix_net", "sum"),
            charges=("charges", "sum"),
            nuitees=("nuitees", "sum"),
        )
        .reset_index()
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

    # --- Graphiques ---
    st.markdown("### 💰 Revenus bruts")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 💸 Charges")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="charges").fillna(0))

    st.markdown("### 🛌 Nuitées")
    st.bar_chart(stats.pivot(index="periode", columns="plateforme", values="nuitees").fillna(0))

    # --- Export XLSX du tableau agrégé filtré (openpyxl) ---
    out = BytesIO()
    try:
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            stats.to_excel(writer, index=False, sheet_name="Rapport")
        data_xlsx = out.getvalue()
    except Exception:
        st.error("Export XLSX indisponible. Ajoute 'openpyxl' dans requirements.txt")
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
            "prix_brut","prix_net","charges","%","prix_brut/nuit","prix_net/nuit"]
    cols = [c for c in cols if c in data.columns]
    show = data.copy()
    for col in ["date_arrivee","date_depart"]:
        if col in show.columns:
            show[col] = show[col].apply(lambda d: d.strftime("%Y/%m/%d") if isinstance(d, date) else "")
    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger la liste (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

def vue_sms(df: pd.DataFrame):
    st.title("✉️ Historique & envoi de SMS")

    # Envoi manuel des rappels "arrivées demain"
    if st.button("🔔 Envoyer les SMS pour les arrivées de demain"):
        envoyes, erreurs = notifier_arrivees_prochaines(df)
        st.success(f"SMS envoyés: {envoyes} • Échecs: {erreurs}")

    st.markdown("#### Historique des SMS envoyés")
    if os.path.exists(SMS_HISTO):
        dfh = pd.read_csv(SMS_HISTO)
        st.dataframe(dfh, use_container_width=True)

        out = BytesIO()
        try:
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                dfh.to_excel(writer, index=False, sheet_name="Historique_SMS")
            data_xlsx = out.getvalue()
        except Exception:
            st.error("Export XLSX indisponible. Ajoute 'openpyxl' dans requirements.txt")
            data_xlsx = None

        if data_xlsx:
            st.download_button(
                "📥 Télécharger l’historique (XLSX)",
                data=data_xlsx,
                file_name="historique_sms.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        if st.button("🧹 Vider l’historique"):
            try:
                os.remove(SMS_HISTO)
                st.success("Historique supprimé.")
                st.rerun()
            except Exception as e:
                st.error(f"Impossible de supprimer : {e}")
    else:
        st.info("Aucun SMS envoyé pour le moment.")

def vue_sync_ical(df: pd.DataFrame):
    st.title("🔄 Synchroniser iCal (Airbnb / Booking / autres)")
    st.info("Colle ici tes URLs iCal. Je charge un aperçu, puis tu importes ce que tu veux dans Excel. "
            "Les réservations CANCELLED ou Blocked sont ignorées. Déduplication par UID pour éviter les doublons.")

    colA, colB = st.columns(2)
    with colA:
        url1 = st.text_input("URL iCal #1")
        plat1 = st.selectbox("Plateforme #1", ["Airbnb","Booking","Autre"], index=0)
    with colB:
        url2 = st.text_input("URL iCal #2")
        plat2 = st.selectbox("Plateforme #2", ["Airbnb","Booking","Autre"], index=1)

    btn = st.button("📥 Charger l’aperçu")
    if not btn:
        return

    dfs = []
    for url, plat in [(url1, plat1), (url2, plat2)]:
        if url.strip():
            txt = fetch_ics(url.strip())
            if not txt:
                st.error(f"Impossible de charger: {url}")
                continue
            dfe = parse_ics(txt, plat)
            if dfe.empty:
                st.warning(f"Aucun événement exploitable pour {plat}.")
            else:
                dfs.append(dfe)

    if not dfs:
        st.info("Rien à importer.")
        return

    df_new = pd.concat(dfs, ignore_index=True)

    # Déduplication par UID vs Excel existant
    df_exist = ensure_schema(df.copy())
    if "uid_ical" not in df_exist.columns:
        df_exist["uid_ical"] = ""

    uids_exist = set(df_exist["uid_ical"].dropna().astype(str))
    df_new["uid_ical"] = df_new["uid_ical"].fillna("").astype(str)
    df_new = df_new[~df_new["uid_ical"].isin(uids_exist)].copy()

    if df_new.empty:
        st.success("✅ Tous les événements iCal sont déjà importés (aucun nouveau).")
        return

    # Aperçu
    show = df_new.copy()
    for col in ["date_arrivee","date_depart"]:
        show[col] = show[col].apply(lambda d: d.strftime("%Y/%m/%d") if isinstance(d, date) else "")
    st.subheader("Aperçu des nouvelles réservations détectées")
    st.dataframe(show[["plateforme","nom_client","date_arrivee","date_depart","uid_ical"]], use_container_width=True)

    # Sélection
    selection = st.multiselect(
        "Sélectionne les UID à importer",
        options=show["uid_ical"].tolist(),
        default=show["uid_ical"].tolist()
    )

    if st.button("✅ Importer la sélection dans Excel"):
        a_importer = df_new[df_new["uid_ical"].isin(selection)].copy()
        if a_importer.empty:
            st.warning("Aucune sélection.")
            return

        # On ne touche pas aux totaux; on concatène puis on sauvegarde (tri auto)
        df_final = pd.concat([df_exist, a_importer], ignore_index=True)
        sauvegarder_donnees(df_final)
        st.success(f"✅ {len(a_importer)} réservation(s) importée(s).")
        st.rerun()


# -------------------- App --------------------
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

    st.sidebar.title("📁 Fichier")
    bouton_restaurer()
    df = charger_donnees()
    bouton_telecharger(df)

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","✉️ Historique SMS","🔄 Synchroniser iCal"]
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
        vue_sms(df)
    elif onglet == "🔄 Synchroniser iCal":
        vue_sync_ical(df)

if __name__ == "__main__":
    main()
