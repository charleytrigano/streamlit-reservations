# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# --- HARD CLEAR (sécurisé) ---
try:
    try: st.cache_data.clear()
    except Exception: pass
    try: st.cache_resource.clear()
    except Exception: pass
except Exception:
    pass

CSV_RESERVATIONS = "reservations_normalise.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

FORM_SHORT_URL = "https://urlr.me/kZuH94"

# ============================== HELPERS ==============================
def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3: return df
        except Exception: continue
    return pd.read_csv(StringIO(txt), dtype=str)

def _to_num(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="float64")
    sc = (s.astype(str).str.replace("€","",regex=False)
                     .str.replace(" ","",regex=False)
                     .str.replace(",",".",regex=False).str.strip())
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="object")
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty: return pd.DataFrame()
    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()
    for c in ["nom_client","plateforme","telephone","email"]:
        if c not in df.columns: df[c] = ""
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()
    for b in ["sms_envoye","post_depart_envoye"]:
        if b not in df.columns: df[b] = False
        df[b] = df[b].astype(str).str.lower().isin(["true","1","yes","oui"])
    for dcol in ["date_arrivee","date_depart"]:
        if dcol in df.columns: df[dcol] = _to_date(df[dcol])
    if "nuitees" not in df.columns: df["nuitees"] = 0
    if "prix_brut" not in df.columns: df["prix_brut"] = 0
    if "prix_net" not in df.columns: df["prix_net"] = 0
    if "base" not in df.columns: df["base"] = 0
    if "charges" not in df.columns: df["charges"] = 0
    if "AAAA" not in df.columns:
        df["AAAA"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year
    if "MM" not in df.columns:
        df["MM"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.month
    return df

@st.cache_data
def charger_donnees():
    try:
        with open(CSV_RESERVATIONS,"rb") as f: raw = f.read()
    except: raw=None
    df = ensure_schema(_detect_delimiter_and_read(raw)) if raw else pd.DataFrame()
    try:
        with open(CSV_PLATEFORMES,"rb") as f: rawp=f.read()
    except: rawp=None
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        pal_df = _detect_delimiter_and_read(rawp)
        if set(["plateforme","couleur"]).issubset(set(pal_df.columns)):
            palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Sauvegarde impossible : {e}")
        return False

def _phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")
    arr = df[df["date_arrivee"]==today][["nom_client","telephone","plateforme"]] if not df.empty else pd.DataFrame()
    dep = df[df["date_depart"]==today][["nom_client","telephone","plateforme"]] if not df.empty else pd.DataFrame()
    c1,c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr) if not arr.empty else st.info("Aucune arrivée.")
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep) if not dep.empty else st.info("Aucun départ.")

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty: st.info("Aucune réservation."); return
    years_ser = pd.to_numeric(df.get("AAAA", pd.Series(dtype="float64")), errors="coerce")
    months_ser= pd.to_numeric(df.get("MM", pd.Series(dtype="float64")), errors="coerce")
    years = ["Toutes"] + sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True)
    months= ["Tous"] + sorted(months_ser.dropna().astype(int).unique().tolist())
    plats = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    y = st.selectbox("Année", years)
    m = st.selectbox("Mois", months)
    p = st.selectbox("Plateforme", plats)
    data=df.copy()
    if y!="Toutes": data=data[data["AAAA"]==int(y)]
    if m!="Tous": data=data[data["MM"]==int(m)]
    if p!="Toutes": data=data[data["plateforme"]==p]
    st.dataframe(data,use_container_width=True)

def vue_clients(df, palette):
    st.header("👥 Clients")
    if df.empty: st.info("Aucun client."); return
    clients=df[["nom_client","telephone","email","plateforme"]].drop_duplicates().sort_values("nom_client")
    st.dataframe(clients,use_container_width=True)


