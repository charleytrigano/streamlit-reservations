import os
import io
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

# -------------------
# Constantes
# -------------------
EXCEL_FILE = "reservations.xlsx"
LOGO_FILE = "logo.png"

# Palette par défaut
PLATFORM_COLORS_DEFAULT = {
    "Booking": "#1e90ff",
    "Airbnb": "#ff5a5f",
    "Abritel": "#9b59b6",
    "Autre": "#f59e0b"
}

# Palette en mémoire (modifiable par l’utilisateur)
if "palette" not in st.session_state:
    st.session_state["palette"] = PLATFORM_COLORS_DEFAULT.copy()


# -------------------
# Fonctions utilitaires
# -------------------
def load_data(file_path=EXCEL_FILE):
    if not os.path.exists(file_path):
        return pd.DataFrame(columns=[
            "plateforme", "reservation", "client", "sms", "paye",
            "date_arrivee", "date_depart", "nuitees", "tarif",
            "commission", "frais_cb", "net"
        ])
    return pd.read_excel(file_path)

def save_data(df, file_path=EXCEL_FILE):
    df.to_excel(file_path, index=False)

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    required_cols = [
        "plateforme", "reservation", "client", "sms", "paye",
        "date_arrivee", "date_depart", "nuitees", "tarif",
        "commission", "frais_cb", "net"
    ]
    for col in required_cols:
        if col not in df.columns:
            if col in ["sms", "paye"]:
                df[col] = False
            else:
                df[col] = np.nan
    return df[required_cols]

def add_platform_to_palette(name: str, color: str):
    st.session_state["palette"][name] = color

def get_color_for_platform(name: str) -> str:
    return st.session_state["palette"].get(name, "#9ca3af")

def platform_badge(name: str) -> str:
    color = get_color_for_platform(name)
    return f"""<span style="color:{color}; font-weight:bold;">⬤ {name}</span>"""

# =========================
# PARTIE 2/3 — VUES UI
# =========================

# ---------- Petits helpers d’UI ----------
def kpi_row(df: pd.DataFrame):
    if df.empty:
        return
    total_brut = pd.to_numeric(df.get("tarif"), errors="coerce").fillna(0).sum()
    total_comm = pd.to_numeric(df.get("commission"), errors="coerce").fillna(0).sum()
    total_cb   = pd.to_numeric(df.get("frais_cb"), errors="coerce").fillna(0).sum()
    total_net  = pd.to_numeric(df.get("net"), errors="coerce").fillna(0).sum()
    total_nuits = pd.to_numeric(df.get("nuitees"), errors="coerce").fillna(0).sum()

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total brut", f"{total_brut:,.2f} €".replace(",", " "))
    col2.metric("Total net", f"{total_net:,.2f} €".replace(",", " "))
    col3.metric("Commissions", f"{total_comm:,.2f} €".replace(",", " "))
    col4.metric("Frais CB", f"{total_cb:,.2f} €".replace(",", " "))
    col5.metric("Nuitées", int(total_nuits))

def apply_paid_filter(df: pd.DataFrame, choice: str) -> pd.DataFrame:
    if choice == "Tous":
        return df
    if choice == "Payé":
        return df[df["paye"] == True]
    if choice == "Non payé":
        # inclut False et NaN (considéré comme non payé)
        return df[df["paye"] != True]
    return df

def search_filter(df: pd.DataFrame, q: str) -> pd.DataFrame:
    if not q:
        return df
    ql = q.strip().lower()
    def m(s):
        s = "" if pd.isna(s) else str(s)
        return ql in s.lower()
    mask = (
        df["client"].apply(m) |
        df["plateforme"].apply(m) |
        df["reservation"].apply(m)
    )
    return df[mask]

