import streamlit as st
import pandas as pd
import numpy as np
import os
import io
import calendar
import colorsys
from datetime import date, datetime, timedelta

# ==========================
# Constantes
# ==========================
EXCEL_FILE = "reservations.xlsx"
LOGO_FILE = "logo.png"

PLATFORM_COLORS_DEFAULT = {
    "Booking": "#1e90ff",
    "Airbnb": "#ff5a5f",
    "Abritel": "#6a1b9a",
    "Autre": "#f59e0b"
}

# ==========================
# Utilitaires
# ==========================
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    expected = [
        "plateforme", "nom_client", "date_arrivee", "date_depart",
        "prix_brut", "commission", "frais_cb", "prix_net",
        "menage", "taxe_sejour", "base", "paye", "sms",
        "AAAA", "MM"
    ]
    for col in expected:
        if col not in df.columns:
            if col in ["paye", "sms"]:
                df[col] = False
            elif col in ["prix_brut","commission","frais_cb","prix_net","menage","taxe_sejour","base"]:
                df[col] = 0.0
            elif col in ["AAAA","MM"]:
                df[col] = None
            else:
                df[col] = ""
    return df

def split_totals(df: pd.DataFrame):
    core = df.copy()
    core = core.dropna(subset=["date_arrivee", "date_depart"])
    totals = {}
    try:
        totals["Total brut"] = core["prix_brut"].sum()
        totals["Total net"] = core["prix_net"].sum()
        totals["Total base"] = core["base"].sum()
        totals["Total charges"] = (core["commission"] + core["frais_cb"]).sum()
        if totals["Total brut"] > 0:
            totals["Commissions moy. %"] = round(100 * totals["Total charges"] / totals["Total brut"], 2)
        else:
            totals["Commissions moy. %"] = 0
        totals["Nuitées"] = sum((pd.to_datetime(core["date_depart"]) - pd.to_datetime(core["date_arrivee"])).dt.days)
        if totals["Nuitées"] > 0:
            totals["Prix moyen nuitées"] = round(totals["Total brut"] / totals["Nuitées"], 2)
        else:
            totals["Prix moyen nuitées"] = 0
    except Exception as e:
        st.error(f"Erreur calcul totaux: {e}")
    return core, totals

def get_palette():
    if "palette" not in st.session_state:
        st.session_state["palette"] = PLATFORM_COLORS_DEFAULT.copy()
    return st.session_state["palette"]

def platform_badge(pf: str) -> str:
    palette = get_palette()
    col = palette.get(pf, "#999999")
    return f'<span style="display:inline-block;background:{col};color:white;padding:2px 6px;border-radius:4px;font-size:0.8em;">{pf}</span>'

# ==========================
# Vue : Calendrier
# ==========================
def vue_calendrier(df: pd.DataFrame):
    palette = get_palette()
    st.title("📅 Calendrier mensuel (cases colorées par plateforme)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    # Sélecteurs mois/année
    col1, col2 = st.columns(2)
    mois_nom = col1.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = col2.selectbox("Année", annees, index=len(annees)-1)

    mois = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, mois)[1]
    jours = [date(annee, mois, j) for j in range(1, nb_jours+1)]

    # Indexation des réservations
    core, _ = split_totals(df)
    planning = {j: [] for j in jours}
    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (isinstance(d1, (date, datetime)) and isinstance(d2, (date, datetime))):
            continue
        d1 = pd.to_datetime(d1).date()
        d2 = pd.to_datetime(d2).date()
        pf = str(row.get("plateforme") or "Autre")
        nom = str(row.get("nom_client") or "")
        for j in jours:
            if d1 <= j < d2:
                planning[j].append((pf, nom))
