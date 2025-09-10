# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import re, uuid, hashlib
from io import StringIO
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote

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

CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# ============================== HELPERS ==============================
def detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 2: return df
        except Exception: continue
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def to_date(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="object")
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def to_num(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="float64")
    sc = (s.astype(str)
          .str.replace("€", "", regex=False)
          .str.replace(" ", "", regex=False)
          .str.replace(",", ".", regex=False)
          .str.strip())
    return pd.to_numeric(sc, errors="coerce")

def stable_uid(res_id: str, nom: str, tel: str) -> str:
    base = f"{res_id or ''}{nom or ''}{tel or ''}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def fmt_ymd(d):
    if isinstance(d, datetime): d = d.date()
    if not isinstance(d, date): return ""
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"

def esc_ics(s):
    if s is None: return ""
    return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

# ============================== DATA ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
    "base","charges","%","res_id","ical_uid","AAAA","MM"
]

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)
    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    rename_map = {"Arrivée":"date_arrivee","Départ":"date_depart","Client":"nom_client"}
    df.rename(columns=rename_map, inplace=True)

    for c in BASE_COLS:
        if c not in df.columns: df[c] = None

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = to_date(df["date_arrivee"])
    df["date_depart"]  = to_date(df["date_depart"])

    mask_ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[mask_ok,"date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok,"date_depart"])
        df.loc[mask_ok,"nuitees"] = (dd - da).dt.days.clip(lower=0)
    except: pass

    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(
        lambda r: stable_uid(r.get("res_id"), r.get("nom_client"), r.get("telephone")), axis=1)

    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(da_all.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(da_all.dt.month, errors="coerce")

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    try:
        with open(CSV_RESERVATIONS,"rb") as f: raw = f.read()
        base_df = detect_delimiter_and_read(raw)
    except: base_df = pd.DataFrame()
    df = ensure_schema(base_df)

    palette = DEFAULT_PALETTE.copy()
    try:
        with open(CSV_PLATEFORMES,"rb") as f: rawp = f.read()
        pal_df = detect_delimiter_and_read(rawp)
        if set(["plateforme","couleur"]).issubset(set(pal_df.columns)):
            palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
    except: pass

    return df, palette


# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfn = ensure_schema(df)
    dfn["date_arrivee"] = to_date(dfn["date_arrivee"])
    dfn["date_depart"]  = to_date(dfn["date_depart"])

    arr = dfn[dfn["date_arrivee"] == today][["nom_client","telephone","plateforme"]]
    dep = dfn[dfn["date_depart"]  == today][["nom_client","telephone","plateforme"]]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        if arr.empty: st.info("Aucune arrivée aujourd'hui.")
        else:         st.dataframe(arr, use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        if dep.empty: st.info("Aucun départ aujourd'hui.")
        else:         st.dataframe(dep, use_container_width=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation.")
        return

    # Filtres robustes
    years_ser  = pd.to_numeric(dfn["AAAA"], errors="coerce")
    months_ser = pd.to_numeric(dfn["MM"],   errors="coerce")

    years_list  = sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True) if not years_ser.dropna().empty else []
    months_list = sorted(months_ser.dropna().astype(int).unique().tolist()) if not months_ser.dropna().empty else list(range(1,13))
    plats_list  = sorted(dfn["plateforme"].dropna().astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)
    year  = c1.selectbox("Année",   ["Toutes"] + years_list, index=0)
    month = c2.selectbox("Mois",    ["Tous"]   + months_list, index=0)
    plat  = c3.selectbox("Plateforme", ["Toutes"] + plats_list, index=0)

    data = dfn.copy()
    if year  != "Toutes": data = data[pd.to_numeric(data["AAAA"], errors="coerce").fillna(-1).astype(int) == int(year)]
    if month != "Tous":   data = data[pd.to_numeric(data["MM"],   errors="coerce").fillna(-1).astype(int) == int(month)]
    if plat  != "Toutes": data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]

    # KPI compacts
    brut    = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net     = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    charges = float(pd.to_numeric(data["charges"],   errors="coerce").fillna(0).sum())
    base    = float(pd.to_numeric(data["base"],      errors="coerce").fillna(0).sum())
    nuits   = int(pd.to_numeric(data["nuitees"],     errors="coerce").fillna(0).sum())
    adr     = (net/nuits) if nuits>0 else 0.0

    html = f"""
    <div style="border:1px solid rgba(127,127,127,.25);border-radius:12px;padding:8px;margin:8px 0;display:flex;flex-wrap:wrap;gap:8px">
      <span style="background:#222;color:#fff;padding:6px 10px;border-radius:10px"><small>Total brut</small><br><strong style="font-size:1.05rem">{brut:,.2f} €</strong></span>
      <span style="background:#222;color:#fff;padding:6px 10px;border-radius:10px"><small>Total net</small><br><strong style="font-size:1.05rem">{net:,.2f} €</strong></span>
      <span style="background:#222;color:#fff;padding:6px 10px;border-radius:10px"><small>Charges</small><br><strong style="font-size:1.05rem">{charges:,.2f} €</strong></span>
      <span style="background:#222;color:#fff;padding:6px 10px;border-radius:10px"><small>Base</small><br><strong style="font-size:1.05rem">{base:,.2f} €</strong></span>
      <span style="background:#222;color:#fff;padding:6px 10px;border-radius:10px"><small>Nuitées</small><br><strong style="font-size:1.05rem">{nuits}</strong></span>
      <span style="background:#222;color:#fff;padding:6px 10px;border-radius:10px"><small>ADR (net)</small><br><strong style="font-size:1.05rem">{adr:,.2f} €</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(html, unsafe_allow_html=True)

    # Tri par arrivée décroissante si dispo
    order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order]
    st.dataframe(data, use_container_width=True)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une réservation")
    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom   = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel   = st.text_input("Téléphone")
            arr   = st.date_input("Arrivée", date.today())
            dep   = st.date_input("Départ", date.today()+timedelta(days=1))
        with c2:
            plat  = st.selectbox("Plateforme", list(palette.keys()))
            brut  = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb    = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage      = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes       = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye        = st.checkbox("Payé", value=False)
        if st.form_submit_button("✅ Ajouter"):
            if not nom or dep <= arr:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nuitees = (dep - arr).days
                new = pd.DataFrame([{
                    "nom_client": nom, "email": email, "telephone": tel, "plateforme": plat,
                    "date_arrivee": arr, "date_depart": dep, "nuitees": nuitees,
                    "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                    "menage": menage, "taxes_sejour": taxes, "paye": paye
                }])
                dfn = ensure_schema(pd.concat([df, new], ignore_index=True))
                # sauvegarde
                out = dfn.copy()
                for col in ["date_arrivee","date_depart"]:
                    out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
                out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
                st.cache_data.clear()
                st.success(f"Réservation pour {nom} ajoutée.")
                st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation.")
        return
    df_sorted = dfn.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client','')} ({r.get('date_arrivee','')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel: return
    idx = int(sel.split(":")[0])
    original_idx = df_sorted.loc[idx, "index"]
    row = dfn.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get("nom_client","") or "")
            email = st.text_input("Email", value=row.get("email","") or "")
            tel = st.text_input("Téléphone", value=row.get("telephone","") or "")
            arrivee = st.date_input("Arrivée", value=row.get("date_arrivee"))
            depart  = st.date_input("Départ", value=row.get("date_depart"))
        with c2:
            palette_keys = list(palette.keys())
            pidx = palette_keys.index(row.get("plateforme")) if row.get("plateforme") in palette_keys else 0
            plat = st.selectbox("Plateforme", options=palette_keys, index=pidx)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=float(row.get("prix_brut") or 0))
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=float(row.get("commissions") or 0))
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=float(row.get("frais_cb") or 0))
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=float(row.get("menage") or 0))
            taxes  = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=float(row.get("taxes_sejour") or 0))

        b1, b2 = st.columns([0.7, 0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            for k, v in {
                "nom_client": nom, "email": email, "telephone": tel, "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye, "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes
            }.items():
                dfn.loc[original_idx, k] = v
            # sauvegarde
            out = ensure_schema(dfn).copy()
            for col in ["date_arrivee","date_depart"]:
                out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
            out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.cache_data.clear()
            st.success("Modifié ✅")
            st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            dfn2 = dfn.drop(index=original_idx)
            # sauvegarde
            out = ensure_schema(dfn2).copy()
            for col in ["date_arrivee","date_depart"]:
                out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
            out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.cache_data.clear()
            st.warning("Supprimé.")
            st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs")
    base = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    c1, c2 = st.columns([0.6,0.4])
    if c1.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
            st.success("Palette enregistrée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("↩️ Restaurer palette par défaut"):
        pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(
            CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
        st.success("Palette par défaut restaurée."); st.rerun()

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    dfn = ensure_schema(df).dropna(subset=['date_arrivee','date_depart']).copy()
    if dfn.empty:
        st.info("Aucune réservation à afficher."); return

    today = date.today()
    years = sorted(pd.to_datetime(dfn["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    st.markdown("<div style='display:grid;grid-template-columns: repeat(7, 1fr);font-weight:700;opacity:.8;margin-top:10px'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        mask = (dfn['date_arrivee'] <= d) & (dfn['date_depart'] > d)
        return dfn[mask]

    cal = Calendar(firstweekday=0)  # lundi
    html = ["<div style='display:grid;grid-template-columns: repeat(7, 1fr);gap:8px;margin-top:8px'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            classes = "opacity:.45;" if outside else ""
            cell = f"<div style='border:1px solid rgba(127,127,127,.25);border-radius:10px;min-height:110px;padding:8px;position:relative;overflow:hidden;{classes}'>"
            cell += f"<div style='position:absolute;top:6px;right:8px;font-weight:700;font-size:.9rem;opacity:.7'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                if not rs.empty:
                    for _, r in rs.iterrows():
                        color = palette.get(r.get('plateforme'), '#888')
                        name  = str(r.get('nom_client') or '')[:22]
                        cell += f"<div style='padding:4px 6px;border-radius:6px;font-size:.85rem;margin-top:22px;color:#fff;background:{color};white-space:nowrap;overflow:hidden;text-overflow:ellipsis' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfn[(dfn['date_arrivee'] <= fin_mois) & (dfn['date_depart'] > debut_mois)].copy()
    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
        plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if plat != "Toutes": rows = rows[rows["plateforme"]==plat]
        brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
        net  = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
        nuits= int(pd.to_numeric(rows["nuitees"],    errors="coerce").fillna(0).sum())
        st.markdown(f"**Total brut : {brut:,.2f} € — Total net : {net:,.2f} € — Nuitées : {nuits}**".replace(",", " "))
        st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

def vue_rapport(df, palette):
    st.header("📊 Rapport")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune donnée."); return
    years = sorted(pd.to_numeric(dfn["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month = st.selectbox("Mois", months, index=0)
    plats = ["Tous"] + sorted(dfn["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)
    metric = st.selectbox("Métrique", ["prix_brut","prix_net","menage","nuitees"], index=0)

    data = dfn[pd.to_numeric(dfn["AAAA"], errors="coerce")==year].copy()
    if month!="Tous": data = data[pd.to_numeric(data["MM"], errors="coerce")==int(month)]
    if plat!="Tous":  data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Aucune donnée après filtres."); return

    data["mois"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.to_period("M").astype(str)
    agg = data.groupby(["mois","plateforme"], as_index=False).agg({metric:"sum"})
    total_val = float(pd.to_numeric(agg[metric], errors="coerce").fillna(0).sum())
    st.markdown(f"**Total {metric.replace('_',' ')} : {total_val:,.2f}**".replace(",", " "))
    st.dataframe(agg, use_container_width=True)

def _copy_preview(label: str, payload: str, key: str):
    st.text_area(label, payload, height=200, key=f"ta_{key}")
    st.caption("Sélectionnez et copiez (Ctrl/Cmd+C).")

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # Pré-arrivée (J+1)
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = ensure_schema(df).dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre["date_arrivee"] = to_date(pre["date_arrivee"])
    pre["date_depart"]  = to_date(pre["date_depart"])
    pre = pre[(pre["date_arrivee"]==target_arrivee) & (~pre["sms_envoye"])]

    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        pre["_rowid"] = pre.index
        pre = pre.sort_values("date_arrivee").reset_index(drop=True)
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None)
        if pick:
            i = int(pick.split(":")[0]); r = pre.loc[i]
            msg = (
                f"VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  "
                f"Nuitées : {int(r.get('nuitees') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                f"Téléphone : {r.get('telephone')}\n\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous acceuillir bientot a Nice. Merci de nous indiquer votre heure d'arrivee.\n\n"
                "Place de parking disponible. Check-in 14:00, check-out 11:00.\n\n"
                "Merci de remplir la fiche d'arrivee : https://urlr.me/kZuH94\n\n"
                "EN — Please tell us your arrival time. Parking on request. Check-in from 2pm, check-out before 11am.\n\n"
                "Annick & Charley"
            )
            e164 = _format_phone_e164(r["telephone"])
            enc  = quote(msg)
            wa   = re.sub(r"\D","", e164)

            _copy_preview("Prévisualisation", msg, key=f"pre_{i}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                out = ensure_schema(df).copy()
                for col in ["date_arrivee","date_depart"]:
                    out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
                out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
                st.cache_data.clear()
                st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # Post-départ (J0)
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = ensure_schema(df).dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post["date_depart"] = to_date(post["date_depart"])
    post = post[(post["date_depart"]==target_depart) & (~post["post_depart_envoye"])]

    if post.empty:
        st.info("Aucun message à envoyer.")
    else:
        post["_rowid"] = post.index
        post = post.sort_values("date_depart").reset_index(drop=True)
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
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n\n"
                "We hope you had as enjoyable a time as we did hosting you.\n\n"
                "If you feel like coming back to explore our city a little more, know that our door will always be open to you.\n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )
            e164b = _format_phone_e164(r2["telephone"])
            enc2  = quote(msg2)
            wab   = re.sub(r"\D","", e164b)

            _copy_preview("Prévisualisation post-départ", msg2, key=f"post_{j}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                out = ensure_schema(df).copy()
                for col in ["date_arrivee","date_depart"]:
                    out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
                out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
                st.cache_data.clear()
                st.success("Marqué ✅"); st.rerun()

def build_ics_from_df(dfin: pd.DataFrame) -> str:
    data = ensure_schema(dfin).copy()
    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        if not (isinstance(da, (date, datetime)) and isinstance(dd, (date, datetime))):
            continue
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"): summary += f" ({r['plateforme']})"
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}",
            f"Prix brut: {float(pd.to_numeric(r.get('prix_brut'), errors='coerce') or 0):.2f} €",
            f"res_id: {r.get('res_id','')}",
        ])
        uid = r.get("ical_uid") or stable_uid(r.get("res_id"), r.get("nom_client"), r.get("telephone"))
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{fmt_ymd(da)}",
            f"DTEND;VALUE=DATE:{fmt_ymd(dd)}",
            f"SUMMARY:{esc_ics(summary)}",
            f"DESCRIPTION:{esc_ics(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation."); return
    years = sorted(pd.to_numeric(dfn["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(dfn["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfn[pd.to_numeric(dfn["AAAA"], errors="coerce")==year].copy()
    if plat!="Tous": data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Rien à exporter."); return

    ics = build_ics_from_df(data)
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"),
                       file_name=f"reservations_{year}.ics", mime="text/calendar")

# ---------- Export ICS PUBLIC ----------
def _get_query_params():
    try:
        return st.query_params
    except Exception:
        try:
            return st.experimental_get_query_params()
        except Exception:
            return {}

def icspublic_endpoint(df):
    params = _get_query_params()
    feed = params.get("feed", [""])[0] if isinstance(params.get("feed"), list) else params.get("feed", "")
    if str(feed).lower() != "ics":
        return False

    # (Optionnel) token
    # token = params.get("token", [""])[0] if isinstance(params.get("token"), list) else params.get("token", "")

    annee = params.get("year", [""])[0] if isinstance(params.get("year"), list) else params.get("year", "")
    plat_params = params.get("plats", [])
    if isinstance(plat_params, str): plat_params = [plat_params]

    data = ensure_schema(df).dropna(subset=['date_arrivee','date_depart']).copy()
    if annee:
        try:
            an = int(annee)
            data = data[pd.to_numeric(data["AAAA"], errors="coerce")==an]
        except:
            pass
    if plat_params:
        plats_norm = [p for p in plat_params if p]
        if plats_norm:
            data = data[data["plateforme"].isin(plats_norm)]

    ics = build_ics_from_df(data)
    st.text(ics)
    st.stop()

def vue_export_ics_public(df, palette):
    st.header("🔗 Export ICS public (URL)")
    st.caption("Copiez l’URL générée dans Google Calendar → **Ajouter un agenda** → **À partir de l’URL**.")
    base_url = st.text_input("URL de base de l'app (exactement celle affichée par votre navigateur)", value="")

    dfn = ensure_schema(df)
    years = sorted(pd.to_numeric(dfn["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)

    all_plats = sorted(dfn["plateforme"].dropna().unique()) if 'plateforme' in dfn.columns else []
    plats_sel = st.multiselect("Plateformes (optionnel)", all_plats, default=[])

    def build_url(base, params):
        if not base: return ""
        base_clean = base.split("?")[0]
        from urllib.parse import urlencode
        return base_clean + "?" + urlencode(params, doseq=True)

    query = {"feed": "ics", "year": str(year)}
    for p in plats_sel:
        query.setdefault("plats", []).append(p)

    flux_url = build_url(base_url, query)
    if flux_url:
        st.code(flux_url, language="text")
        st.link_button("📋 Ouvrir l’URL de flux", flux_url)

    with st.expander("Aperçu ICS"):
        data = dfn[pd.to_numeric(dfn["AAAA"], errors="coerce")==year].copy()
        if plats_sel:
            data = data[data["plateforme"].isin(plats_sel)]
        st.text(build_ics_from_df(data))

def vue_clients(df, palette):
    st.header("👥 Clients")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucun client."); return
    clients = (dfn[['nom_client','telephone','email','plateforme','res_id']].copy())
    clients["nom_client"] = clients["nom_client"].astype(str).str.strip()
    clients["telephone"]  = clients["telephone"].astype(str).str.strip()
    clients["email"]      = clients["email"].astype(str).str.strip()
    clients = clients.loc[clients["nom_client"] != ""]
    clients = clients.drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    dfn = ensure_schema(df)

    st.sidebar.download_button(
        "Télécharger CSV",
        data=dfn.to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            content = up.read()
            tmp_df = detect_delimiter_and_read(content)
            tmp_df = ensure_schema(tmp_df)
            out = tmp_df.copy()
            for col in ["date_arrivee","date_depart"]:
                out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
            out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement…"); st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache & recharger"):
        try: st.cache_data.clear()
        except: pass
        try: st.cache_resource.clear()
        except: pass
        st.success("Cache vidé. Rechargement…")
        st.rerun()

# ============================== MAIN ==============================
def main():
    # Endpoint ICS public (si appelé avec ?feed=ics)
    params = _get_query_params()
    if str(params.get("feed", [""])[0]).lower() == "ics":
        icspublic_endpoint(charger_donnees()[0])
        return

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette = charger_donnees()

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
        "🔗 Export ICS public": vue_export_ics_public,
        "👥 Clients": vue_clients,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()