def recompute_nights_and_net(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # nuitees
    try:
        d1 = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date
        d2 = pd.to_datetime(df["date_depart"], errors="coerce").dt.date
        df["nuitees"] = (pd.to_datetime(d2) - pd.to_datetime(d1)).dt.days.clip(lower=0)
    except Exception:
        pass
    # net
    for col in ["tarif", "commission", "frais_cb"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["net"] = (df["tarif"] - df["commission"] - df["frais_cb"]).clip(lower=0)
    return df

# ---------- VUE: Réservations ----------
def view_reservations():
    st.title("📋 Réservations")

    # Bloc 1 : Options (expander indépendant)
    with st.expander("🎛️ Options d’affichage", expanded=True):
        c1, c2 = st.columns([1.2, 2])
        paid_choice = c1.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
        q = c2.text_input("Recherche (client, plateforme, référence)")

    # Bloc 2 : Gestion de palette (expander indépendant, pas imbriqué)
    with st.expander("🎨 Plateformes (couleurs)"):
        st.caption("Ajoutez/éditez des plateformes ci-dessous (couleur utilisée dans le calendrier).")
        # Liste actuelle
        if st.session_state["palette"]:
            st.markdown("**Plateformes existantes**")
            for pf, col in st.session_state["palette"].items():
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    st.markdown(platform_badge(pf), unsafe_allow_html=True)
                with c2:
                    new_col = st.color_picker("Couleur", value=col, key=f"col_{pf}")
                with c3:
                    if new_col != col:
                        st.session_state["palette"][pf] = new_col
                        st.toast(f"Couleur mise à jour pour {pf}")
        st.divider()
        # Ajout rapide
        colA, colB, colC = st.columns([2, 1, 1])
        new_name = colA.text_input("Nouvelle plateforme (ex: Expedia)", key="new_pf_name")
        new_color = colB.color_picker("Couleur", value="#10b981", key="new_pf_color")
        if colC.button("➕ Ajouter", type="primary"):
            name = new_name.strip()
            if not name:
                st.warning("Indiquez un nom de plateforme.")
            else:
                add_platform_to_palette(name, new_color)
                st.success(f"Plateforme ajoutée : {name}")
                st.experimental_rerun()

    # Charger données
    df = ensure_schema(load_data())
    df = recompute_nights_and_net(df)
    # Appliquer filtres
    df = apply_paid_filter(df, paid_choice)
    df = search_filter(df, q)

    # KPIs
    kpi_row(df)

    # Éditeur : seules colonnes 'paye' et 'sms' éditables
    editable = df.copy()
    # vue formatée
    for col in ["date_arrivee", "date_depart"]:
        editable[col] = pd.to_datetime(editable[col], errors="coerce").dt.strftime("%Y-%m-%d")
    st.markdown("### Tableau")
    edited = st.data_editor(
        editable,
        use_container_width=True,
        hide_index=True,
        column_config={
            "paye": st.column_config.CheckboxColumn("Payé"),
            "sms": st.column_config.CheckboxColumn("SMS"),
            "plateforme": st.column_config.TextColumn("Plateforme", disabled=True),
            "reservation": st.column_config.TextColumn("Référence", disabled=True),
            "client": st.column_config.TextColumn("Client", disabled=True),
            "date_arrivee": st.column_config.TextColumn("Arrivée", disabled=True),
            "date_depart": st.column_config.TextColumn("Départ", disabled=True),
            "nuitees": st.column_config.NumberColumn("Nuitées", disabled=True),
            "tarif": st.column_config.NumberColumn("Brut (€)", disabled=True, format="%.2f"),
            "commission": st.column_config.NumberColumn("Commissions (€)", disabled=True, format="%.2f"),
            "frais_cb": st.column_config.NumberColumn("Frais CB (€)", disabled=True, format="%.2f"),
            "net": st.column_config.NumberColumn("Net (€)", disabled=True, format="%.2f"),
        }
    )
    c1, c2 = st.columns([1, 3])
    if c1.button("💾 Enregistrer Payé/SMS"):
        # on répercute seulement paye & sms sur le df original (pas filtré)
        base = ensure_schema(load_data())
        base = recompute_nights_and_net(base)
        # alignement par (plateforme, reservation, client, date_arrivee) pour être robuste
        key_cols = ["plateforme", "reservation", "client", "date_arrivee"]
        # reparse date_arrivee dans edited
        edited_sync = edited.copy()
        edited_sync["date_arrivee"] = pd.to_datetime(edited_sync["date_arrivee"], errors="coerce").dt.normalize()
        base_sync = base.copy()
        base_sync["date_arrivee"] = pd.to_datetime(base_sync["date_arrivee"], errors="coerce").dt.normalize()

        # merge pour récupérer les flags paye/sms
        flags = edited_sync[key_cols + ["paye", "sms"]].drop_duplicates()
        merged = base_sync.merge(flags, on=key_cols, how="left", suffixes=("", "_new"))
        for col in ["paye", "sms"]:
            pick = np.where(merged[f"{col}_new"].notna(), merged[f"{col}_new"], merged[col])
            merged[col] = pick.astype(bool)
            merged.drop(columns=[f"{col}_new"], inplace=True)
        # Sauvegarde
        save_data(merged)
        st.success("✅ Statuts mis à jour.")
        st.experimental_rerun()

    # Info export
    st.info(
        "Pour exporter le fichier, utilisez **Fichier ▸ Sauvegarde xlsx** dans la barre latérale."
    )

# ---------- VUE: Calendrier coloré ----------
def view_calendar():
    st.title("📅 Calendrier (type agenda, couleurs par plateforme)")
    df = ensure_schema(load_data())
    if df.empty:
        st.info("Aucune réservation.")
        return

    # Sélecteurs
    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["date_depart"]  = pd.to_datetime(df["date_depart"],  errors="coerce")
    years = sorted(df["date_arrivee"].dropna().dt.year.unique().tolist() or [datetime.today().year])
    c1, c2 = st.columns(2)
    year = c1.selectbox("Année", years, index=len(years)-1)
    month = c2.selectbox("Mois", list(range(1,13)), index=(datetime.today().month-1))

    # Génère la grille (lundi -> dimanche)
    first_day = datetime(year, month, 1)
    start_weekday = (first_day.weekday())  # 0 = lundi
    # nombre de jours du mois
    if month == 12:
        next_month = datetime(year+1, 1, 1)
    else:
        next_month = datetime(year, month+1, 1)
    days_in_month = (next_month - first_day).days

    # Préparer événements journaliers
    # Un jour est "occupé" si date_arrivee <= j < date_depart
    day_events = {d: [] for d in range(1, days_in_month+1)}
    for _, r in df.iterrows():
        d1 = r["date_arrivee"]
        d2 = r["date_depart"]
        if pd.isna(d1) or pd.isna(d2):
            continue
        # normaliser
        d1 = d1.normalize()
        d2 = d2.normalize()
        p  = str(r.get("plateforme") or "")
        c  = str(r.get("client") or "")
        color = get_color_for_platform(p)
        # boucler sur les jours couverts
        cur = d1
        while cur < d2:
            if cur.year == year and cur.month == month:
                j = cur.day
                day_events[j].append((p, c, color))
            cur += timedelta(days=1)

    # Générer la table HTML
    headers = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    html = []
    html.append("""
    <style>
      .cal { border-collapse: collapse; width: 100%; table-layout: fixed; }
      .cal th, .cal td { border:1px solid #e5e7eb; vertical-align: top; padding:6px; }
      .cal th { background:#f8fafc; text-align:center; font-weight:600; }
      .daynum { font-weight:700; margin-bottom:4px; display:block; }
      .evt { display:block; margin:2px 0; padding:3px 6px; border-radius:6px; background: #f3f4f6; }
      .evt .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; vertical-align:middle; }
    </style>
    """)

    html.append("<table class='cal'>")
    html.append("<thead><tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead>")
    html.append("<tbody>")

    # construire semaine par semaine
    day_cursor = 1
    cur_weekday = start_weekday  # 0..6
    # première ligne
    html.append("<tr>")
    for _ in range(cur_weekday):
        html.append("<td></td>")
    while day_cursor <= days_in_month:
        # cellule du jour
        events_html = []
        for (p, c, color) in day_events.get(day_cursor, []):
            events_html.append(
                f"<span class='evt'>"
                f"<span class='dot' style='background:{color}'></span>"
                f"{p} — {c}"
                f"</span>"
            )
        html.append(
            f"<td><span class='daynum'>{day_cursor}</span>" +
            "".join(events_html) +
            "</td>"
        )
        cur_weekday += 1
        day_cursor += 1
        if cur_weekday == 7 and day_cursor <= days_in_month:
            html.append("</tr><tr>")
            cur_weekday = 0
    # fin de ligne
    if cur_weekday != 0:
        for _ in range(7 - cur_weekday):
            html.append("<td></td>")
    html.append("</tr>")
    html.append("</tbody></table>")

    st.markdown("".join(html), unsafe_allow_html=True)

    # Légende des plateformes
    st.markdown("#### Légende")
    legend = " &nbsp; ".join(
        f"<span><span class='dot' style='background:{col}; display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px;'></span>{pf}</span>"
        for pf, col in st.session_state["palette"].items()
    )
    st.markdown(legend, unsafe_allow_html=True)

# =========================
# PARTIE 3/3 — SIDEBAR & MAIN
# =========================

from io import BytesIO

# ---------- Barre latérale : fichier ----------
def sidebar_file_section():
    st.sidebar.header("📁 Fichier")

    # Télécharger le xlsx courant
    df_now = ensure_schema(load_data())
    buf = BytesIO()
    try:
        df_now.to_excel(buf, index=False, engine="openpyxl")
        data_xlsx = buf.getvalue()
        disabled = False
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = b""
        disabled = True

    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=disabled,
        help="Télécharge une sauvegarde Excel de vos réservations."
    )

    # Restaurer un xlsx
    up = st.sidebar.file_uploader("📤 Restaurer depuis un xlsx", type=["xlsx"])
    if up is not None:
        try:
            df_new = pd.read_excel(up)
            df_new = ensure_schema(df_new)
            save_data(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.experimental_rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

# ---------- Barre latérale : maintenance ----------
def sidebar_maintenance():
    st.sidebar.markdown("---")
    st.sidebar.subheader("🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.sidebar.success("Cache vidé, relance…")
        st.experimental_rerun()

# ---------- Navigation ----------
def sidebar_nav() -> str:
    st.sidebar.header("🧭 Navigation")
    return st.sidebar.radio(
        "Aller à",
        ["📋 Réservations", "📅 Calendrier"],
        index=0,
        label_visibility="collapsed"
    )

# ---------- MAIN ----------
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

    # Palette par défaut si absente (définie en PARTIE 1)
    if "palette" not in st.session_state:
        st.session_state["palette"] = DEFAULT_PALETTE.copy()

    # Barre latérale
    sidebar_file_section()
    sidebar_maintenance()
    page = sidebar_nav()

    # Pages
    if page == "📋 Réservations":
        view_reservations()
    elif page == "📅 Calendrier":
        view_calendar()

if __name__ == "__main__":
    main()