# ============================== PART 1/5 — IMPORTS, CONFIG, STYLES, HELPERS ==============================

import os
import re
import pandas as pd
import streamlit as st
from datetime import date, datetime, timedelta

# Constantes
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES = "plateformes.csv"
APARTMENTS_CSV = "apartments.csv"
INDICATIFS_CSV = "indicatifs_pays.csv"

FORM_SHORT_URL = "https://urlr.me/kZuH94"

DEFAULT_PALETTE = {
    "Booking": "#003580",
    "Airbnb": "#FF5A5F",
    "Abritel": "#0067DB",
    "Expedia": "#F2A900",
    "Direct": "#228B22",
}

# ==================== INDICATIFS (pays, drapeaux) ====================

def _indicatifs_mtime() -> float:
    try:
        return os.path.getmtime(INDICATIFS_CSV)
    except Exception:
        return 0.0

@st.cache_data(show_spinner=False)
def load_indicatifs_cached(_mtime_key: float) -> pd.DataFrame:
    """Charge le CSV des indicatifs (avec cache)."""
    if not os.path.exists(INDICATIFS_CSV):
        # créer un CSV minimal si absent
        pd.DataFrame(
            [
                {"code_pays": "FR", "pays": "France", "indicatif": "+33", "emoji": "🇫🇷"},
                {"code_pays": "ES", "pays": "Espagne", "indicatif": "+34", "emoji": "🇪🇸"},
                {"code_pays": "IT", "pays": "Italie", "indicatif": "+39", "emoji": "🇮🇹"},
            ]
        ).to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")
    return pd.read_csv(INDICATIFS_CSV, dtype=str, encoding="utf-8").fillna("")

def _phone_country(phone: str) -> str:
    """Retourne le pays trouvé selon l’indicatif."""
    s = str(phone or "").strip()
    s = re.sub(r"\D", "", s)
    if not s:
        return ""
    if not s.startswith("+"):
        s = "+" + s
    df = load_indicatifs_cached(_indicatifs_mtime())
    for _, r in df.iterrows():
        indic = str(r.get("indicatif") or "").strip()
        if indic and s.startswith(indic.replace(" ", "").replace("-", "")):
            return f"{r.get('emoji','')} {r.get('pays','')}"
    return ""

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D", "", str(phone or ""))
    if not s:
        return ""
    if not s.startswith("+" ):
        s = "+" + s
    return s

# ==================== STYLE ====================

