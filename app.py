# ============================== PART 1/5 — Imports & Helpers ==============================
import os, re, io, calendar
from calendar import Calendar, monthrange
from datetime import datetime, date
from html import escape

import pandas as pd
import streamlit as st

# ============================== FICHIERS ==============================
APARTMENTS_CSV = "apartments.csv"
INDICATIFS_CSV = "indicatifs.csv"

# ============================== INDICATIFS (pays ↔ code) ==============================
_INDICATIFS_FALLBACK = {
    "33": ("France", "🇫🇷"),
    "32": ("Belgique", "🇧🇪"),
    "352": ("Luxembourg", "🇱🇺"),
    "41": ("Suisse", "🇨🇭"),
    "39": ("Italie", "🇮🇹"),
    "34": ("Espagne", "🇪🇸"),
    "351": ("Portugal", "🇵🇹"),
    "49": ("Allemagne", "🇩🇪"),
    "44": ("Royaume-Uni", "🇬🇧"),
    "31": ("Pays-Bas", "🇳🇱"),
    "1": ("États-Unis / Canada", "🇺🇸"),
    "61": ("Australie", "🇦🇺"),
    "81": ("Japon", "🇯🇵"),
    "86": ("Chine", "🇨🇳"),
    "90": ("Turquie", "🇹🇷"),
    "212": ("Maroc", "🇲🇦"),
    "216": ("Tunisie", "🇹🇳"),
    "971": ("Émirats arabes unis", "🇦🇪"),
}

def _read_indicatifs_csv() -> pd.DataFrame:
    """Charge le fichier indicatifs.csv ou crée un DataFrame vide."""
    if not os.path.exists(INDICATIFS_CSV):
        return pd.DataFrame(columns=["indicatif", "pays", "drapeau"])
    try:
        df = pd.read_csv(INDICATIFS_CSV, dtype=str).fillna("")
        if not {"indicatif", "pays", "drapeau"}.issubset(df.columns):
            return pd.DataFrame(columns=["indicatif", "pays", "drapeau"])
        return df
    except Exception:
        return pd.DataFrame(columns=["indicatif", "pays", "drapeau"])

def _save_indicatifs_csv(df: pd.DataFrame):
    """Écrit le DataFrame indicatifs.csv."""
    try:
        df.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")
    except Exception as e:
        st.error(f"Erreur écriture indicatifs.csv : {e}")

def _phone_country(phone: str) -> str:
    """Retourne le pays associé à un numéro de téléphone en lisant indicatifs.csv."""
    if not phone:
        return "Inconnu"
    p = str(phone).strip()
    if p.startswith("+"):
        p1 = p[1:]
    elif p.startswith("00"):
        p1 = p[2:]
    elif p.startswith("0"):
        return "France"
    else:
        p1 = p

    # Charger mapping CSV
    df = _read_indicatifs_csv()
    mapping = {str(r["indicatif"]): (r["pays"], r.get("drapeau", "")) for _, r in df.iterrows() if r["indicatif"]}
    if not mapping:
        mapping = _INDICATIFS_FALLBACK

    for k in sorted(mapping.keys(), key=lambda x: -len(x)):
        if p1.startswith(k):
            pays, drap = mapping[k]
            return f"{pays} {drap}".strip()
    return "Inconnu"