# ---------- rendu grille ----------
    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, mois)

    # Fonctions couleur
    def lighten(hex_color: str, factor: float = 0.75) -> str:
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
        l = min(1.0, l + (1.0 - l) * factor)
        r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
        return f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"

    def ideal_text(bg_hex: str) -> str:
        bg_hex = bg_hex.lstrip("#")
        r = int(bg_hex[0:2], 16)
        g = int(bg_hex[2:4], 16)
        b = int(bg_hex[4:6], 16)
        luminance = (0.299*r + 0.587*g + 0.114*b) / 255
        return "#000000" if luminance > 0.6 else "#ffffff"

    # Prépare texte et couleurs
    table = []
    bg_table = []
    fg_table = []

    for semaine in monthcal:
        row_text = []
        row_bg = []
        row_fg = []
        for j in semaine:
            if j == 0:
                row_text.append("")
                row_bg.append("transparent")
                row_fg.append(None)
            else:
                d = date(annee, mois, j)
                items = planning.get(d, [])
                # Texte : jour + noms (une par ligne)
                content_lines = [str(j)] + [nom for _, nom in items]
                row_text.append("\n".join(content_lines))

                # Couleur : celle de la plateforme du 1er item (si présent), en clair
                if items:
                    base = palette.get(items[0][0], "#999999")
                    bg = lighten(base, 0.75)
                    fg = ideal_text(bg)
                else:
                    bg, fg = "transparent", None
                row_bg.append(bg)
                row_fg.append(fg)
        table.append(row_text)
        bg_table.append(row_bg)
        fg_table.append(row_fg)

    df_table = pd.DataFrame(table, columns=headers)

    # Style cellule par cellule (fond + couleur texte + retour à la ligne)
    def style_row(vals, row_idx):
        css = []
        for col_idx, _ in enumerate(vals):
            bg = bg_table[row_idx][col_idx]
            fg = fg_table[row_idx][col_idx] or "inherit"
            css.append(
                f"background-color:{bg};color:{fg};white-space:pre-wrap;"
                f"border:1px solid rgba(127,127,127,0.25);"
            )
        return css

    styler = df_table.style
    for r in range(df_table.shape[0]):
        styler = styler.apply(lambda v, r=r: style_row(v, r), axis=1)

    # Légende plateformes
    st.caption("Légende :")
    leg = " • ".join([
        f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{palette[p]};margin-right:6px;border-radius:3px;"></span>{p}'
        for p in sorted(palette.keys())
    ])
    st.markdown(leg, unsafe_allow_html=True)

    st.dataframe(styler, use_container_width=True, height=450)

# ==========================
# Lectures / sauvegardes Excel
# ==========================
def _to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    df = pd.read_excel(path, engine="openpyxl")
    # Harmonise champs connus si présents
    for c in ["date_arrivee", "date_depart"]:
        if c in df.columns:
            df[c] = df[c].apply(_to_date_only)
    return df

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(EXCEL_FILE):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(EXCEL_FILE)
        df = _read_excel_cached(EXCEL_FILE, mtime)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def sauvegarder_donnees(df: pd.DataFrame):
    try:
        df2 = ensure_schema(df).copy()
        # recalc AAAA/MM si colonnes dates présentes
        if "date_arrivee" in df2.columns:
            df2["AAAA"] = df2["date_arrivee"].apply(lambda d: d.year if isinstance(d, (date, datetime)) else None)
            df2["MM"]   = df2["date_arrivee"].apply(lambda d: d.month if isinstance(d, (date, datetime)) else None)
        df2.to_excel(EXCEL_FILE, index=False, engine="openpyxl")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = io.BytesIO()
    try:
        ensure_schema(df).to_excel(buf, index=False, engine="openpyxl")
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = b""
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data_xlsx) == 0),
    )

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            df_new = pd.read_excel(up, engine="openpyxl")
            df_new = ensure_schema(df_new)
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

