# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib, json
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

# ============================== 0) CONFIG & THEME ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# purge prudente au chargement (ne plante pas si indispo)
for _clear in (getattr(st, "cache_data", None), getattr(st, "cache_resource", None)):
    try:
        if _clear: _clear.clear()
    except Exception:
        pass

# ATTENTION : J'ai modifié ce chemin de fichier pour qu'il corresponde au fichier que vous avez fourni.
# Le programme était configuré pour chercher "reservations.csv" au lieu de "reservations_normalise.csv".
CSV_RESERVATIONS = "reservations_normalise.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

def apply_style(light: bool):
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    chip_bg = "#333" if not light else "#e8e8e8"
    chip_fg = "#eee" if not light else "#222"
    st.markdown(
        f"""
        <style>
        html, body, [data-testid="stAppViewContainer"] {{
          background: {bg}; color: {fg};
        }}
        [data-testid="stSidebar"] {{
          background: {side}; border-right: 1px solid {border};
        }}
        .glass {{
          background: {"rgba(255,255,255,0.65)" if light else "rgba(255,255,255,0.06)"};
          border: 1px solid {border}; border-radius: 12px; padding: 12px; margin: 8px 0;
        }}
        .chip {{
          display:inline-block; background:{chip_bg}; color:{chip_fg};
          padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:.85rem
        }}
        .kpi-line strong {{ font-size:1.05rem; }}
        .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; margin-top:8px; }}
        .cal-cell {{
          border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px;
          position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"};
        }}
        .cal-cell.outside {{ opacity:.45; }}
        .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
        .resa-pill {{
          padding:4px 6px; border-radius:6px; font-size:.85rem; margin-top:22px;
          color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }}
        .cal-header {{
          display:grid; grid-template-columns: repeat(7, 1fr);
          font-weight:700; opacity:.8; margin-top:10px;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# ============================== 1) HELPERS DE TYPE ==============================
def _series(obj, dtype=None):
    """Garantit une Series (évite les ndarray sans fillna)."""
    if isinstance(obj, pd.Series):
        s = obj.copy()
    elif isinstance(obj, (list, tuple, np.ndarray)):
        s = pd.Series(obj)
    else:
        s = pd.Series([]) if obj is None else pd.Series(obj)
    if dtype:
        try: s = s.astype(dtype)
        except Exception: pass
    return s

def _to_bool_series(s) -> pd.Series:
    ser = _series(s, "string").fillna("")
    return ser.str.strip().str.lower().isin(["true","1","oui","vrai","yes","y","t"])

def _to_num(s) -> pd.Series:
    ser = _series(s, "string").fillna("")
    ser = (ser.str.replace("€","", regex=False)
              .str.replace(" ", "", regex=False)
              .str.replace("\u00A0","", regex=False)   # espace insécable
              .str.replace(",", ".", regex=False)
              .str.replace(r"[^\d\.\-]", "", regex=True)
              .str.strip())
    return pd.to_numeric(ser, errors="coerce")

def _to_date(s) -> pd.Series:
    """Accepte JJ/MM/AAAA, AAAA-MM-JJ, JJ-MM-AAAA, retourne date."""
    ser = _series(s, "string").fillna("").str.strip()
    if ser.empty:
        return pd.Series([], dtype="object")
    # 1) tentative flexible dayfirst
    d = pd.to_datetime(ser, errors="coerce", dayfirst=True)
    # 2) complète avec ISO si NaT
    mask_nat = d.isna()
    if mask_nat.any():
        d2 = pd.to_datetime(ser[mask_nat], errors="coerce", format="%Y-%m-%d")
        d = d.where(~mask_nat, d2)
    return d.dt.date

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

# ============================== 2) SCHEMA & IO ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid","AAAA","MM"
]

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
    # essai multi-separateurs
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3:
                return df
        except Exception:
            continue
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # alias éventuels
    df.rename(columns={
        'Payé':'paye', 'Client':'nom_client', 'Plateforme':'plateforme',
        'Arrivée':'date_arrivee', 'Départ':'date_depart', 'Nuits':'nuitees',
        'Brut (€)':'prix_brut'
    }, inplace=True)

    # ajouter colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    # numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # recalcul nuitées si possible
    ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[ok, "date_depart"])
        df.loc[ok, "nuitees"] = (dd - da).dt.days.clip(lower=0)
    except Exception:
        pass

    # dérivées
    df["prix_net"] = (_to_num(df["prix_brut"]) - _to_num(df["commissions"]) - _to_num(df["frais_cb"])).fillna(0.0)
    df["charges"]  = (_to_num(df["prix_brut"]) - _to_num(df["prix_net"])).fillna(0.0)
    df["base"]     = (_to_num(df["prix_net"]) - _to_num(df["menage"]) - _to_num(df["taxes_sejour"])).fillna(0.0)
    
    # Correction pour l'erreur de division
    mask = _to_num(df["prix_brut"]) > 0
    df["%"] = 0.0
    df.loc[mask, "%"] = (_to_num(df.loc[mask, "charges"]) / _to_num(df.loc[mask, "prix_brut"]) * 100)

    # AAAA / MM
    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(da_all.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(da_all.dt.month, errors="coerce")

    # IDs
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]
    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # strings propres
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = _series(df[c], "string").fillna("").str.replace("nan","").str.replace("None","").str.strip()

    return df[BASE_COLS]

@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

@st.cache_data
def charger_donnees():
    raw = _load_file_bytes(CSV_RESERVATIONS)
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if set(["plateforme","couleur"]).issubset(set(pal_df.columns)):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception:
            pass
    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        df2 = ensure_schema(df)
        out = df2.copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde CSV : {e}")
        return False

# ============================== 3) VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"] = _to_date(dfv["date_depart"])

    arr = dfv[dfv["date_arrivee"] == today][["nom_client","telephone","plateforme"]]
    dep = dfv[dfv["date_depart"] == today][["nom_client","telephone","plateforme"]]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame(columns=["nom_client","telephone","plateforme"]), use_container_width=True)

    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame(columns=["nom_client","telephone","plateforme"]), use_container_width=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df is None or df.empty:
        st.info("Aucune réservation."); return

    years_ser = pd.to_numeric(_series(df.get("AAAA")), errors="coerce")
    months_ser = pd.to_numeric(_series(df.get("MM")), errors="coerce")

    years_unique = sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True)
    if not years_unique:
        st.info("Aucune année de réservation disponible."); return
    
    st.sidebar.markdown("### Filtres")
    selected_year = st.sidebar.selectbox("Année", years_unique, index=0)

    df_filtered = df[df["AAAA"] == selected_year]
    months_in_year = sorted(df_filtered["MM"].dropna().astype(int).unique().tolist())
    
    month_options = {1:"Jan",2:"Fév",3:"Mar",4:"Avr",5:"Mai",6:"Juin",
                     7:"Juil",8:"Août",9:"Sep",10:"Oct",11:"Nov",12:"Déc"}
    
    month_list_with_labels = [f"{m} ({month_options.get(m)})" for m in months_in_year]
    selected_month_label = st.sidebar.radio("Mois", month_list_with_labels)
    selected_month = int(selected_month_label.split(" ")[0])

    st.subheader(f"Réservations pour {month_options.get(selected_month)} {selected_year}")
    
    df_month = df_filtered[df_filtered["MM"] == selected_month].sort_values("date_arrivee")
    
    if df_month.empty:
        st.info("Aucune réservation pour ce mois."); return
        
    for _, row in df_month.iterrows():
        start = row["date_arrivee"]
        end   = row["date_depart"]
        
        # === Début de la correction pour l'erreur de date ===
        # Formate les dates seulement si elles sont valides
        start_date_str = pd.to_datetime(start).strftime('%d/%m/%Y') if pd.notna(start) else "Date manquante"
        end_date_str = pd.to_datetime(end).strftime('%d/%m/%Y') if pd.notna(end) else "Date manquante"
        
        info = f"""
        **{row['nom_client']}**<br/>
        **{row['plateforme']}** ({row['nuitees']} nuits)<br/>
        Prix brut: **{_to_num(row['prix_brut']):.2f}€**<br/>
        Arrivée: {start_date_str}<br/>
        Départ: {end_date_str}
        """
        # === Fin de la correction ===

        st.markdown(info, unsafe_allow_html=True)
        st.markdown("---")


def vue_ajouter(df, palette):
    st.header("➕ Ajouter une réservation")
    st.info("Ce module est en cours de développement. Veuillez utiliser le formulaire pour ajouter une nouvelle réservation.")
    st.markdown(f"[Ajouter via Google Forms]({GOOGLE_FORM_URL})", unsafe_allow_html=True)

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    st.info("Cette fonctionnalité n'est pas encore implémentée. Pour le moment, les modifications doivent être faites directement dans le fichier CSV ou via le formulaire.")
    st.markdown(f"[Modifier via Google Sheet]({GOOGLE_SHEET_EMBED_URL})", unsafe_allow_html=True)

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes")
    st.markdown("Affichage des plateformes avec la couleur associée. Si un fichier `plateformes.csv` n'est pas fourni, une palette par défaut est utilisée.")

    if not palette:
        st.warning("Aucune palette de couleurs trouvée."); return
        
    st.write("Couleurs utilisées :")
    for plat, color in palette.items():
        st.markdown(f"<span class='chip' style='background:{color};'>{plat}</span>", unsafe_allow_html=True)

    df_plat = df.groupby("plateforme").agg(
        total_reservations=("nom_client", "count"),
        total_prix_brut=("prix_brut", "sum"),
        total_nuitees=("nuitees", "sum")
    ).reset_index()

    st.subheader("Synthèse par plateforme")
    st.dataframe(df_plat, use_container_width=True)

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des réservations")
    today = date.today()
    years = sorted(df["AAAA"].dropna().unique().tolist(), reverse=True)
    
    c1, c2 = st.columns(2)
    with c1:
        y = st.selectbox("Année", years, index=0)
    with c2:
        m_options = list(range(1, 13))
        m = st.selectbox("Mois", m_options, format_func=lambda x: f"{x} ({['Jan','Fév','Mar','Avr','Mai','Juin','Juil','Août','Sep','Oct','Nov','Déc'][x-1]})")

    selected_month_dates = [
        date(y, m, d) for d in range(1, monthrange(y, m)[1] + 1)
    ]
    
    df_month = df[(df["AAAA"]==y) & (df["MM"]==m)].copy()
    
    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='cal-grid'>", unsafe_allow_html=True)
    
    # Remplissage pour le décalage du 1er jour du mois
    first_day = date(y, m, 1).weekday()
    for _ in range(first_day):
        st.markdown("<div></div>", unsafe_allow_html=True)

    for d in selected_month_dates:
        is_today = "cal-today" if d == today else ""
        resa = df_month[(_to_date(df_month["date_arrivee"]) == d) | (_to_date(df_month["date_depart"]) == d)]
        
        resa_html = ""
        if not resa.empty:
            for _, r in resa.iterrows():
                plat = r["plateforme"]
                color = palette.get(plat, "#999999")
                resa_html += f"<div class='resa-pill' style='background:{color};'>{r['nom_client']} ({r['nuitees']}N)</div>"
        
        st.markdown(f"<div class='cal-cell {is_today}'><div class='cal-date'>{d.day}</div>{resa_html}</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def vue_rapport(df, palette):
    st.header("📊 Rapport")
    st.info("Ce module est en cours de développement.")
    
    df_report = df.groupby(["AAAA","MM"]).agg(
        total_prix_brut=("prix_brut","sum"),
        total_prix_net=("prix_net","sum"),
        total_nuitees=("nuitees","sum")
    ).reset_index()

    st.subheader("Revenus bruts mensuels")
    chart = alt.Chart(df_report).mark_bar().encode(
        x=alt.X("MM", axis=None),
        y=alt.Y("total_prix_brut", title="Revenu brut (€)"),
        tooltip=[alt.Tooltip("AAAA", title="Année"),
                 alt.Tooltip("MM", title="Mois"),
                 alt.Tooltip("total_prix_brut", title="Revenu brut", format=".2f")]
    ).properties(title="Revenus bruts par mois")
    st.altair_chart(chart, use_container_width=True)

def vue_sms(df, palette):
    st.header("✉️ SMS & Emails")
    st.info("Cette fonctionnalité est en cours de développement.")
    df_sms = df[["nom_client","telephone","email","sms_envoye","post_depart_envoye"]].copy()
    st.subheader("Contacts")
    st.dataframe(df_sms, use_container_width=True)

def vue_export_ics(df, palette):
    st.header("📆 Export ICS")
    st.info("Cette fonctionnalité est en cours de développement.")
    
def vue_google_sheet(df, palette):
    st.header("📝 Google Sheet")
    st.info("Accédez directement à la feuille de calcul Google Sheet pour une gestion plus avancée.")
    st.markdown(f"[Ouvrir la Google Sheet]({GOOGLE_SHEET_EMBED_URL})", unsafe_allow_html=True)
    
def vue_clients(df, palette):
    st.header("👥 Fichier Clients")
    st.info("Ce module est en cours de développement.")
    st.dataframe(df, use_container_width=True)


# ============================== 4) BARRE LATERALE & INPUTS ==============================
def sidebar_actions(df):
    st.sidebar.markdown("### Actions")
    st.sidebar.markdown(f"[Ajouter une réservation]({GOOGLE_FORM_URL})")
    
    if st.sidebar.button("💾 Sauvegarder les données"):
        ok = sauvegarder_donnees(df)
        if ok:
            st.sidebar.success("Données sauvegardées avec succès !")
    
    uploaded_file = st.sidebar.file_uploader("📥 Importer un CSV", type="csv")
    if uploaded_file is not None:
        try:
            raw_bytes = uploaded_file.getvalue()
            imported_df = _detect_delimiter_and_read(raw_bytes)
            if not imported_df.empty:
                st.session_state["imported_df"] = imported_df
                st.sidebar.success("Fichier importé ! Affichez l'aperçu ou fusionnez-le.")
                st.sidebar.subheader("Aperçu de l'import")
                st.sidebar.dataframe(imported_df.head())
                if st.sidebar.button("🔗 Fusionner avec les données existantes"):
                    df_new = pd.concat([df, imported_df], ignore_index=True)
                    st.session_state["df"] = df_new
                    st.sidebar.success("Fusion réussie ! Redémarrage...")
                    st.rerun()
            else:
                st.sidebar.error("Erreur de lecture du fichier CSV.")
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache & recharger"):
        for _clear in (getattr(st, "cache_data", None), getattr(st, "cache_resource", None)):
            try:
                if _clear: _clear.clear()
            except Exception:
                pass
        st.success("Cache vidé. Rechargement…"); st.rerun()

# ============================== 5) MAIN ==============================
def main():
    # Mode sombre par défaut (lisible PC), toggle pour mode clair
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE
    
    if df.empty:
        st.warning("Aucune donnée de réservation n'a pu être chargée. Veuillez vérifier que le fichier reservations_normalise.csv existe et est correctement formaté.")

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
        "👥 Clients": vue_clients
    }

    st.sidebar.markdown("### Navigation")
    selection = st.sidebar.radio("Aller à", list(pages.keys()))

    page = pages[selection]
    page(df, palette)
    sidebar_actions(df)

if __name__ == "__main__":
    main()
