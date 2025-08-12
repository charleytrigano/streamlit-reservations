# app.py — Réservations Villa Tobias (barre métriques sombre + totaux corrigés)
import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta
from io import BytesIO
import os, re, json, base64, requests
import matplotlib.pyplot as plt
from urllib.parse import quote

FICHIER = "reservations.xlsx"
ICAL_SOURCES = "ical_sources.json"   # { "sources": [ {"name": "Booking", "url": "..."} ] }

# ==============================  CSS / UI HELPERS  =========================

def inject_css():
    st.markdown(
        """
        <style>
          /* Couleurs auto (clair/sombre) */
          :root{
            --chip-bg: rgba(0,0,0,0.03);
            --chip-border: rgba(0,0,0,0.12);
            --chip-text: inherit;
            --muted: rgba(0,0,0,0.55);
          }
          @media (prefers-color-scheme: dark){
            :root{
              --chip-bg: rgba(255,255,255,0.06);
              --chip-border: rgba(255,255,255,0.18);
              --chip-text: rgba(255,255,255,0.95);
              --muted: rgba(255,255,255,0.65);
            }
          }

          .stTable td, .stTable th { font-size: 0.92rem; }
          h2, h3 { letter-spacing: 0.2px; }
          section[data-testid="stSidebar"] button { padding: .3rem .55rem !important; }
          .inline-label { font-size:.9rem; color:var(--muted); padding:.35rem .4rem .35rem 0; white-space:nowrap; }
          .muted { color:var(--muted); font-size:.9rem }

          /* Bouton rouge */
          .btn-danger > div > button { background-color: #e02424 !important; color: white !important; border: 0 !important; }

          /* Boutons à droite du titre */
          .btn-right { display: flex; justify-content: flex-end; gap:.5rem; align-items:center; }

          /* Barre de métriques responsive */
          .metrics-row{
            display:flex; flex-wrap:wrap; gap:.5rem; align-items:stretch;
            margin: .25rem 0 .75rem 0;
          }
          .chip{
            background: var(--chip-bg);
            border: 1px solid var(--chip-border);
            border-radius: .6rem;
            padding: .5rem .65rem;
            min-width: 140px;
            color: var(--chip-text);
          }
          .chip .lbl { font-size:.85rem; opacity:.9; }
          .chip .val { font-weight:600; font-variant-numeric: tabular-nums; }
          .chip .sub { font-size:.82rem; opacity:.75; margin-top:.1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def header(titre: str, sous_titre: str = ""):
    st.markdown(
        f"""
        <div style="padding:8px 0 4px 0">
          <h2 style="margin:0">{titre}</h2>
          <div style="color:#666;margin-top:2px">{sous_titre}</div>
        </div>
        <hr style="margin:8px 0 16px 0; opacity:.25">
        """,
        unsafe_allow_html=True,
    )

def inline_input(label_text, widget_fn, key=None, col_ratio=(1,3), **widget_kwargs):
    c1, c2 = st.columns(col_ratio)
    with c1:
        st.markdown(f"<div class='inline-label'>{label_text}</div>", unsafe_allow_html=True)
    with c2:
        widget_kwargs.setdefault("label_visibility", "collapsed")
        # Harmonise types pour st.number_input (évite MixedNumericTypesError)
        if widget_fn is st.number_input:
            for k in ("min_value","max_value","step","value"):
                if k in widget_kwargs and isinstance(widget_kwargs[k], int):
                    widget_kwargs[k] = float(widget_kwargs[k])
        return widget_fn(label_text, key=key, **widget_kwargs)

def render_cache_button_sidebar():
    st.sidebar.markdown("## 🧭 Navigation")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.sidebar.success("Cache vidé. Redémarrage…")
        st.rerun()

def metrics_bar(df: pd.DataFrame, prefix: str = ""):
    """Barre de métriques compatible thème sombre + responsive mobile (totaux corrects)."""
    if df is None or df.empty:
        return
    tmp = df.copy()
    # Conserve uniquement les lignes "normales" (sans lignes Total)
    tmp = tmp[~_marque_totaux(tmp)] if not tmp.empty else tmp

    for c in ["prix_brut", "prix_net", "charges", "nuitees", "%"]:
        tmp[c] = pd.to_numeric(tmp.get(c, 0), errors="coerce").fillna(0)

    brut = float(tmp["prix_brut"].sum())
    net = float(tmp["prix_net"].sum())
    ch = float(tmp["charges"].sum())
    nts = float(tmp["nuitees"].sum())
    pct_mean = (float((tmp["%"] * tmp["prix_brut"]).sum() / tmp["prix_brut"].replace(0, np.nan).sum())
                if tmp["prix_brut"].sum() else 0.0)
    brut_nuit = (brut / nts) if nts else 0.0
    net_nuit  = (net / nts) if nts else 0.0

    def chip_html(label, value, sub=None):
        sub_html = f"<div class='sub'>{sub}</div>" if sub else ""
        return f"""
        <div class="chip">
          <div class="lbl">{label}</div>
          <div class="val">{value}</div>
          {sub_html}
        </div>
        """

    html = "<div class='metrics-row'>"
    html += chip_html(prefix + "Brut", f"{brut:,.2f} €".replace(",", " "),
                      f"{brut_nuit:,.2f} €/nuit".replace(",", " "))
    html += chip_html(prefix + "Net", f"{net:,.2f} €".replace(",", " "),
                      f"{net_nuit:,.2f} €/nuit".replace(",", " "))
    html += chip_html(prefix + "Charges", f"{ch:,.2f} €".replace(",", " "))
    html += chip_html(prefix + "Nuitées", f"{int(nts)}")
    html += chip_html(prefix + "Commission moy.", f"{pct_mean:.2f} %")
    html += "</div>"

    st.markdown(html, unsafe_allow_html=True)

# ==============================  UTILS / SCHEMA  ===========================

def to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()

    # Dates pures
    for col in ["date_arrivee", "date_depart"]:
        if col in df.columns:
            df[col] = df[col].apply(to_date_only)

    # Numériques
    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Calcul charges / %
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

    # AAAA / MM
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
        df["MM"]    = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)
        df["AAAA"] = pd.to_numeric(df["AAAA"], errors="coerce").astype("Int64")
        df["MM"]   = pd.to_numeric(df["MM"], errors="coerce").astype("Int64")

    # Colonnes minimales
    for k, v in {"plateforme": "Autre", "nom_client": "", "telephone": ""}.items():
        if k not in df.columns:
            df[k] = v

    # Téléphone : enlève apostrophe Excel (on la remettra à l’export)
    if "telephone" in df.columns:
        def _clean_tel(x):
            s = "" if pd.isna(x) else str(x).strip()
            if s.startswith("'"):
                s = s[1:]
            return s
        df["telephone"] = df["telephone"].apply(_clean_tel)

    if "ical_uid" not in df.columns:
        df["ical_uid"] = ""

    cols_order = [
        "nom_client","plateforme","telephone","date_arrivee","date_depart","nuitees",
        "prix_brut","prix_net","charges","%","AAAA","MM","ical_uid"
    ]
    ordered = [c for c in cols_order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

def _marque_totaux(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series([], dtype=bool)
    mask = pd.Series(False, index=df.index)
    for col in ["nom_client", "plateforme"]:
        if col in df.columns:
            mask |= df[col].astype(str).strip().str.lower().eq("total")
    has_no_dates = pd.Series(True, index=df.index)
    for c in ["date_arrivee","date_depart"]:
        if c in df.columns:
            has_no_dates &= df[c].isna()
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
    df_core  = df[~tot_mask].copy()
    by_cols = [c for c in ["date_arrivee","nom_client"] if c in df_core.columns]
    if by_cols:
        df_core = df_core.sort_values(by=by_cols, na_position="last").reset_index(drop=True)
    return pd.concat([df_core, df_total], ignore_index=True)

# ==============================  EXCEL I/O + GITHUB  =======================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path)

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return pd.DataFrame()
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        df = ensure_schema(df)
        df = _trier_et_recoller_totaux(df)
        return df
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return pd.DataFrame()

def _excel_bytes_from_df(df: pd.DataFrame) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _trier_et_recoller_totaux(ensure_schema(df)).to_excel(writer, index=False)
    return buf.getvalue()

def sauvegarder_donnees(df: pd.DataFrame):
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
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def github_save_file(file_bytes: bytes, commit_msg: str = "Update reservations.xlsx"):
    token = st.secrets.get("GITHUB_TOKEN")
    repo  = st.secrets.get("GITHUB_REPO")
    branch= st.secrets.get("GITHUB_BRANCH", "main")
    path  = st.secrets.get("GITHUB_PATH", "reservations.xlsx")
    if not token or not repo:
        return False, "Secrets GitHub non configurés"

    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    sha = None
    try:
        r = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass
    payload = {
        "message": commit_msg,
        "content": base64.b64encode(file_bytes).decode("utf-8"),
        "branch": branch
    }
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(api_url, headers=headers, json=payload, timeout=20)
        if r.status_code in (200, 201):
            return True, "GitHub OK"
        return False, f"GitHub PUT {r.status_code}: {r.text}"
    except Exception as e:
        return False, f"GitHub error: {e}"

def restauration_from_uploader(uploaded_file):
    try:
        df_new = pd.read_excel(uploaded_file)
        df_new = _trier_et_recoller_totaux(ensure_schema(df_new))
        sauvegarder_donnees(df_new)
        file_bytes = _excel_bytes_from_df(df_new)
        ok, msg = github_save_file(file_bytes, commit_msg="Restore reservations.xlsx")
        if ok:
            st.success("✅ Restauration OK + poussée GitHub.")
        else:
            st.info(f"ℹ️ Restauration OK (GitHub) : {msg}")
        st.rerun()
    except Exception as e:
        st.error(f"Erreur import: {e}")

# ==============================  LIENS / SMS  ==============================

def clean_tel_display(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^\d\+ ]", "", s)
    return s

def tel_to_uri(s: str) -> str:
    s = clean_tel_display(s)
    if not s:
        return ""
    s_uri = re.sub(r"[ \-\.]", "", s)
    return f"tel:{s_uri}"

def sms_message_arrivee(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "").strip()
    plateforme = str(row.get("plateforme") or "").strip()
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart"); nuitees = row.get("nuitees")
    d1s = d1.strftime("%Y/%m/%d") if isinstance(d1, date) else ""
    d2s = d2.strftime("%Y/%m/%d") if isinstance(d2, date) else ""
    return (
        f"VILLA TOBIAS - Plateforme : {plateforme}\n"
        f"Date d'arrivee : {d1s}  Date depart : {d2s}  Nombre de nuitees : {nuitees}\n\n"
        f"Bonjour {nom}\n\n"
        "Nous sommes heureux de vous accueillir prochainement et vous prions de bien vouloir nous communiquer votre heure d'arrivee. "
        "Nous vous attendrons sur place pour vous remettre les cles de l'appartement et vous indiquer votre emplacement de parking. "
        "Nous vous souhaitons un bon voyage et vous disons a demain.\n\n"
        "Annick & Charley"
    )

def sms_message_depart_24h(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "").strip()
    return (
        f"Bonjour {nom},\n\n"
        "Un grand merci d’avoir choisi notre appartement pour votre séjour ! "
        "Nous espérons que vous avez passé un moment aussi agréable que celui que nous avons eu à vous accueillir.\n\n"
        "Si l’envie vous prend de revenir explorer encore un peu notre ville (ou simplement retrouver le confort de notre petit cocon), "
        "sachez que notre porte vous sera toujours grande ouverte.\n\n"
        "Au plaisir de vous accueillir à nouveau,\n"
        "Annick & Charley"
    )

# ==============================  VUES  =====================================

def vue_en_cours_banner(df: pd.DataFrame):
    if df is None or df.empty:
        return
    dft = ensure_schema(df).copy()
    if dft.empty:
        return

    mask_total = _marque_totaux(dft)
    today = date.today()
    def _is_date(x): return isinstance(x, date)

    en_cours = dft[
        (~mask_total)
        & dft["date_arrivee"].apply(_is_date)
        & dft["date_depart"].apply(_is_date)
        & (dft["date_arrivee"] <= today)
        & (dft["date_depart"] > today)
    ].copy()

    st.markdown("### 🟢 En cours aujourd’hui")
    if en_cours.empty:
        st.info(f"Aucun séjour en cours aujourd’hui ({today.strftime('%Y/%m/%d')}).")
        return

    en_cours = en_cours.sort_values(["date_depart", "nom_client"]).copy()
    en_cours["date_arrivee"] = en_cours["date_arrivee"].apply(lambda d: d.strftime("%Y/%m/%d"))
    en_cours["date_depart"] = en_cours["date_depart"].apply(lambda d: d.strftime("%Y/%m/%d"))

    def _make_links(row):
        tel_raw = str(row.get("telephone") or "").strip()
        tel_ui = tel_to_uri(tel_raw)
        sms_txt = sms_message_arrivee(row)
        tel_clean = re.sub(r"[ \-\.]", "", clean_tel_display(tel_raw))
        sms_uri = f"sms:{tel_clean}?&body={quote(sms_txt)}" if tel_clean else ""
        link_tel = f'<a href="{tel_ui}">📞 Appeler</a>' if tel_ui else ""
        link_sms = f'<a href="{sms_uri}">📲 SMS</a>' if sms_uri else ""
        return link_tel, link_sms

    links = en_cours.apply(_make_links, axis=1, result_type="expand")
    en_cours["📞 Appeler"] = links[0]
    en_cours["📲 SMS"] = links[1]

    colonnes = ["plateforme", "nom_client", "date_arrivee", "date_depart", "nuitees", "📞 Appeler", "📲 SMS"]
    colonnes = [c for c in colonnes if c in en_cours.columns]
    out = en_cours.loc[:, colonnes].copy()
    st.markdown(out.to_html(index=False, escape=False), unsafe_allow_html=True)

def vue_reservations(df: pd.DataFrame):
    # Titre + boutons à droite
    c_title, c_btns = st.columns([3, 2])
    with c_title:
        header("📋 Réservations", "Filtrez, exportez, modifiez en un clin d’œil")
    with c_btns:
        st.markdown("<div class='btn-right'>", unsafe_allow_html=True)
        data_xlsx = _excel_bytes_from_df(df) if not df.empty else b""
        st.download_button(
            "💾 Sauvegarde XLSX",
            data=data_xlsx,
            file_name="reservations.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_top"
        )
        restore_click = st.button("📤 Restauration XLSX", key="restore_top_btn")
        st.markdown("</div>", unsafe_allow_html=True)
        if restore_click:
            st.session_state.show_restore_top = True
        if st.session_state.get("show_restore_top"):
            up = st.file_uploader("Sélectionner un fichier .xlsx", type=["xlsx"], key="restore_top_uploader")
            if up is not None:
                restauration_from_uploader(up)
            if st.button("Annuler", key="restore_top_cancel"):
                st.session_state.show_restore_top = False
                st.rerun()

    # Bandeau "En cours aujourd'hui"
    vue_en_cours_banner(df)

    show = _trier_et_recoller_totaux(ensure_schema(df)).copy()
    if show.empty:
        st.info("Aucune réservation.")
        return

    for col in ["date_arrivee", "date_depart"]:
        if col in show.columns:
            show[col] = show[col].apply(format_date_str)

    st.dataframe(show, use_container_width=True)

    # 🔴 Totaux corrigés : on exclut les lignes “Total”
    st.markdown("#### Totaux")
    metrics_bar(show, prefix="Total ")

def vue_ajouter(df: pd.DataFrame):
    header("➕ Ajouter une réservation", "Saisie rapide (libellés inline)")
    with st.form("ajout_resa"):
        # Ligne 1 : Nom | Téléphone
        c1, c2 = st.columns(2)
        with c1:
            nom = inline_input("Nom", st.text_input, key="add_nom", value="")
        with c2:
            tel = inline_input("Téléphone (+33...)", st.text_input, key="add_tel", value="")

        # Ligne 2 : Plateforme | Arrivée | Départ
        c3, c4, c5 = st.columns([1, 1, 1])
        with c3:
            plateforme = inline_input(
                "Plateforme", st.selectbox, key="add_pf",
                options=["Booking", "Airbnb", "Autre"], index=0
            )

        if "ajout_arrivee" not in st.session_state:
            st.session_state.ajout_arrivee = date.today()

        with c4:
            arrivee = inline_input("Arrivée", st.date_input, key="ajout_arrivee")

        min_dep = st.session_state.ajout_arrivee + timedelta(days=1)
        if "ajout_depart" not in st.session_state or not isinstance(st.session_state.ajout_depart, date):
            st.session_state.ajout_depart = min_dep
        elif st.session_state.ajout_depart < min_dep:
            st.session_state.ajout_depart = min_dep

        with c5:
            depart = inline_input("Départ", st.date_input, key="ajout_depart", min_value=min_dep)

        # Ligne 3 : Prix brut | Prix net | (Charges+%)
        c6, c7, c8, c9 = st.columns([1, 1, 1, 1])
        with c6:
            prix_brut = inline_input(
                "Prix brut (€)", st.number_input, key="add_brut",
                min_value=0.0, step=1.0, format="%.2f"
            ) or 0.0
        with c7:
            prix_net = inline_input(
                "Prix net (€)", st.number_input, key="add_net",
                min_value=0.0, step=1.0, format="%.2f"
            ) or 0.0

        charges_calc = max(float(prix_brut) - float(prix_net), 0.0)
        pct_calc = (charges_calc / float(prix_brut) * 100.0) if float(prix_brut) > 0 else 0.0

        with c8:
            inline_input("Charges (€)", st.text_input, key="add_ch",
                         value=f"{charges_calc:.2f}", disabled=True)
        with c9:
            inline_input("Commission (%)", st.text_input, key="add_pct",
                         value=f"{pct_calc:.2f}", disabled=True)

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
            "MM": arrivee.month,
            "ical_uid": "",
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        df2 = _trier_et_recoller_totaux(df2)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    header("✏️ Modifier / Supprimer", "Libellés inline, mêmes sections que l’ajout")
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
        # Ligne 1
        c1, c2 = st.columns(2)
        with c1:
            nom = inline_input("Nom", st.text_input, key="m_nom", value=df.at[i, "nom_client"])
        with c2:
            tel = inline_input("Téléphone", st.text_input, key="m_tel",
                               value=df.at[i, "telephone"] if "telephone" in df.columns else "")

        # Ligne 2
        c3, c4, c5 = st.columns([1,1,1])
        plateformes = ["Booking", "Airbnb", "Autre"]
        index_pf = plateformes.index(df.at[i, "plateforme"]) if df.at[i, "plateforme"] in plateformes else 2
        with c3:
            plateforme = inline_input("Plateforme", st.selectbox, key="m_pf",
                                      options=plateformes, index=index_pf)
        with c4:
            arrivee = inline_input("Arrivée", st.date_input, key="m_arr",
                                   value=df.at[i, "date_arrivee"] if isinstance(df.at[i, "date_arrivee"], date) else date.today())
        with c5:
            def_dep = df.at[i, "date_depart"] if isinstance(df.at[i, "date_depart"], date) else (arrivee + timedelta(days=1))
            depart = inline_input("Départ", st.date_input, key="m_dep", value=def_dep)

        # Ligne 3
        c6, c7 = st.columns([1,1])
        with c6:
            brut = inline_input("Prix brut (€)", st.number_input, key="m_brut",
                                value=float(df.at[i, "prix_brut"]) if pd.notna(df.at[i, "prix_brut"]) else 0.0,
                                format="%.2f", min_value=0.0, step=1.0)
        with c7:
            net = inline_input("Prix net (€)", st.number_input, key="m_net",
                               value=float(df.at[i, "prix_net"]) if pd.notna(df.at[i, "prix_net"]) else 0.0,
                               format="%.2f", min_value=0.0, step=1.0)

        charges_calc = max((brut or 0) - (net or 0), 0.0)
        pct_calc = (charges_calc / (brut or 1) * 100) if brut else 0.0
        c8, c9 = st.columns([1,1])
        with c8:
            inline_input("Charges (€)", st.text_input, key="m_ch",
                         value=f"{charges_calc:.2f}", disabled=True)
        with c9:
            inline_input("Commission (%)", st.text_input, key="m_pct",
                         value=f"{pct_calc:.2f}", disabled=True)

        cA, cB = st.columns(2)
        b_modif = cA.form_submit_button("💾 Enregistrer")
        b_del   = cB.form_submit_button("🗑 Supprimer")

    if b_modif:
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[i, "nom_client"] = nom.strip()
        df.at[i, "plateforme"] = plateforme
        df.at[i, "telephone"]  = tel.strip()
        df.at[i, "date_arrivee"] = arrivee
        df.at[i, "date_depart"]  = depart
        df.at[i, "prix_brut"] = float(brut)
        df.at[i, "prix_net"]  = float(net)
        df.at[i, "charges"]   = round(brut - net, 2)
        df.at[i, "%"]         = round(((brut - net) / brut * 100) if brut else 0, 2)
        df.at[i, "nuitees"]   = (depart - arrivee).days
        df.at[i, "AAAA"]      = arrivee.year
        df.at[i, "MM"]        = arrivee.month
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
    header("📅 Calendrier", "Vue mensuelle avec repérage rapide des séjours")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    c_mois, c_annee = st.columns([2, 1])
    with c_mois:
        mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, (date.today().month - 1)))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    with c_annee:
        annee = st.selectbox("Année", annees, index=max(0, len(annees) - 1))

    mois_index = list(calendar.month_name).index(mois_nom)

    jours = [date(annee, mois_index, j + 1) for j in range(calendar.monthrange(annee, mois_index)[1])]
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
                contenu = f"**{jour:02d}**\n" + "\n".join(planning.get(d, []))
                ligne.append(contenu)
        table.append(ligne)

    st.table(pd.DataFrame(table, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

def vue_rapport(df: pd.DataFrame):
    header("📊 Rapport (1 année)", "Filtres et graphiques triés 01 → 12")
    df = _trier_et_recoller_totaux(ensure_schema(df)).copy()
    if df.empty:
        st.info("Aucune donnée.")
        return

    if "AAAA" not in df.columns or "MM" not in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA)
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA)

    df["AAAA"] = pd.to_numeric(df["AAAA"], errors="coerce")
    df["MM"]   = pd.to_numeric(df["MM"], errors="coerce")
    df = df.dropna(subset=["AAAA","MM"]).copy()
    df["AAAA"] = df["AAAA"].astype(int)
    df["MM"]   = df["MM"].astype(int)

    annees = sorted(df["AAAA"].unique().tolist())
    if not annees:
        st.info("Aucune année disponible.")
        return

    cA, cB, cC = st.columns([1, 2, 1])
    with cA:
        annee = st.selectbox("Année", annees, index=len(annees) - 1, key="rapport_annee")
    data = df[df["AAAA"] == int(annee)].copy()

    plateformes = ["Toutes"] + sorted(data["plateforme"].dropna().unique().tolist())
    with cB:
        filtre_plateforme = st.selectbox("Plateforme", plateformes, key="rapport_pf")
    with cC:
        filtre_mois_label = st.selectbox("Mois (01–12)", ["Tous"] + [f"{i:02d}" for i in range(1, 13)], key="rapport_mois")

    if filtre_plateforme != "Toutes":
        data = data[data["plateforme"] == filtre_plateforme]
    if filtre_mois_label != "Tous":
        data = data[data["MM"] == int(filtre_mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    data = data[(data["MM"] >= 1) & (data["MM"] <= 12)]
    data["prix_brut/nuit"] = (pd.to_numeric(data["prix_brut"], errors="coerce") / data["nuitees"]).replace([np.inf, -np.inf], np.nan).fillna(0).round(2)
    data["prix_net/nuit"]  = (pd.to_numeric(data["prix_net"],  errors="coerce") / data["nuitees"]).replace([np.inf, -np.inf], np.nan).fillna(0).round(2)

    stats = (
        data.groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 charges=("charges","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
    )
    if stats.empty:
        st.info("Aucune donnée après agrégation.")
        return

    plats = sorted(stats["plateforme"].unique().tolist())
    full = []
    for m in range(1, 13):
        for p in plats:
            row = stats[(stats["MM"] == m) & (stats["plateforme"] == p)]
            if row.empty:
                full.append({"MM": m, "plateforme": p, "prix_brut": 0.0, "prix_net": 0.0, "charges": 0.0, "nuitees": 0})
            else:
                full.append(row.iloc[0].to_dict())
    stats = pd.DataFrame(full).sort_values(["MM","plateforme"]).reset_index(drop=True)

    stats_view = stats.copy()
    mask_non_zero = (stats_view[["prix_brut", "prix_net", "charges", "nuitees"]].sum(axis=1) != 0)
    stats_view = stats_view[mask_non_zero]
    st.dataframe(
        stats_view.rename(columns={"MM": "Mois"})[["Mois","plateforme","prix_brut","prix_net","charges","nuitees"]],
        use_container_width=True
    )

    metrics_bar(data, prefix="Total ")

    # Graphes (01→12, barres groupées)
    def plot_grouped_bars(metric: str, title: str, ylabel: str):
        months = list(range(1, 13))
        base_x = np.arange(len(months), dtype=float)
        plats_sorted = sorted(plats)
        width = 0.8 / max(1, len(plats_sorted))

        fig, ax = plt.subplots(figsize=(10, 4))
        for i, p in enumerate(plats_sorted):
            sub = stats[stats["plateforme"] == p]
            vals = {int(mm): float(v) for mm, v in zip(sub["MM"], sub[metric])}
            y = np.array([vals.get(m, 0.0) for m in months], dtype=float)
            x = base_x + (i - (len(plats_sorted)-1)/2) * width
            ax.bar(x, y, width=width, label=p)

        ax.set_xlim(-0.5, 11.5)
        ax.set_xticks(base_x)
        ax.set_xticklabels([f"{m:02d}" for m in months])
        ax.set_xlabel(f"Mois ({annee})")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(loc="upper left", frameon=False)
        ax.grid(axis="y", linestyle="--", alpha=0.3)
        st.pyplot(fig); plt.close(fig)

    plot_grouped_bars("prix_brut", "💰 Revenus bruts", "€")
    plot_grouped_bars("charges", "💸 Charges", "€")
    plot_grouped_bars("nuitees", "🛌 Nuitées", "Nuitées")

def vue_clients(df: pd.DataFrame):
    header("👥 Liste des clients", "Export et calculs par nuitée")
    df = _trier_et_recoller_totaux(ensure_schema(df))
    if df.empty:
        st.info("Aucune donnée.")
        return

    cA, cB = st.columns([1,1])
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    with cA:
        annee = st.selectbox("Année", annees) if annees else None
    with cB:
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

# ==============================  SMS (manuel)  =============================

def vue_sms(df: pd.DataFrame):
    header("✉️ SMS", "Préparez et envoyez depuis votre téléphone (liens Appeler/SMS)")
    dft = _trier_et_recoller_totaux(ensure_schema(df)).copy()
    if dft.empty:
        st.info("Aucune donnée.")
        return

    today = date.today()
    cA, cB = st.columns(2)
    with cA:
        cible_arrivee = st.date_input("📅 Date d’arrivée ciblée (accueil)", value=today + timedelta(days=1))
    with cB:
        cible_depart = st.date_input("📅 Date de départ ciblée (remerciement J+1)", value=today - timedelta(days=1))

    st.markdown("#### 🟢 Arrivées (messages d’accueil)")
    arr = dft[(dft["date_arrivee"] == cible_arrivee)].copy()
    if arr.empty:
        st.info("Aucune arrivée à cette date.")
    else:
        for _, row in arr.iterrows():
            tel_ui = tel_to_uri(str(row.get("telephone") or ""))
            sms_txt = sms_message_arrivee(row)
            tel_clean = re.sub(r"[ \-\.]", "", clean_tel_display(str(row.get("telephone") or "")))
            sms_uri = f"sms:{tel_clean}?&body={quote(sms_txt)}" if tel_clean else ""
            col1, col2, col3 = st.columns([3,1,1])
            with col1:
                st.markdown(f"**{row.get('plateforme','')} — {row.get('nom_client','')}**  "
                            f"({format_date_str(row.get('date_arrivee'))} → {format_date_str(row.get('date_depart'))}, "
                            f"{row.get('nuitees','')} nuitées)")
            with col2:
                if tel_ui:
                    st.markdown(f"[📞 Appeler]({tel_ui})")
            with col3:
                if sms_uri:
                    st.markdown(f"[📲 SMS]({sms_uri})")
            st.code(sms_txt, language="text")

    st.markdown("#### 🟡 Départs (remerciement J+1)")
    dep = dft[(dft["date_depart"] == cible_depart)].copy()
    if dep.empty:
        st.info("Aucun départ à cette date.")
    else:
        for _, row in dep.iterrows():
            tel_ui = tel_to_uri(str(row.get("telephone") or ""))
            sms_txt = sms_message_depart_24h(row)
            tel_clean = re.sub(r"[ \-\.]", "", clean_tel_display(str(row.get("telephone") or "")))
            sms_uri = f"sms:{tel_clean}?&body={quote(sms_txt)}" if tel_clean else ""
            col1, col2, col3 = st.columns([3,1,1])
            with col1:
                st.markdown(f"**{row.get('plateforme','')} — {row.get('nom_client','')}**  "
                            f"(Départ {format_date_str(row.get('date_depart'))})")
            with col2:
                if tel_ui:
                    st.markdown(f"[📞 Appeler]({tel_ui})")
            with col3:
                if sms_uri:
                    st.markdown(f"[📲 SMS]({sms_uri})")
            st.code(sms_txt, language="text")

# ==============================  iCal (simple)  ============================

def load_ical_sources():
    if os.path.exists(ICAL_SOURCES):
        try:
            with open(ICAL_SOURCES, "r", encoding="utf-8") as f:
                obj = json.load(f)
            return obj.get("sources", [])
        except Exception:
            return []
    return []

def save_ical_sources(sources):
    try:
        with open(ICAL_SOURCES, "w", encoding="utf-8") as f:
            json.dump({"sources": sources}, f, ensure_ascii=False, indent=2)
        st.success("📁 Sources iCal sauvegardées.")
    except Exception as e:
        st.error(f"Impossible d’écrire {ICAL_SOURCES}: {e}")

def parse_ics(text: str):
    events = []
    if not text:
        return events
    for block in re.split(r"BEGIN:VEVENT", text)[1:]:
        block = "BEGIN:VEVENT" + block
        if "END:VEVENT" not in block:
            continue
        vevent = block.split("END:VEVENT", 1)[0]

        def get_line(prop):
            m = re.search(rf"^{prop}[:;](.+)$", vevent, re.MULTILINE)
            return m.group(1).strip() if m else ""

        uid = get_line("UID")
        dtstart = get_line("DTSTART")
        dtend   = get_line("DTEND")
        summary = get_line("SUMMARY")

        def parse_dt(s):
            if not s:
                return None
            s = s.strip()
            try:
                if len(s) >= 8:
                    y, m, d = int(s[0:4]), int(s[4:6]), int(s[6:8])
                    return date(y, m, d)
            except Exception:
                return None
            return None

        d1 = parse_dt(dtstart)
        d2 = parse_dt(dtend)
        events.append({"uid": uid, "start": d1, "end": d2, "summary": summary})
    return events

def vue_ical(df: pd.DataFrame):
    header("🔄 iCal", "Ajoutez vos URLs et importez les réservations manquantes")
    sources = load_ical_sources()

    st.markdown("#### 📚 Sources actuelles")
    if sources:
        for i, s in enumerate(sources):
            c1, c2, c3 = st.columns([1,3,1])
            with c1:
                name = st.text_input(f"Nom #{i+1}", value=s.get("name",""), key=f"ical_name_{i}")
            with c2:
                url  = st.text_input(f"URL #{i+1}", value=s.get("url",""), key=f"ical_url_{i}")
            with c3:
                if st.button("🗑 Supprimer", key=f"del_src_{i}"):
                    sources.pop(i)
                    save_ical_sources(sources)
                    st.rerun()
            s["name"], s["url"] = name, url
        if st.button("💾 Sauvegarder les sources"):
            save_ical_sources(sources)
    else:
        st.info("Aucune source configurée.")

    st.markdown("#### ➕ Ajouter une nouvelle source")
    c1, c2, c3 = st.columns([1.2, 2.8, 1])
    with c1:
        new_name = st.text_input("Nom", key="new_ical_name", placeholder="Booking / Airbnb / Autre")
    with c2:
        new_url  = st.text_input("URL", key="new_ical_url", placeholder="https://...ics")
    with c3:
        if st.button("Ajouter"):
            if new_name and new_url:
                sources.append({"name": new_name.strip(), "url": new_url.strip()})
                save_ical_sources(sources)
                st.rerun()
            else:
                st.warning("Veuillez renseigner un nom et une URL.")

    st.markdown("#### ⬇️ Charger et comparer")
    if st.button("Analyser les sources iCal"):
        if not sources:
            st.warning("Ajoutez au moins une source.")
            return
        df_local = ensure_schema(df).copy()
        uids_existants = set((df_local["ical_uid"].dropna().astype(str)).tolist()) if "ical_uid" in df_local.columns else set()

        a_importer = []
        erreurs = []
        for s in sources:
            nom_src = s.get("name","")
            url = s.get("url","")
            try:
                r = requests.get(url, timeout=20)
                if r.status_code != 200:
                    erreurs.append(f"{nom_src}: HTTP {r.status_code}")
                    continue
                evs = parse_ics(r.text)
                for ev in evs:
                    if ev["uid"] and ev["uid"] in uids_existants:
                        continue
                    if isinstance(ev["start"], date) and isinstance(ev["end"], date):
                        a_importer.append({
                            "plateforme": nom_src or "Autre",
                            "nom_client": (ev["summary"] or "").strip(),
                            "telephone": "",
                            "date_arrivee": ev["start"],
                            "date_depart": ev["end"],
                            "prix_brut": 0.0, "prix_net": 0.0, "charges": 0.0, "%": 0.0,
                            "nuitees": (ev["end"] - ev["start"]).days if (ev["end"] and ev["start"]) else None,
                            "AAAA": ev["start"].year if ev["start"] else pd.NA,
                            "MM":   ev["start"].month if ev["start"] else pd.NA,
                            "ical_uid": ev["uid"] or "",
                        })
            except Exception as e:
                erreurs.append(f"{nom_src}: {e}")

        if erreurs:
            st.warning("Erreurs rencontrées :\n- " + "\n- ".join(erreurs))

        if not a_importer:
            st.success("Aucun nouvel événement à importer (tout est déjà présent).")
            return

        st.markdown("##### ✅ Nouveaux événements détectés")
        df_new = pd.DataFrame(a_importer)
        if not df_new.empty:
            df_new_show = df_new.copy()
            for col in ["date_arrivee","date_depart"]:
                df_new_show[col] = df_new_show[col].apply(format_date_str)
            st.dataframe(df_new_show[["plateforme","nom_client","date_arrivee","date_depart","nuitees","ical_uid"]], use_container_width=True)

            if st.button("📥 Importer ces événements dans Excel"):
                df_all = pd.concat([df, df_new], ignore_index=True)
                df_all = _trier_et_recoller_totaux(df_all)
                sauvegarder_donnees(df_all)
                st.success("Import iCal terminé.")
                st.rerun()

# ==============================  APP  ======================================

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    inject_css()
    render_cache_button_sidebar()

    onglet = st.sidebar.radio(
        "Aller à",
        [
            "📋 Réservations",
            "➕ Ajouter",
            "✏️ Modifier / Supprimer",
            "📅 Calendrier",
            "📊 Rapport",
            "👥 Liste clients",
            "✉️ SMS",
            "🔄 iCal",
        ],
    )

    df = charger_donnees()

    # Restauration XLSX (option secondaire en sidebar)
    with st.sidebar:
        st.markdown("### ")
        holder = st.container()
        with holder:
            red = st.container()
            with red:
                clicked = st.button("📤 Restauration XLSX (sidebar)", key="restore_sb_btn")
            st.markdown('<div class="btn-danger"></div>', unsafe_allow_html=True)
        if clicked:
            up2 = st.file_uploader("Sélectionner un fichier .xlsx (sidebar)", type=["xlsx"], key="restore_sb_uploader")
            if up2 is not None:
                restauration_from_uploader(up2)

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
    elif onglet == "✉️ SMS":
        vue_sms(df)
    elif onglet == "🔄 iCal":
        vue_ical(df)

if __name__ == "__main__":
    main()