# ==========================
# Aides UI (totaux, recherche)
# ==========================
def kpi_chips(df: pd.DataFrame):
    core, totals = split_totals(df)
    if not totals:
        return
    b = totals.get("Total brut", 0)
    n = totals.get("Total net", 0)
    base = totals.get("Total base", 0)
    ch = totals.get("Total charges", 0)
    nuits = totals.get("Nuitées", 0)
    pct = totals.get("Commissions moy. %", 0)
    pm_nuit = totals.get("Prix moyen nuitées", 0)

    html = f"""
    <style>
    .chips-wrap {{ display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px 0; }}
    .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12); border: 1px solid rgba(127,127,127,0.25); font-size:0.9rem; }}
    .chip b {{ display:block; margin-bottom:3px; font-size:0.85rem; opacity:0.8; }}
    .chip .v {{ font-weight:600; }}
    </style>
    <div class="chips-wrap">
      <div class="chip"><b>Total Brut</b><div class="v">{b:,.2f} €</div></div>
      <div class="chip"><b>Total Net</b><div class="v">{n:,.2f} €</div></div>
      <div class="chip"><b>Total Base</b><div class="v">{base:,.2f} €</div></div>
      <div class="chip"><b>Total Charges</b><div class="v">{ch:,.2f} €</div></div>
      <div class="chip"><b>Nuitées</b><div class="v">{nuits}</div></div>
      <div class="chip"><b>Commission moy.</b><div class="v">{pct:.2f} %</div></div>
      <div class="chip"><b>Prix moyen/nuit</b><div class="v">{pm_nuit:,.2f} €</div></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def format_date_str(d):
    return pd.to_datetime(d).strftime("%Y/%m/%d") if pd.notna(d) else ""

def search_box(df: pd.DataFrame) -> pd.DataFrame:
    q = st.text_input("🔎 Recherche (nom, plateforme, téléphone…)", "")
    if not q:
        return df
    ql = q.strip().lower()
    def _match(v):
        s = "" if pd.isna(v) else str(v)
        return ql in s.lower()
    mask = (
        df.get("nom_client", pd.Series(dtype=str)).apply(_match) |
        df.get("plateforme", pd.Series(dtype=str)).apply(_match) |
        df.get("telephone", pd.Series(dtype=str)).apply(_match)
    )
    return df[mask].copy()

# ==========================
# Vues principales (inchangées)
# ==========================
def vue_reservations(df: pd.DataFrame):
    palette = get_palette()
    st.title("📋 Réservations")
    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)

    # pastilles plateformes
    st.markdown("### Plateformes")
    if palette:
        badges = " &nbsp;&nbsp;".join([
            f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{get_palette().get(p,"#999")};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{p}'
            for p in sorted(palette.keys())
        ])
        st.markdown(badges, unsafe_allow_html=True)

    df = ensure_schema(df)

    if filtre_paye == "Payé":
        df = df[df["paye"] == True].copy()
    elif filtre_paye == "Non payé":
        df = df[df["paye"] == False].copy()

    if show_kpi:
        kpi_chips(df)
    if enable_search:
        df = search_box(df)

    # Éditeur en lecture (on permet seulement cases paye/sms si colonnes présentes)
    core = df.copy()
    core["__rowid"] = core.index
    for c in ["date_arrivee","date_depart"]:
        if c in core.columns:
            core[c] = core[c].apply(format_date_str)

    cols_pref = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commission","frais_cb","prix_net",
        "menage","taxe_sejour","base","AAAA","MM","__rowid"
    ]
    cols_show = [c for c in cols_pref if c in core.columns]

    edited = st.data_editor(
        core[cols_show],
        use_container_width=True,
        hide_index=True,
        column_config={
            "paye": st.column_config.CheckboxColumn("Payé"),
            "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
            "__rowid": st.column_config.Column("id", disabled=True, width="small"),
        }
    )

    c1, _ = st.columns([1,3])
    if c1.button("💾 Enregistrer les cases cochées"):
        df2 = df.copy()
        for _, r in edited.iterrows():
            ridx = int(r["__rowid"])
            if "paye" in df2.columns:
                df2.at[ridx, "paye"] = bool(r.get("paye", False))
            if "sms_envoye" in df2.columns:
                df2.at[ridx, "sms_envoye"] = bool(r.get("sms_envoye", False))
        sauvegarder_donnees(df2)
        st.success("✅ Statuts Payé / SMS mis à jour.")
        st.rerun()

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    st.caption("Saisie compacte (libellés inline)")
    palette = get_palette()

    def inline_input(label, widget_fn, key=None, **widget_kwargs):
        col1, col2 = st.columns([1,2])
        with col1: st.markdown(f"**{label}**")
        with col2: return widget_fn(label, key=key, label_visibility="collapsed", **widget_kwargs)

    paye = inline_input("Payé", st.checkbox, key="add_paye", value=False)
    nom = inline_input("Nom", st.text_input, key="add_nom", value="")
    sms_envoye = inline_input("SMS envoyé", st.checkbox, key="add_sms", value=False)
    tel = inline_input("Téléphone (+33...)", st.text_input, key="add_tel", value="")
    pf_options = sorted(palette.keys())
    pf_index = pf_options.index("Booking") if "Booking" in pf_options else 0
    plateforme = inline_input("Plateforme", st.selectbox, key="add_pf",
                              options=pf_options, index=pf_index)

    arrivee = inline_input("Arrivée", st.date_input, key="add_arrivee", value=date.today())
    min_dep = arrivee + timedelta(days=1)
    depart  = inline_input("Départ",  st.date_input, key="add_depart",
                           value=min_dep, min_value=min_dep)

    brut = inline_input("Prix brut (€)", st.number_input, key="add_brut", min_value=0.0, step=1.0, format="%.2f")
    commission = inline_input("Commissions (€)", st.number_input, key="add_comm", min_value=0.0, step=1.0, format="%.2f")
    frais_cb = inline_input("Frais CB (€)", st.number_input, key="add_cb", min_value=0.0, step=1.0, format="%.2f")

    net_calc = max(float(brut) - float(commission) - float(frais_cb), 0.0)
    inline_input("Prix net (calculé)", st.number_input, key="add_net",
                 value=round(net_calc,2), step=0.01, format="%.2f", disabled=True)

    menage = inline_input("Ménage (€)", st.number_input, key="add_menage", min_value=0.0, step=1.0, format="%.2f")
    taxe  = inline_input("Taxes séjour (€)", st.number_input, key="add_taxes", min_value=0.0, step=1.0, format="%.2f")

    base_calc = max(net_calc - float(menage) - float(taxe), 0.0)

    if st.button("Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        ligne = {
            "paye": bool(paye),
            "nom_client": (nom or "").strip(),
            "sms_envoye": bool(sms_envoye),
            "plateforme": plateforme,
            "telephone": str(tel).strip(),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": float(brut),
            "commission": float(commission),
            "frais_cb": float(frais_cb),
            "prix_net": round(net_calc, 2),
            "menage": float(menage),
            "taxe_sejour": float(taxe),
            "base": round(base_calc, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month,
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = ensure_schema(df)
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

    t0, t1, t2 = st.columns(3)
    paye = t0.checkbox("Payé", value=bool(df.at[i, "paye"]))
    nom = t1.text_input("Nom", df.at[i, "nom_client"])
    sms_envoye = t2.checkbox("SMS envoyé", value=bool(df.at[i, "sms_envoye"]))

    col = st.columns(2)
    tel = col[0].text_input("Téléphone", str(df.at[i, "telephone"]))
    palette = get_palette()
    options_pf = sorted(palette.keys())
    cur_pf = df.at[i,"plateforme"]
    pf_index = options_pf.index(cur_pf) if cur_pf in options_pf else 0
    plateforme = col[1].selectbox("Plateforme", options_pf, index=pf_index)

    arrivee = st.date_input("Arrivée", df.at[i,"date_arrivee"] if pd.notna(df.at[i,"date_arrivee"]) else date.today())
    depart  = st.date_input("Départ",  df.at[i,"date_depart"] if pd.notna(df.at[i,"date_depart"]) else arrivee + timedelta(days=1), min_value=arrivee+timedelta(days=1))

    c1, c2, c3 = st.columns(3)
    brut = c1.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"]) if pd.notna(df.at[i,"prix_brut"]) else 0.0, step=1.0, format="%.2f")
    commission = c2.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i,"commission"]) if pd.notna(df.at[i,"commission"]) else 0.0, step=1.0, format="%.2f")
    frais_cb = c3.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"]) if pd.notna(df.at[i,"frais_cb"]) else 0.0, step=1.0, format="%.2f")

    net_calc = max(brut - commission - frais_cb, 0.0)

    d1, d2 = st.columns(2)
    menage = d1.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i,"menage"]) if pd.notna(df.at[i,"menage"]) else 0.0, step=1.0, format="%.2f")
    taxe  = d2.number_input("Taxes séjour (€)", min_value=0.0, value=float(df.at[i,"taxe_sejour"]) if pd.notna(df.at[i,"taxe_sejour"]) else 0.0, step=1.0, format="%.2f")
    base_calc = max(net_calc - menage - taxe, 0.0)

    c_save, c_del = st.columns(2)
    if c_save.button("💾 Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[i,"paye"] = bool(paye)
        df.at[i,"nom_client"] = nom.strip()
        df.at[i,"sms_envoye"] = bool(sms_envoye)
        df.at[i,"plateforme"] = plateforme
        df.at[i,"telephone"]  = str(tel).strip()
        df.at[i,"date_arrivee"] = arrivee
        df.at[i,"date_depart"]  = depart
        df.at[i,"prix_brut"] = float(brut)
        df.at[i,"commission"] = float(commission)
        df.at[i,"frais_cb"] = float(frais_cb)
        df.at[i,"prix_net"]  = round(net_calc, 2)
        df.at[i,"menage"] = float(menage)
        df.at[i,"taxe_sejour"] = float(taxe)
        df.at[i,"base"] = round(base_calc, 2)
        df.at[i,"nuitees"]   = (depart - arrivee).days
        df.at[i,"AAAA"]      = arrivee.year
        df.at[i,"MM"]        = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df)
        st.success("✅ Modifié")
        st.rerun()

    if c_del.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("Supprimé.")
        st.rerun()

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport (détaillé)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.info("Aucune année disponible.")
        return

    c1, c2, c3 = st.columns(3)
    annee = c1.selectbox("Année", annees, index=len(annees)-1, key="rapport_annee")
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = c2.selectbox("Plateforme", pf_opt, key="rapport_pf")
    mois_opt = ["Tous"] + [f"{i:02d}" for i in range(1,13)]
    mois_label = c3.selectbox("Mois", mois_opt, key="rapport_mois")

    data = df[df["AAAA"] == int(annee)].copy()
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]
    if mois_label != "Tous":
        data = data[data["MM"] == int(mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    detail = data.copy()
    for c in ["date_arrivee","date_depart"]:
        detail[c] = detail[c].apply(format_date_str)
    by = [c for c in ["date_arrivee","nom_client"] if c in detail.columns]
    if by:
        detail = detail.sort_values(by=by, na_position="last").reset_index(drop=True)

    cols_detail = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commission","frais_cb","prix_net","menage","taxe_sejour","base"
    ]
    cols_detail = [c for c in cols_detail if c in detail.columns]
    st.dataframe(detail[cols_detail], use_container_width=True)

    # petit graphe mensuel
    stats = (
        data.groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 base=("base","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
            .sort_values(["MM","plateforme"])
    )

    if not stats.empty:
        pvt = stats.pivot(index="MM", columns="plateforme", values="prix_brut").fillna(0).sort_index()
        pvt.index = [f"{int(m):02d}" for m in pvt.index]
        st.markdown("**Revenus bruts par mois / plateforme**")
        st.bar_chart(pvt)

def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    c1, c2 = st.columns(2)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", annees, index=len(annees)-1) if annees else None
    mois  = c2.selectbox("Mois", ["Tous"] + [f"{i:02d}" for i in range(1,13)])

    data = df.copy()
    if annee:
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]

    if data.empty:
        st.info("Aucune donnée pour cette période.")
        return

    data["prix_brut/nuit"] = data.apply(lambda r: round((r["prix_brut"]/r["nuitees"]) if r.get("nuitees") else 0,2), axis=1)
    data["prix_net/nuit"]  = data.apply(lambda r: round((r["prix_net"]/r["nuitees"])  if r.get("nuitees") else 0,2), axis=1)

    show = data.copy()
    for c in ["date_arrivee","date_depart"]:
        show[c] = show[c].apply(format_date_str)

    cols = ["paye","nom_client","sms_envoye","plateforme","telephone","date_arrivee","date_depart",
            "nuitees","prix_brut","commission","frais_cb","prix_net","menage","taxe_sejour","base","prix_brut/nuit","prix_net/nuit"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

def df_to_ics(df: pd.DataFrame, cal_name: str = "Villa Tobias – Réservations") -> str:
    if df.empty:
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Villa Tobias//Reservations//FR\r\n"
            f"X-WR-CALNAME:{cal_name}\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "METHOD:PUBLISH\r\n"
            "END:VCALENDAR\r\n"
        )
    lines = []
    A = lines.append
    A("BEGIN:VCALENDAR")
    A("VERSION:2.0")
    A("PRODID:-//Villa Tobias//Reservations//FR")
    A(f"X-WR-CALNAME:{cal_name}")
    A("CALSCALE:GREGORIAN")
    A("METHOD:PUBLISH")

    for _, row in df.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (pd.notna(d1) and pd.notna(d2)):
            continue
        d1s = pd.to_datetime(d1).strftime("%Y%m%d")
        d2s = pd.to_datetime(d2).strftime("%Y%m%d")
        pf = str(row.get("plateforme") or "")
        nom = str(row.get("nom_client") or "")
        tel = str(row.get("telephone") or "")
        summary = " - ".join([x for x in [pf, nom, tel] if x])

        A("BEGIN:VEVENT")
        A(f"DTSTART;VALUE=DATE:{d1s}")
        A(f"DTEND;VALUE=DATE:{d2s}")
        A(f"SUMMARY:{summary}")
        A("END:VEVENT")
    A("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

def vue_export_ics(df: pd.DataFrame):
    st.title("📤 Export ICS (Google Agenda – Import manuel)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée à exporter.")