def apply_style(light: bool = False):
    """Applique un thème clair ou sombre via CSS."""
    bg = "#FFFFFF" if light else "#0E1117"
    fg = "#000000" if light else "#FAFAFA"
    st.markdown(
        f"""
        <style>
        body {{
            background-color: {bg};
            color: {fg};
        }}
        .stButton>button {{
            border-radius: 12px;
            padding: 0.6em 1.2em;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

# ============================== PART 2/5 — DATA HELPERS, I/O, APARTMENTS, UI UTILS ==============================

import io
import uuid
import numpy as np

BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","pays",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid"
]

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    """Essaie ; , tab | puis par défaut pandas."""
    if not raw:
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(io.StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 2:
                return df
        except Exception:
            pass
    try:
        return pd.read_csv(io.StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _to_bool_series(s: pd.Series) -> pd.Series:
    vals_true = {"true","1","oui","vrai","yes","y","t"}
    return (
        s.astype(str)
         .str.strip()
         .str.lower()
         .isin(vals_true)
    )

def _to_num(s: pd.Series) -> pd.Series:
    sc = (
        s.astype(str)
         .str.replace("€","", regex=False)
         .str.replace(" ","", regex=False)
         .str.replace(",",".", regex=False)
         .str.strip()
    )
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Normalise les colonnes/typos et calcule prix_net, base, %, nuitees…"""
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    rename_map = {
        "Payé":"paye","Client":"nom_client","Plateforme":"plateforme",
        "Arrivée":"date_arrivee","Départ":"date_depart","Nuits":"nuitees",
        "Brut (€)":"prix_brut"
    }
    df.rename(columns=rename_map, inplace=True)

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False)

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    mask_ok = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)

    prix_brut = _to_num(df["prix_brut"])
    commissions = _to_num(df["commissions"])
    frais_cb = _to_num(df["frais_cb"])
    menage = _to_num(df["menage"])
    taxes  = _to_num(df["taxes_sejour"])

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0.0)
    df["charges"]  = (prix_brut - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - menage - taxes).fillna(0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        df["%"] = np.where(prix_brut > 0, (df["charges"]/prix_brut*100), 0.0).astype(float)

    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    for c in ["nom_client","plateforme","telephone","email","pays","ical_uid"]:
        df[c] = df[c].astype(str).replace({"nan":"", "None":""}).str.strip()

    # Remplit pays depuis indicatif si vide
    need = (df["pays"] == "") | df["pays"].isna()
    if need.any():
        df.loc[need, "pays"] = df.loc[need, "telephone"].apply(_phone_country)

    return df[BASE_COLS]

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    """Sauve le CSV courant (celui de l’appartement actif)."""
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        target = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
        out.to_csv(target, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
    """Charge les données et la palette (créé des fichiers vides si absents)."""
    # Crée les fichiers si manquants
    for fichier, header in [
        (csv_reservations, "nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut\n"),
        (csv_plateformes,  "plateforme,couleur\nBooking,#003580\nAirbnb,#FF5A5F\nAbritel,#0067DB\nDirect,#228B22\n"),
    ]:
        if not os.path.exists(fichier):
            with open(fichier, "w", encoding="utf-8", newline="") as f:
                f.write(header)

    raw = _load_file_bytes(csv_reservations)
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    rawp = _load_file_bytes(csv_plateformes)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if {"plateforme","couleur"}.issubset(pal_df.columns):
                p = pal_df.dropna().copy()
                p["plateforme"] = p["plateforme"].astype(str).str.strip()
                p["couleur"] = p["couleur"].astype(str).str.strip()
                palette.update(dict(zip(p["plateforme"], p["couleur"])))
        except Exception as e:
            st.warning(f"Erreur de palette : {e}")

    return df, palette

# ==================== APARTMENTS (sélecteur) ====================

def _read_apartments_csv() -> pd.DataFrame:
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug", "name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug", "name"])

        df.columns = [str(c).strip().lower() for c in df.columns]
        if "slug" not in df.columns: df["slug"] = ""
        if "name" not in df.columns: df["name"] = ""

        df["slug"] = (
            df["slug"].astype(str).str.replace("\ufeff","",regex=False)
              .str.strip().str.replace(" ","-",regex=False)
              .str.replace("_","-",regex=False).str.lower()
        )
        df["name"] = df["name"].astype(str).str.replace("\ufeff","",regex=False).str.strip()

        df = df[(df["slug"] != "") & (df["name"] != "")]
        df = df.drop_duplicates(subset=["slug"], keep="first")
        return df[["slug","name"]]
    except Exception:
        return pd.DataFrame(columns=["slug", "name"])

def _current_apartment() -> dict | None:
    slug = st.session_state.get("apt_slug", "")
    name = st.session_state.get("apt_name", "")
    if slug and name:
        return {"slug": slug, "name": name}
    return None

def _select_apartment_sidebar() -> bool:
    """Affiche le sélecteur dans la sidebar + met à jour chemins CSV."""
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

    changed = (slug != st.session_state.get("apt_slug", "") or name != st.session_state.get("apt_name", ""))

    # Mémorise et synchronise
    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"]  = f"plateformes_{slug}.csv"

    global CSV_RESERVATIONS, CSV_PLATEFORMES
    CSV_RESERVATIONS = st.session_state["CSV_RESERVATIONS"]
    CSV_PLATEFORMES  = st.session_state["CSV_PLATEFORMES"]

    st.sidebar.success(f"Connecté : {name}")
    try:
        print_buttons(location="sidebar")
    except Exception:
        pass

    return changed

def _load_data_for_active_apartment():
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES",  CSV_PLATEFORMES)
    try:
        return charger_donnees(csv_res, csv_pal)
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()

# ==================== UI UTILS ====================

def print_buttons(location: str = "main"):
    """Petit bouton Imprimer (ouvre la boîte de dialogue du navigateur)."""
    target = st.sidebar if location == "sidebar" else st
    target.button("🖨️ Imprimer", key=f"print_btn_{location}")
    st.markdown(
        """
        <script>
        (function(){
          const labels = Array.from(parent.document.querySelectorAll('button span, button p'));
          const btn = labels.find(n => n.textContent && n.textContent.trim() === "🖨️ Imprimer");
          if (btn) { btn.parentElement.onclick = () => window.print(); }
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

# ============================== PART 3/5 — VUES ACCUEIL, RÉSERVATIONS, AJOUT/MODIF, PLATEFORMES, CALENDRIER ==============================

def vue_accueil(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation disponible.")
        return

    today = date.today()
    demain = today + timedelta(days=1)
    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    arrivals_today = dfv[dfv["date_arrivee"] == today]
    departures_today = dfv[dfv["date_depart"] == today]
    arrivals_tomorrow = dfv[dfv["date_arrivee"] == demain]

    st.subheader("📅 Arrivées aujourd’hui")
    if arrivals_today.empty:
        st.write("Aucune arrivée.")
    else:
        st.dataframe(arrivals_today[["nom_client","plateforme","telephone","date_arrivee","date_depart"]], use_container_width=True)

    st.subheader("📦 Départs aujourd’hui")
    if departures_today.empty:
        st.write("Aucun départ.")
    else:
        st.dataframe(departures_today[["nom_client","plateforme","telephone","date_arrivee","date_depart"]], use_container_width=True)

    st.subheader("🛬 Arrivées demain")
    if arrivals_tomorrow.empty:
        st.write("Aucune arrivée demain.")
    else:
        st.dataframe(arrivals_tomorrow[["nom_client","plateforme","telephone","date_arrivee","date_depart"]], use_container_width=True)


def vue_reservations(df: pd.DataFrame, palette: dict):
    st.header("📋 Réservations")
    print_buttons()

    if df.empty:
        st.info("Aucune donnée de réservation.")
        return

    st.dataframe(df, use_container_width=True)
    st.download_button("⬇️ Exporter CSV", df.to_csv(sep=";", index=False).encode("utf-8"), "reservations_export.csv", "text/csv")


def vue_ajouter(df: pd.DataFrame, palette: dict):
    st.header("➕ Ajouter une réservation")
    print_buttons()

    with st.form("add_reservation"):
        nom = st.text_input("Nom du client")
        plateforme = st.text_input("Plateforme")
        tel = st.text_input("Téléphone")
        email = st.text_input("Email")
        arrivee = st.date_input("Date arrivée", value=date.today())
        depart = st.date_input("Date départ", value=date.today() + timedelta(days=1))
        prix = st.number_input("Prix brut (€)", min_value=0.0, step=1.0)
        submitted = st.form_submit_button("Ajouter")

        if submitted:
            nuitees = (depart - arrivee).days
            new_row = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": tel,
                "email": email,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "nuitees": nuitees,
                "prix_brut": prix,
            }
            df2 = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            if sauvegarder_donnees(df2):
                st.success("Réservation ajoutée ✅")
                st.rerun()


def vue_modifier(df: pd.DataFrame, palette: dict):
    st.header("✏️ Modifier / Supprimer")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation à modifier.")
        return

    choix = st.selectbox("Choisir une réservation", df["nom_client"].astype(str) + " — " + df["plateforme"].astype(str))
    sel = df[df["nom_client"].astype(str) + " — " + df["plateforme"].astype(str) == choix]
    if sel.empty:
        return

    r = sel.iloc[0]
    idx = sel.index[0]

    with st.form("edit_reservation"):
        nom = st.text_input("Nom du client", value=r["nom_client"])
        plateforme = st.text_input("Plateforme", value=r["plateforme"])
        tel = st.text_input("Téléphone", value=r["telephone"])
        email = st.text_input("Email", value=r["email"])
        arrivee = st.date_input("Date arrivée", value=_to_date(pd.Series([r["date_arrivee"]])).iloc[0])
        depart = st.date_input("Date départ", value=_to_date(pd.Series([r["date_depart"]])).iloc[0])
        prix = st.number_input("Prix brut (€)", value=float(r.get("prix_brut",0.0)))
        submitted = st.form_submit_button("Mettre à jour")

        if submitted:
            df.loc[idx, ["nom_client","plateforme","telephone","email","date_arrivee","date_depart","prix_brut"]] = [
                nom, plateforme, tel, email, arrivee, depart, prix
            ]
            if sauvegarder_donnees(df):
                st.success("Réservation mise à jour ✅")
                st.rerun()

    if st.button("🗑️ Supprimer cette réservation"):
        df2 = df.drop(idx).reset_index(drop=True)
        if sauvegarder_donnees(df2):
            st.success("Réservation supprimée ✅")
            st.rerun()


def vue_plateformes(df: pd.DataFrame, palette: dict):
    st.header("🎨 Plateformes")
    print_buttons()

    pal_df = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
    st.dataframe(pal_df, use_container_width=True)

    st.markdown("#### Ajouter / Modifier une couleur")
    with st.form("edit_palette"):
        plat = st.text_input("Plateforme")
        coul = st.color_picker("Couleur", "#000000")
        ok = st.form_submit_button("Enregistrer")
        if ok and plat:
            palette[plat] = coul
            pal_df = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
            target = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
            pal_df.to_csv(target, sep=";", index=False, encoding="utf-8")
            st.success("Palette mise à jour ✅")
            st.rerun()


def vue_calendrier(df: pd.DataFrame, palette: dict):
    st.header("📅 Calendrier")
    print_buttons()

    if df.empty:
        st.info("Aucune donnée de réservation.")
        return

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])
    dfv = dfv.dropna(subset=["date_arrivee","date_depart"])

    st.write("Vue simplifiée du calendrier (arrivées/départs)")
    st.dataframe(dfv[["nom_client","plateforme","date_arrivee","date_depart","nuitees"]], use_container_width=True)

# ============================== PART 4/5 — RAPPORT, SMS PLACEHOLDER, GOOGLE SHEET, CLIENTS, ID, INDICATIFS ==============================

def vue_rapport(df: pd.DataFrame, palette: dict):
    st.header("📊 Rapport")
    print_buttons()

    if df.empty:
        st.info("Aucune donnée de réservation.")
        return

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])
    dfv["nuitees"] = pd.to_numeric(dfv.get("nuitees"), errors="coerce").fillna(0).astype(int)
    dfv["prix_brut"] = pd.to_numeric(dfv.get("prix_brut"), errors="coerce").fillna(0.0)

    total_nuites = dfv["nuitees"].sum()
    total_revenu = dfv["prix_brut"].sum()

    c1, c2 = st.columns(2)
    c1.metric("Nuitées totales", total_nuites)
    c2.metric("Revenus bruts (€)", f"{total_revenu:,.2f}")

    st.subheader("Répartition par plateforme")
    agg = dfv.groupby("plateforme").agg({"nuitees":"sum","prix_brut":"sum"}).reset_index()
    st.dataframe(agg, use_container_width=True)

    fig, ax = plt.subplots()
    ax.pie(agg["prix_brut"], labels=agg["plateforme"], autopct="%1.1f%%")
    st.pyplot(fig)


# --- SMS Placeholder (réel dans Part 5) ---
def vue_sms(df: pd.DataFrame, palette: dict):
    st.header("✉️ SMS")
    st.info("Les messages SMS détaillés sont gérés dans la PART 5.")


def vue_google_sheet(df: pd.DataFrame, palette: dict):
    st.header("📝 Google Sheet")
    st.info("Intégration Google Sheet désactivée (placeholder).")


def vue_clients(df: pd.DataFrame, palette: dict):
    st.header("👥 Clients")
    print_buttons()

    if df.empty:
        st.info("Aucun client.")
        return

    clients = df.groupby(["nom_client","telephone","email"], dropna=False).size().reset_index(name="reservations")
    st.dataframe(clients, use_container_width=True)


def vue_id(df: pd.DataFrame, palette: dict):
    st.header("🆔 ID Réservations")
    print_buttons()
    if df.empty:
        st.info("Aucune réservation.")
    else:
        st.dataframe(df[["nom_client","plateforme","date_arrivee","date_depart"]], use_container_width=True)


def vue_indicatifs(df: pd.DataFrame, palette: dict):
    st.header("🌍 Indicateurs pays")
    print_buttons()

    indicatifs = load_indicatifs()
    st.dataframe(indicatifs, use_container_width=True)

    with st.form("add_country_code"):
        flag = st.text_input("Drapeau (emoji)", value="🇫🇷")
        pays = st.text_input("Pays", value="France")
        indicatif = st.text_input("Indicatif", value="+33")
        ok = st.form_submit_button("Ajouter")
        if ok and pays and indicatif:
            new_row = {"flag": flag, "country": pays, "code": indicatif}
            indicatifs = pd.concat([indicatifs, pd.DataFrame([new_row])], ignore_index=True)
            indicatifs.to_csv(INDICATIFS_CSV, sep=";", index=False, encoding="utf-8")
            st.success("Ajouté ✅")
            st.rerun()

    if st.button("♻️ Recharger depuis le disque"):
        st.cache_data.clear()
        st.rerun()

# ============================== PART 5/5 — SMS COMPLET, PARAMÈTRES, MAIN ==============================

def vue_sms(df: pd.DataFrame, palette: dict):
    """Page SMS — messages préformatés avant arrivée et après départ."""
    from urllib.parse import quote

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    # -------- Pré-arrivée --------
    st.subheader("🛬 Pré-arrivée (J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1))
    pre = dfv[(dfv["date_arrivee"] == target_arrivee)]

    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        for _, r in pre.iterrows():
            arr_txt = r["date_arrivee"].strftime("%d/%m/%Y") if pd.notna(r["date_arrivee"]) else ""
            dep_txt = r["date_depart"].strftime("%d/%m/%Y") if pd.notna(r["date_depart"]) else ""
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)

            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}\n\n"
                f"Bonjour {r.get('nom_client','')}\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. "
                "Merci de remplir la fiche suivante :\n"
                f"{FORM_SHORT_URL}\n\n"
                "Parking disponible sur place.\n"
                "Check-in dès 14h, check-out avant 11h.\n\n"
                "Annick & Charley"
            )

            st.text_area(f"Pré-arrivée — {r.get('nom_client','')}", msg, height=300)

    # -------- Post-départ --------
    st.subheader("📤 Post-départ (aujourd’hui)")
    target_depart = st.date_input("Départs du", date.today())
    post = dfv[(dfv["date_depart"] == target_depart)]

    if post.empty:
        st.info("Aucun départ aujourd’hui.")
    else:
        for _, r in post.iterrows():
            name = str(r.get("nom_client") or "")
            msg2 = (
                f"Bonjour {name},\n\n"
                "Merci d'avoir choisi notre appartement. "
                "Nous espérons que vous avez passé un agréable séjour.\n"
                "Notre porte sera toujours ouverte si vous souhaitez revenir.\n\n"
                "Annick & Charley"
            )
            st.text_area(f"Post-départ — {name}", msg2, height=220)


# ============================== PARAMÈTRES ==============================

def vue_settings(df: pd.DataFrame, palette: dict):
    st.header("⚙️ Paramètres")
    print_buttons()

    # Export CSV
    try:
        out = ensure_schema(df).copy()
        out.to_csv("export_reservations.csv", sep=";", index=False, encoding="utf-8")
        with open("export_reservations.csv", "rb") as f:
            csv_bytes = f.read()
    except Exception:
        csv_bytes = b""

    st.download_button(
        "⬇️ Exporter réservations (CSV)",
        data=csv_bytes,
        file_name="reservations_export.csv",
        mime="text/csv",
    )

    # Restauration
    up = st.file_uploader("Restaurer un fichier", type=["csv", "xlsx"])
    if up:
        try:
            if up.name.endswith(".xlsx"):
                tmp = pd.read_excel(up, dtype=str)
            else:
                tmp = pd.read_csv(up, sep=None, engine="python", dtype=str)
            st.dataframe(tmp.head(), use_container_width=True)
            if st.button("✅ Confirmer restauration"):
                tmp.to_csv(st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS),
                           sep=";", index=False, encoding="utf-8")
                st.success("Fichier restauré ✅")
                st.rerun()
        except Exception as e:
            st.error(f"Erreur restauration : {e}")

    # Outil secours apartments.csv
    st.markdown("### 🧰 Réinitialiser apartments.csv")
    default_csv = "slug,name\nvilla-tobias,Villa Tobias\nle-turenne,Le Turenne\n"
    txt = st.text_area("Contenu apartments.csv", value=default_csv, height=120)
    if st.button("📝 Réécrire apartments.csv"):
        with open(APARTMENTS_CSV, "w", encoding="utf-8") as f:
            f.write(txt.strip() + "\n")
        st.success("apartments.csv réécrit ✅")
        st.rerun()


# ============================== MAIN ==============================

def main():
    # Reset cache via URL ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1","true","yes"):
        st.cache_data.clear()

    # Sélecteur d’appartement
    _select_apartment_sidebar()

    # Thème clair/sombre
    mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=mode_clair)

    # En-tête
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    # Charger données
    df, palette = _load_data_for_active_apartment()

    # Pages
    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Google Sheet": vue_google_sheet,
        "👥 Clients": vue_clients,
        "🆔 ID": vue_id,
        "🌍 Indicateurs pays": vue_indicatifs,
        "⚙️ Paramètres": vue_settings,
    }

    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    page_func = pages[choice]
    page_func(df, palette)


if __name__ == "__main__":
    main()