# ============================== SMS ==============================
def _series_bool(s: pd.Series) -> pd.Series:
    """Convertit en booléen robuste sans renvoyer de ndarray nu."""
    if s is None:
        return pd.Series([], dtype=bool)
    return s.astype(str).str.strip().str.lower().isin(
        ["true", "1", "yes", "oui", "y", "t"]
    )

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    if df.empty:
        st.info("Aucune réservation."); return

    # Assurer les colonnes existantes et types sûrs
    dfx = df.copy()
    for col in ["sms_envoye", "post_depart_envoye"]:
        if col not in dfx.columns:
            dfx[col] = False
    dfx["sms_envoye"] = _series_bool(dfx["sms_envoye"])
    dfx["post_depart_envoye"] = _series_bool(dfx["post_depart_envoye"])
    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"]  = _to_date(dfx["date_depart"])

    # -------- Pré-arrivée (J+1) --------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfx.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (pre["sms_envoye"] == False)]

    if pre.empty:
        st.info("Aucun client à contacter pour la date sélectionnée.")
    else:
        pre = pre.reset_index(drop=False).rename(columns={"index":"_rowid"})
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None)
        if pick:
            i = int(pick.split(":")[0])
            r = pre.loc[i]
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce").fillna(0) if isinstance(r.get("nuitees"), pd.Series) else (r.get("nuitees") or 0))
            nuitees = int(nuitees)

            msg = (
                "VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  "
                f"Nuitées : {nuitees}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                f"Téléphone : {r.get('telephone')}\n\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous acceuillir bientot a Nice. Aussi afin d'organiser au mieux votre reception "
                "merci de nous indiquer votre heure d'arrivee.\n\n"
                "Sachez qu'une place de parking vous est allouee en cas de besoin.\n\n"
                "Le check-in se fait a partir de 14:00 h et le check-out avant 11:00 h.\n\n"
                "Vous trouverez des consignes a bagages dans chaque quartier a Nice.\n\n"
                "Welcome to our home!\n\n"
                "We are delighted to welcome you soon to Nice. In order to organize your reception as best as possible, "
                "please let us know your arrival time.\n\n"
                "Please note that a parking space is available if needed.\n\n"
                "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m.\n\n"
                "You will find luggage storage facilities in every neighborhood in Nice.\n\n"
                "We wish you a wonderful trip and look forward to meeting you very soon.\n\n"
                "Annick & Charley\n\n"
                "Merci de remplir la fiche d'arrivee / Please fill out the arrival form :\n"
                f"{FORM_SHORT_URL}"
            )
            e164 = _phone_e164(r["telephone"])
            wa_num = re.sub(r"\D","", e164)
            enc = quote(msg)

            st.text_area("Prévisualisation message", value=msg, height=220)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa_num}?text={enc}")

            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(df):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # -------- Post-départ (J0) --------
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfx.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (post["post_depart_envoye"] == False)]

    if post.empty:
        st.info("Aucun message à envoyer pour la date sélectionnée.")
    else:
        post = post.reset_index(drop=False).rename(columns={"index":"_rowid"})
        opts2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=opts2, index=None)
        if pick2:
            j = int(pick2.split(":")[0]); r2 = post.loc[j]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci d'avoir choisi notre appartement pour votre sejour.\n\n"
                "Nous esperons que vous avez passe un moment aussi agreable que celui que nous avons eu a vous accueillir.\n\n"
                "Si l'envie vous prend de revenir explorer encore un peu notre ville, sachez que notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n"
                f"\nHello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n\n"
                "We hope you had as enjoyable a time as we did hosting you.\n\n"
                "If you feel like coming back to explore our city a little more, know that our door will always be open to you.\n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )
            e164b = _phone_e164(r2["telephone"])
            wab = re.sub(r"\D","", e164b)
            enc2 = quote(msg2)

            st.text_area("Prévisualisation message", value=msg2, height=200, key="ta2")
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")

            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                if sauvegarder_donnees(df):
                    st.success("Marqué ✅"); st.rerun()


# ============================== EXPORT ICS ==============================
def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    if df.empty: st.info("Aucune réservation."); return

    # Filtres
    years = sorted(pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    data["date_arrivee"] = _to_date(data["date_arrivee"])
    data["date_depart"]  = _to_date(data["date_depart"])
    data = data[pd.to_datetime(data["date_arrivee"], errors="coerce").dt.year == year]
    if plat != "Tous": data = data[data["plateforme"] == plat]
    if data.empty:
        st.warning("Rien à exporter avec ces filtres."); return

    # UIDs stables
    if "ical_uid" not in data.columns:
        data["ical_uid"] = None
    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss.any():
        # UID basé sur res_id + nom + tel
        def _build_uid(row):
            base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
            return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"
        data.loc[miss, "ical_uid"] = data[miss].apply(_build_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _fmt(d):
        if not isinstance(d, (date, datetime)): return ""
        if isinstance(d, datetime): d = d.date()
        return f"{d.year:04d}{d.month:02d}{d.day:02d}"

    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        if not (isinstance(da, (date, datetime)) and isinstance(dd, (date, datetime))):
            continue
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"): summary += f" ({r['plateforme']})"
        nuit = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
        brut = float(pd.to_numeric(r.get("prix_brut"), errors="coerce") or 0.0)
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {nuit}",
            f"Prix brut: {brut:.2f} €",
            f"res_id: {r.get('res_id','')}",
        ])
        lines += [
            "BEGIN:VEVENT",
            f"UID:{r['ical_uid']}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt(da)}",
            f"DTEND;VALUE=DATE:{_fmt(dd)}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"

    st.download_button("📥 Télécharger .ics",
                       data=ics.encode("utf-8"),
                       file_name=f"reservations_{year}.ics",
                       mime="text/calendar")


# ============================== ADMIN (sidebar) ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    # Téléchargement de sauvegarde
    safe = ensure_schema(df)
    # convertir les dates avant export
    out = safe.copy()
    for col in ["date_arrivee","date_depart"]:
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
    st.sidebar.download_button(
        "⬇️ Télécharger CSV",
        data=out.to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )

    # Restauration
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            content = up.read()
            tmp = _detect_delimiter_and_read(content)
            tmp = ensure_schema(tmp)
            # Sauvegarder normalisé
            save = tmp.copy()
            for col in ["date_arrivee","date_depart"]:
                save[col] = pd.to_datetime(save[col], errors="coerce").dt.strftime("%d/%m/%Y")
            save.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.cache_data.clear(); st.cache_resource.clear()
            st.success("Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    # Purge cache
    if st.sidebar.button("🧹 Vider le cache & recharger"):
        try: st.cache_data.clear()
        except: pass
        try: st.cache_resource.clear()
        except: pass
        st.success("Cache vidé. Rechargement…")
        st.rerun()


# ============================== MAIN ==============================
def main():
    st.title("✨ Villa Tobias — Gestion des Réservations")

    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "👥 Clients": vue_clients,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)


if __name__ == "__main__":
    main()