# ============================== HELPERS GÉNÉRIQUES ==============================
def _load_file_bytes(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    sample = raw.decode("utf-8", errors="ignore")
    if ";" in sample:
        delim = ";"
    elif "," in sample:
        delim = ","
    elif "\t" in sample:
        delim = "\t"
    elif "|" in sample:
        delim = "|"
    else:
        delim = ";"
    return pd.read_csv(io.BytesIO(raw), sep=delim, dtype=str).fillna("")

DEFAULT_PALETTE = {
    "Booking": "#003580",
    "Airbnb": "#FF5A5F",
    "Abritel": "#00ADEF",
    "Expedia": "#FEC601",
    "Direct": "#28A745",
}

# ============================== PART 2/5 — Appartements & Chargement ==============================

def _read_apartments_csv() -> pd.DataFrame:
    """Charge apartments.csv (séparateur auto) et normalise {slug, name}."""
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug", "name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug", "name"])

        df.columns = [str(c).strip().lower() for c in df.columns]
        if "slug" not in df.columns:
            df["slug"] = ""
        if "name" not in df.columns:
            df["name"] = ""
        df["slug"] = (
            df["slug"].astype(str)
            .str.replace("\ufeff", "", regex=False)
            .str.strip()
            .str.replace(" ", "-", regex=False)
            .str.replace("_", "-", regex=False)
            .str.lower()
        )
        df["name"] = df["name"].astype(str).str.replace("\ufeff", "", regex=False).str.strip()
        df = df[(df["slug"] != "") & (df["name"] != "")]
        df = df.drop_duplicates(subset=["slug"], keep="first")
        return df[["slug", "name"]]
    except Exception:
        return pd.DataFrame(columns=["slug", "name"])


def _current_apartment() -> dict | None:
    slug = st.session_state.get("apt_slug", "")
    name = st.session_state.get("apt_name", "")
    if slug and name:
        return {"slug": slug, "name": name}
    return None


def _select_apartment_sidebar() -> bool:
    """Affiche le sélecteur d'appartement dans la sidebar."""
    st.sidebar.markdown("### Appartement")
    apts = _read_apartments_csv()
    if apts.empty:
        st.sidebar.warning("Aucun appartement trouvé dans apartments.csv")
        return False

    options = apts["slug"].tolist()
    labels = {r["slug"]: r["name"] for _, r in apts.iterrows()}

    cur_slug = st.session_state.get("apt_slug", options[0])
    if cur_slug not in options:
        cur_slug = options[0]
    default_idx = options.index(cur_slug)

    slug = st.sidebar.selectbox(
        "Choisir un appartement",
        options=options,
        index=default_idx,
        format_func=lambda s: labels.get(s, s),
        key="apt_slug_selectbox",
    )
    name = labels.get(slug, slug)

    changed = slug != st.session_state.get("apt_slug", "") or name != st.session_state.get("apt_name", "")
    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"] = f"plateformes_{slug}.csv"

    global CSV_RESERVATIONS, CSV_PLATEFORMES
    CSV_RESERVATIONS = st.session_state["CSV_RESERVATIONS"]
    CSV_PLATEFORMES = st.session_state["CSV_PLATEFORMES"]

    st.sidebar.success(f"Connecté : {name}")
    return changed


def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Garantit que toutes les colonnes nécessaires existent."""
    cols = [
        "res_id",
        "ical_uid",
        "nom_client",
        "telephone",
        "email",
        "plateforme",
        "pays",
        "date_arrivee",
        "date_depart",
        "nuitees",
        "prix_net",
        "commission",
        "frais_bancaires",
        "taxes_sejour",
        "frais_menage",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]


@st.cache_data
def _load_data_for_active_apartment() -> tuple[pd.DataFrame, dict]:
    """Charge les données de réservation et la palette pour l'appartement actif."""
    apt = _current_apartment()
    if not apt:
        return pd.DataFrame(), DEFAULT_PALETTE

    df = pd.DataFrame()
    if os.path.exists(CSV_RESERVATIONS):
        try:
            raw = _load_file_bytes(CSV_RESERVATIONS)
            df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        except Exception:
            df = pd.DataFrame()
    df = ensure_schema(df)

    palette = DEFAULT_PALETTE.copy()
    if os.path.exists(CSV_PLATEFORMES):
        try:
            raw = _load_file_bytes(CSV_PLATEFORMES)
            plat = _detect_delimiter_and_read(raw)
            for _, r in plat.iterrows():
                k = str(r.get("plateforme", "")).strip()
                v = str(r.get("couleur", "")).strip()
                if k and v:
                    palette[k] = v
        except Exception:
            pass

    return df, palette

# ============================== PART 3/5 — Accueil, Réservations, Ajout, Modification, Plateformes, Calendrier ==============================

def print_buttons(location="main"):
    """Boutons d'impression (affichés partout où c'est pertinent)."""
    st.markdown(
        """
        <script>
        function printPage(){window.print();}
        </script>
        <button onclick="printPage()">🖨️ Imprimer</button>
        """,
        unsafe_allow_html=True,
    )


def vue_accueil(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    today = pd.to_datetime(date.today())
    arriv = df[df["date_arrivee"] == today.strftime("%Y-%m-%d")]
    dep = df[df["date_depart"] == today.strftime("%Y-%m-%d")]
    demain = (today + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    arriv_dem = df[df["date_arrivee"] == demain]

    st.subheader("Arrivées aujourd'hui")
    st.dataframe(arriv, use_container_width=True)

    st.subheader("Départs aujourd'hui")
    st.dataframe(dep, use_container_width=True)

    st.subheader("Arrivées demain")
    st.dataframe(arriv_dem, use_container_width=True)


def vue_reservations(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    filtre_paye = st.radio("Filtrer par statut de paiement", ["Tous", "Payé", "Non payé"], horizontal=True)
    if filtre_paye == "Payé":
        df = df[df["commission"].astype(str) != ""]
    elif filtre_paye == "Non payé":
        df = df[df["commission"].astype(str) == ""]

    st.dataframe(df, use_container_width=True)


def vue_ajouter(df: pd.DataFrame, palette: dict):
    st.header("➕ Ajouter une réservation")
    print_buttons()
    st.info("Formulaire d’ajout (non implémenté dans ce prototype).")


def vue_modifier(df: pd.DataFrame, palette: dict):
    st.header("✏️ Modifier / Supprimer une réservation")
    print_buttons()
    st.info("Formulaire de modification/suppression (non implémenté dans ce prototype).")


def vue_plateformes(df: pd.DataFrame, palette: dict):
    st.header("🎨 Plateformes")
    print_buttons()
    st.caption("Palette des plateformes, éditable et sauvegardée par appartement.")

    plat = pd.DataFrame(
        [{"plateforme": k, "couleur": v} for k, v in palette.items()],
        columns=["plateforme", "couleur"],
    )
    edited = st.data_editor(plat, num_rows="dynamic", use_container_width=True)
    if st.button("💾 Sauvegarder la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, index=False, sep=";", encoding="utf-8")
            st.success("Palette sauvegardée ✅")
        except Exception as e:
            st.error(f"Erreur sauvegarde : {e}")


def vue_calendrier(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    col1, col2 = st.columns(2)
    annee = col1.selectbox("Année", sorted(df["date_arrivee"].dropna().astype(str).str[:4].unique()), index=0)
    mois = col2.selectbox("Mois", list(range(1, 13)), index=date.today().month - 1)

    try:
        dfv = df.copy()
        dfv["date_arrivee"] = pd.to_datetime(dfv["date_arrivee"], errors="coerce")
        dfv["date_depart"] = pd.to_datetime(dfv["date_depart"], errors="coerce")
    except Exception:
        st.error("Impossible de parser les dates.")
        return

    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True,
    )

    def day_resas(d):
        mask = (dfv["date_arrivee"] <= d) & (dfv["date_depart"] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)
    html_parts = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(int(annee), int(mois)):
        for d in week:
            outside = (d.month != int(mois))
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'>"
            cell += f"<div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                if not rs.empty:
                    for _, r in rs.iterrows():
                        color = palette.get(r.get("plateforme"), "#888")
                        name = str(r.get("nom_client") or "")[:22]
                        title_txt = escape(str(r.get("nom_client", "")), quote=True)
                        cell += (
                            "<div class='resa-pill' "
                            f"style='background:{color}' "
                            f"title='{title_txt}'>"
                            f"{name}</div>"
                        )
            cell += "</div>"
            html_parts.append(cell)
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(int(annee), int(mois), 1)
    fin_mois = date(int(annee), int(mois), monthrange(int(annee), int(mois))[1])
    rows = dfv[(dfv["date_arrivee"] <= fin_mois) & (dfv["date_depart"] > debut_mois)].copy()
    st.dataframe(rows, use_container_width=True)

# ============================== PART 4/5 — Rapport, SMS, Export ICS ==============================

def vue_rapport(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune donnée.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"] = pd.to_datetime(dfa["date_depart"], errors="coerce")
    dfa["annee"] = dfa["date_arrivee_dt"].dt.year
    dfa["mois"] = dfa["date_arrivee_dt"].dt.month

    # Analyse simple par année
    agg = dfa.groupby("annee").agg(
        reservations=("res_id", "count"),
        nuitees=("nuitees", "sum"),
        prix_net=("prix_net", "sum"),
    ).reset_index()

    st.subheader("Synthèse par année")
    st.dataframe(agg, use_container_width=True)

    # Analyse par pays
    if "pays" in dfa.columns:
        st.subheader("🌍 Analyse par pays")
        pays = dfa.groupby("pays").agg(
            reservations=("res_id", "count"),
            nuitees=("nuitees", "sum"),
            prix_net=("prix_net", "sum"),
        ).reset_index()
        st.dataframe(pays.sort_values("prix_net", ascending=False), use_container_width=True)


def _copy_button(label: str, payload: str, key: str):
    st.text_area("Aperçu", payload, height=200, key=f"ta_{key}")
    st.caption("Sélectionnez puis copiez (Ctrl/Cmd+C).")


def vue_sms(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS & WhatsApp — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre["date_arrivee"] = pd.to_datetime(pre["date_arrivee"], errors="coerce")
    pre["date_depart"] = pd.to_datetime(pre["date_depart"], errors="coerce")
    pre = pre[pre["date_arrivee"].dt.date == target_arrivee]

    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        for _, r in pre.iterrows():
            msg = (
                f"APPARTEMENT {apt_name}\n"
                f"Plateforme : {r.get('plateforme', 'N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  "
                f"Nuitées : {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. "
                "Afin d'organiser au mieux votre réception, merci de remplir la fiche suivante :\n"
                "https://urlr.me/kZuH94\n\n"
                "Un parking est à votre disposition sur place.\n\n"
                "Le check-in se fait à partir de 14:00 h et le check-out avant 11:00 h.\n\n"
                "Vous trouverez des consignes à bagages dans chaque quartier, à Nice.\n\n"
                "Nous vous souhaitons un excellent voyage et nous nous réjouissons de vous rencontrer très bientôt.\n\n"
                "Annick & Charley\n\n"
                "******\n\n"
                "Welcome to our establishment!\n\n"
                "We are delighted to welcome you soon to Nice. "
                "Please fill out the form below:\n"
                "https://urlr.me/kZuH94\n\n"
                "Parking is available on site.\n\n"
                "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m.\n\n"
                "We wish you a pleasant journey and look forward to meeting you very soon.\n\n"
                "Annick & Charley"
            )
            _copy_button("📋 Copier le message", msg, key=f"sms_{r['res_id']}")


def vue_export_ics(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📆 Export ICS (Google Calendar) — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"] = pd.to_datetime(dfa["date_depart"], errors="coerce")

    year = st.selectbox("Année", sorted(dfa["date_arrivee_dt"].dt.year.dropna().unique()), index=0)
    data = dfa[dfa["date_arrivee_dt"].dt.year == int(year)]

    if data.empty:
        st.warning("Rien à exporter.")
        return

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Villa Tobias//Reservations//FR"]
    for _, r in data.iterrows():
        dt_a = pd.to_datetime(r["date_arrivee"], errors="coerce")
        dt_d = pd.to_datetime(r["date_depart"], errors="coerce")
        if pd.isna(dt_a) or pd.isna(dt_d):
            continue

        summary = f"{apt_name} — {r.get('nom_client', '')}"
        desc = f"Client: {r.get('nom_client', '')}\\nTéléphone: {r.get('telephone', '')}\\nNuitées: {r.get('nuitees', '')}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{r.get('res_id', '')}",
            f"DTSTART;VALUE=DATE:{dt_a.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{dt_d.strftime('%Y%m%d')}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"

    st.download_button(
        "📥 Télécharger .ics",
        data=ics.encode("utf-8"),
        file_name=f"reservations_{year}.ics",
        mime="text/calendar",
    )

# ============================== PART 5/5 — Google Sheet, Clients, ID, Paramètres, Main ==============================

def vue_google_sheet(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Fiche d'arrivée / Google Sheet — {apt_name}")
    print_buttons()
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")
    st.markdown(f'<iframe src="{GOOGLE_FORM_VIEW}" width="100%" height="900" frameborder="0"></iframe>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Feuille Google intégrée")
    st.markdown(f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        show_email = st.checkbox("Afficher les colonnes d'email (si présentes)", value=False)
        if not show_email:
            mask_cols = [c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()]
            rep_display = rep.drop(columns=mask_cols, errors="ignore")
        else:
            rep_display = rep
        st.dataframe(rep_display, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


def vue_clients(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Liste des clients — {apt_name}")
    print_buttons()
    if df.empty:
        st.info("Aucun client.")
        return

    clients = df[['nom_client', 'telephone', 'email', 'plateforme', 'res_id', 'pays']].copy()
    for c in ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]:
        clients[c] = clients[c].astype(str).str.strip().replace({"nan": ""})

    need = clients["pays"].eq("") | clients["pays"].isna()
    if need.any():
        clients.loc[need, "pays"] = clients.loc[need, "telephone"].apply(_phone_country)

    cols_order = ["nom_client", "pays", "telephone", "email", "plateforme", "res_id"]
    clients = clients[cols_order]
    clients = clients.loc[clients["nom_client"] != ""].drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)


def vue_id(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants des réservations — {apt_name}")
    print_buttons()
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return
    tbl = df[["res_id", "nom_client", "telephone", "email", "plateforme", "pays"]].copy()
    for c in ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]:
        tbl[c] = tbl[c].astype(str).str.strip().replace({"nan": ""})
    need = tbl["pays"].eq("") | tbl["pays"].isna()
    if need.any():
        tbl.loc[need, "pays"] = tbl.loc[need, "telephone"].apply(_phone_country)
    tbl = tbl.dropna(subset=["res_id"])
    tbl = tbl[tbl["res_id"] != ""].drop_duplicates()
    st.dataframe(tbl, use_container_width=True)


def vue_settings(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"⚙️ Paramètres — {apt_name}")
    print_buttons()

    st.subheader("💾 Sauvegarde (exports)")
    export_csv(df, CSV_RESERVATIONS, "Exporter réservations CSV")
    export_xlsx(df, "reservations_export.xlsx", "Exporter réservations XLSX")

    st.subheader("♻️ Restauration (remplacer les données)")
    uploaded = st.file_uploader("Restaurer (CSV ou XLSX)", type=["csv", "xlsx"], key="restore_file")
    if uploaded is not None:
        try:
            content = uploaded.read()
            with open(CSV_RESERVATIONS, "wb") as f:
                f.write(content)
            st.success("Fichier restauré avec succès.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Erreur restauration : {e}")

    st.subheader("🧹 Vider le cache")
    if st.button("Vider le cache"):
        st.cache_data.clear()
        st.success("Cache vidé.")

    st.subheader("⛑️ Import manuel (remplacement immédiat)")
    manual = st.file_uploader("Choisir un fichier (CSV ou XLSX)", type=["csv", "xlsx"], key="manual_import")
    if manual is not None:
        try:
            content = manual.read()
            with open(CSV_RESERVATIONS, "wb") as f:
                f.write(content)
            st.success("Import manuel effectué.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Erreur import manuel : {e}")


# ---- CSS global (impression A4 paysage + petits raffinements UI) ----
def _apply_custom_css():
    st.markdown(
        """
        <style>
        /* --------- Impression A4 paysage --------- */
        @media print {
          @page { size: A4 landscape; margin: 10mm; }
          /* Enlève la sidebar et la barre de menu Streamlit à l'impression */
          [data-testid="stSidebar"], header, footer { display: none !important; }
          /* Agrandit un peu le texte imprimé */
          body, [data-testid="stAppViewContainer"] { font-size: 12pt !important; }
          /* Évite les coupures bizarres */
          .block-container { padding: 0 !important; }
          .stDataFrame, .stTable { break-inside: avoid; }
        }

        /* --------- Petits styles UI --------- */
        .chip small { opacity: .75; }
        .stButton>button { border-radius: 10px; }
        .stDownloadButton>button { border-radius: 10px; }

        /* Masque les colonnes techniques si besoin (on peut utiliser column_config côté DataFrame) */
        .hide-tech { display: none !important; }

        /* Bandeau d’en-tête imprimable (si tu l’utilises) */
        .print-header {
          display: none;
          font-weight: 700; margin: 0 0 8px 0; padding: 6px 0;
          border-bottom: 1px solid rgba(0,0,0,.15);
        }
        @media print {
          .print-header { display: block; }
        }
        </style>
        """,
        unsafe_allow_html=True
    )


st.markdown(f"<div class='print-header'>{(_current_apartment() or {}).get('name','—')} — Export</div>", unsafe_allow_html=True)

# ============================== MAIN ==============================

def main():
    st.set_page_config(page_title="✨ Villa Tobias — Réservations", layout="wide")
    _apply_custom_css()

    changed = _select_apartment_sidebar()
    df, palette_loaded = _load_data_for_active_apartment()

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier_supprimer,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Google Sheet": vue_google_sheet,
        "👥 Clients": vue_clients,
        "🆔 ID": vue_id,
        "⚙️ Paramètres": vue_settings,
    }

    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    page_func = pages.get(choice)
    if page_func:
        page_func(df, palette_loaded)


if __name__ == "__main__":
    main()