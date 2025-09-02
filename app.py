# app.py — Villa Tobias (VERSION OPTIMISÉE)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
from urllib.parse import quote
import logging
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from pathlib import Path

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
@dataclass
class Config:
    FICHIER: str = "reservations.xlsx"
    PALETTE_SHEET: str = "Plateformes"
    DATA_SHEET: str = "Sheet1"
    DEFAULT_PALETTE: Dict[str, str] = None
    
    def __post_init__(self):
        if self.DEFAULT_PALETTE is None:
            self.DEFAULT_PALETTE = {
                "Booking": "#1e90ff",
                "Airbnb":  "#e74c3c", 
                "Autre":   "#f59e0b",
            }

config = Config()

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(
    page_title="📖 Réservations Villa Tobias", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================  SESSION STATE INITIALIZATION  ==============================
def init_session_state():
    """Initialize session state variables"""
    default_values = {
        "uploader_key_restore": 0,
        "did_clear_cache": False,
        "palette": config.DEFAULT_PALETTE.copy()
    }
    
    for key, value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ==============================  UTILITY FUNCTIONS  ==============================
class DataUtils:
    @staticmethod
    def clean_hex(color: str) -> str:
        """Clean and validate hex color code"""
        if not isinstance(color, str):
            return "#999999"
        
        color = color.strip()
        if not color.startswith("#"):
            color = "#" + color
            
        if len(color) in [4, 7] and all(c in '0123456789abcdefABCDEF' for c in color[1:]):
            return color
        return "#999999"

    @staticmethod
    def to_date_only(value) -> Optional[date]:
        """Convert value to date object"""
        if pd.isna(value) or value is None:
            return None
        try:
            return pd.to_datetime(value).date()
        except Exception as e:
            logger.warning(f"Date conversion failed: {e}")
            return None

    @staticmethod
    def format_date_str(d) -> str:
        """Format date to string"""
        return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

    @staticmethod
    def normalize_tel(value) -> str:
        """Normalize telephone number"""
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return ""
        
        tel_str = str(value).strip().replace(" ", "")
        if tel_str.endswith(".0"):
            tel_str = tel_str[:-2]
        return tel_str

class PaletteManager:
    """Manage color palette for platforms"""
    
    @staticmethod
    def get_palette() -> Dict[str, str]:
        """Get current palette from session state"""
        if "palette" not in st.session_state:
            st.session_state.palette = config.DEFAULT_PALETTE.copy()
        
        # Clean palette
        clean_palette = {}
        for key, value in st.session_state.palette.items():
            if isinstance(key, str) and isinstance(value, str):
                clean_palette[key.strip()] = DataUtils.clean_hex(value)
        
        st.session_state.palette = clean_palette
        return st.session_state.palette

    @staticmethod
    def set_palette(palette: Dict[str, str]):
        """Set new palette"""
        st.session_state.palette = {
            str(k).strip(): DataUtils.clean_hex(str(v)) 
            for k, v in palette.items() if k and v
        }

    @staticmethod
    def platform_badge(name: str, palette: Dict[str, str]) -> str:
        """Generate HTML badge for platform"""
        color = palette.get(name, "#999999")
        return (
            f'<span style="display:inline-block;width:0.9em;height:0.9em;'
            f'background:{color};border-radius:3px;margin-right:6px;'
            f'vertical-align:-0.1em;"></span>{name}'
        )

# ==============================  DATA SCHEMA & PROCESSING  ==============================
class DataProcessor:
    BASE_COLS = [
        "paye", "nom_client", "sms_envoye", "plateforme", "telephone",
        "date_arrivee", "date_depart", "nuitees", "prix_brut", "commissions", 
        "frais_cb", "prix_net", "menage", "taxes_sejour", "base", 
        "charges", "%", "AAAA", "MM", "ical_uid"
    ]

    @classmethod
    def ensure_schema(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure DataFrame has correct schema and calculate derived fields"""
        if df is None or df.empty:
            df = pd.DataFrame()
        
        df = df.copy()

        # Add missing columns
        for col in cls.BASE_COLS:
            if col not in df.columns:
                df[col] = np.nan

        # Process boolean columns
        for bool_col in ["paye", "sms_envoye"]:
            df[bool_col] = df[bool_col].fillna(False).astype(bool)

        # Process date columns
        for date_col in ["date_arrivee", "date_depart"]:
            df[date_col] = df[date_col].apply(DataUtils.to_date_only)

        # Process telephone
        df["telephone"] = df["telephone"].apply(DataUtils.normalize_tel)

        # Process numeric columns
        numeric_cols = [
            "prix_brut", "commissions", "frais_cb", "prix_net", 
            "menage", "taxes_sejour", "base", "charges", "%", "nuitees"
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Calculate derived fields
        df = cls._calculate_derived_fields(df)
        
        # Order columns
        return cls._order_columns(df)

    @staticmethod
    def _calculate_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate derived fields like nuitees, prix_net, etc."""
        # Calculate nuitees
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

        # Calculate year and month
        df["AAAA"] = df["date_arrivee"].apply(
            lambda d: d.year if isinstance(d, date) else np.nan
        ).astype("Int64")
        df["MM"] = df["date_arrivee"].apply(
            lambda d: d.month if isinstance(d, date) else np.nan
        ).astype("Int64")

        # Fill string columns
        df["nom_client"] = df["nom_client"].fillna("")
        df["plateforme"] = df["plateforme"].fillna("Autre")
        df["ical_uid"] = df["ical_uid"].fillna("")

        # Fill numeric columns and calculate
        for col in ["prix_brut", "commissions", "frais_cb", "menage", "taxes_sejour"]:
            df[col] = df[col].fillna(0.0)

        # Calculate derived amounts
        df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
        df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
        df["charges"] = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
        
        # Calculate percentage
        with pd.option_context("mode.use_inf_as_na", True):
            df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

        # Round numeric columns
        numeric_cols = [
            "prix_brut", "commissions", "frais_cb", "prix_net", 
            "menage", "taxes_sejour", "base", "charges", "%"
        ]
        for col in numeric_cols:
            df[col] = df[col].round(2)

        return df

    @classmethod
    def _order_columns(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Order columns according to BASE_COLS"""
        ordered_cols = [c for c in cls.BASE_COLS if c in df.columns]
        rest_cols = [c for c in df.columns if c not in ordered_cols]
        return df[ordered_cols + rest_cols]

    @staticmethod
    def is_total_row(row: pd.Series) -> bool:
        """Check if row is a total row"""
        name_is_total = str(row.get("nom_client", "")).strip().lower() == "total"
        pf_is_total = str(row.get("plateforme", "")).strip().lower() == "total"
        
        d1 = row.get("date_arrivee")
        d2 = row.get("date_depart")
        no_dates = not isinstance(d1, date) and not isinstance(d2, date)
        
        has_money = any(
            pd.notna(row.get(c)) and float(row.get(c) or 0) != 0
            for c in ["prix_brut", "prix_net", "base", "charges"]
        )
        
        return name_is_total or pf_is_total or (no_dates and has_money)

    @classmethod
    def split_totals(cls, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Split DataFrame into data and totals"""
        if df is None or df.empty:
            return df, df
        
        mask = df.apply(cls.is_total_row, axis=1)
        return df[~mask].copy(), df[mask].copy()

    @staticmethod
    def sort_core(df: pd.DataFrame) -> pd.DataFrame:
        """Sort core data by date and name"""
        if df is None or df.empty:
            return df
        
        by_cols = [c for c in ["date_arrivee", "nom_client"] if c in df.columns]
        if by_cols:
            return df.sort_values(by=by_cols, na_position="last").reset_index(drop=True)
        return df

# ==============================  FILE I/O OPERATIONS  ==============================
class FileManager:
    """Handle Excel file operations"""
    
    @staticmethod
    @st.cache_data(show_spinner=False)
    def _read_workbook(path: str, mtime: float) -> Tuple[pd.DataFrame, Dict[str, str]]:
        """Read Excel workbook and return reservations and palette"""
        try:
            with pd.ExcelFile(path, engine="openpyxl") as xf:
                # Read reservations
                sheet_name = config.DATA_SHEET if config.DATA_SHEET in xf.sheet_names else xf.sheet_names[0]
                df = pd.read_excel(
                    xf, 
                    sheet_name=sheet_name, 
                    engine="openpyxl",
                    converters={"telephone": DataUtils.normalize_tel}
                )
                df = DataProcessor.ensure_schema(df)

                # Read palette
                palette = config.DEFAULT_PALETTE.copy()
                if config.PALETTE_SHEET in xf.sheet_names:
                    palette_df = pd.read_excel(xf, sheet_name=config.PALETTE_SHEET, engine="openpyxl")
                    if {"plateforme", "couleur"}.issubset(set(palette_df.columns)):
                        for _, row in palette_df.iterrows():
                            name = str(row["plateforme"]).strip()
                            color = DataUtils.clean_hex(str(row["couleur"]))
                            if name:
                                palette[name] = color
                
                return df, palette
                
        except Exception as e:
            logger.error(f"Error reading Excel file: {e}")
            st.error(f"Erreur de lecture Excel : {e}")
            return DataProcessor.ensure_schema(pd.DataFrame()), config.DEFAULT_PALETTE.copy()

    @classmethod
    def load_data(cls) -> Tuple[pd.DataFrame, Dict[str, str]]:
        """Load data from Excel file"""
        if not os.path.exists(config.FICHIER):
            return DataProcessor.ensure_schema(pd.DataFrame()), PaletteManager.get_palette()
        
        mtime = os.path.getmtime(config.FICHIER)
        df, palette = cls._read_workbook(config.FICHIER, mtime)
        PaletteManager.set_palette(palette)
        return df, palette

    @staticmethod
    def _force_tel_text_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
        """Force telephone column to text format"""
        try:
            worksheet = writer.sheets.get(sheet_name)
            if worksheet is None or "telephone" not in df_to_save.columns:
                return
            
            col_idx = df_to_save.columns.get_loc("telephone") + 1
            for row in worksheet.iter_rows(
                min_row=2, max_row=worksheet.max_row, 
                min_col=col_idx, max_col=col_idx
            ):
                row[0].number_format = '@'
        except Exception as e:
            logger.warning(f"Could not format telephone column: {e}")

    @classmethod
    def save_data(cls, df: pd.DataFrame, palette: Optional[Dict[str, str]] = None):
        """Save data to Excel file"""
        try:
            df = DataProcessor.ensure_schema(df)
            core, totals = DataProcessor.split_totals(df)
            core = DataProcessor.sort_core(core)
            output_df = pd.concat([core, totals], ignore_index=True)

            with pd.ExcelWriter(config.FICHIER, engine="openpyxl") as writer:
                output_df.to_excel(writer, index=False, sheet_name=config.DATA_SHEET)
                cls._force_tel_text_openpyxl(writer, output_df, config.DATA_SHEET)
                
                # Save palette if provided
                if palette is not None:
                    palette_df = pd.DataFrame([
                        {"plateforme": k, "couleur": v} 
                        for k, v in sorted(palette.items())
                    ])
                    palette_df.to_excel(writer, index=False, sheet_name=config.PALETTE_SHEET)
            
            st.cache_data.clear()
            st.success("💾 Sauvegarde Excel effectuée.")
            
        except Exception as e:
            logger.error(f"Save failed: {e}")
            st.error(f"Échec de sauvegarde Excel : {e}")

# ==============================  UI COMPONENTS  ==============================
class UIComponents:
    """Reusable UI components"""
    
    @staticmethod
    def kpi_chips(df: pd.DataFrame):
        """Display KPI chips"""
        core, _ = DataProcessor.split_totals(df)
        if core.empty:
            return
        
        # Calculate metrics
        metrics = {
            'brut': core["prix_brut"].sum(),
            'commissions': core["commissions"].sum(),
            'frais_cb': core["frais_cb"].sum(),
        }
        
        metrics.update({
            'charges': metrics['commissions'] + metrics['frais_cb'],
            'net': core["prix_net"].sum(),
            'base': core["base"].sum(),
            'nuits': core["nuitees"].sum(),
        })
        
        metrics['pct'] = (metrics['charges'] / metrics['brut'] * 100) if metrics['brut'] else 0
        metrics['pm_nuit'] = (metrics['brut'] / metrics['nuits']) if metrics['nuits'] else 0

        html = f"""
        <style>
        .chips-wrap {{ display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px 0; }}
        .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12); 
                 border: 1px solid rgba(127,127,127,0.25); font-size:0.9rem; }}
        .chip b {{ display:block; margin-bottom:3px; font-size:0.85rem; opacity:0.8; }}
        .chip .v {{ font-weight:600; }}
        </style>
        <div class="chips-wrap">
          <div class="chip"><b>Total Brut</b><div class="v">{metrics['brut']:,.2f} €</div></div>
          <div class="chip"><b>Total Net</b><div class="v">{metrics['net']:,.2f} €</div></div>
          <div class="chip"><b>Total Base</b><div class="v">{metrics['base']:,.2f} €</div></div>
          <div class="chip"><b>Total Charges</b><div class="v">{metrics['charges']:,.2f} €</div></div>
          <div class="chip"><b>Nuitées</b><div class="v">{int(metrics['nuits']) if pd.notna(metrics['nuits']) else 0}</div></div>
          <div class="chip"><b>Commission moy.</b><div class="v">{metrics['pct']:.2f} %</div></div>
          <div class="chip"><b>Prix moyen/nuit</b><div class="v">{metrics['pm_nuit']:,.2f} €</div></div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)

    @staticmethod
    def search_box(df: pd.DataFrame) -> pd.DataFrame:
        """Search functionality for reservations"""
        query = st.text_input(
            "🔎 Recherche (nom, plateforme, téléphone…)", 
            "", 
            placeholder="Tapez pour rechercher..."
        )
        
        if not query:
            return df
        
        query_lower = query.strip().lower()
        
        def match_text(value):
            text = "" if pd.isna(value) else str(value)
            return query_lower in text.lower()
        
        mask = (
            df["nom_client"].apply(match_text) |
            df["plateforme"].apply(match_text) |
            df["telephone"].apply(match_text)
        )
        
        return df[mask].copy()

# ==============================  MAIN APPLICATION  ==============================
def vue_reservations(df: pd.DataFrame):
    """Main reservations view"""
    st.title("📋 Réservations")
    palette = PaletteManager.get_palette()

    # Filters and options
    with st.expander("🎛️ Options d'affichage", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        filtre_paye = col1.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
        show_kpi = col2.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = col3.checkbox("Activer la recherche", value=True)

    # Platform badges
    if palette:
        st.markdown("### Plateformes")
        badges = " &nbsp;&nbsp;".join([
            PaletteManager.platform_badge(pf, palette) 
            for pf in sorted(palette.keys())
        ])
        st.markdown(badges, unsafe_allow_html=True)

    # Apply filters
    df = DataProcessor.ensure_schema(df)
    if filtre_paye == "Payé":
        df = df[df["paye"] == True].copy()
    elif filtre_paye == "Non payé":
        df = df[df["paye"] == False].copy()

    # Show KPIs and search
    if show_kpi:
        UIComponents.kpi_chips(df)
    if enable_search:
        df = UIComponents.search_box(df)

    # Split data
    core, totals = DataProcessor.split_totals(df)
    core = DataProcessor.sort_core(core)

    # Prepare editable data
    core_edit = core.copy()
    core_edit["__rowid"] = core_edit.index
    core_edit["date_arrivee"] = core_edit["date_arrivee"].apply(DataUtils.format_date_str)
    core_edit["date_depart"] = core_edit["date_depart"].apply(DataUtils.format_date_str)

    # Column configuration for data editor
    column_config = {
        "paye": st.column_config.CheckboxColumn("Payé"),
        "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
        "__rowid": st.column_config.Column("id", help="Interne", disabled=True, width="small"),
    }
    
    # Disable editing for calculated fields
    disabled_cols = [
        "date_arrivee", "date_depart", "nom_client", "plateforme", "telephone",
        "nuitees", "prix_brut", "commissions", "frais_cb", "prix_net",
        "menage", "taxes_sejour", "base", "charges", "%", "AAAA", "MM"
    ]
    
    for col in disabled_cols:
        if col in core_edit.columns:
            column_config[col] = st.column_config.Column(col, disabled=True)

    # Display editable table
    cols_order = [
        "paye", "nom_client", "sms_envoye", "plateforme", "telephone",
        "date_arrivee", "date_depart", "nuitees", "prix_brut", "commissions", 
        "frais_cb", "prix_net", "menage", "taxes_sejour", "base", "charges", 
        "%", "AAAA", "MM", "__rowid"
    ]
    cols_show = [c for c in cols_order if c in core_edit.columns]

    edited = st.data_editor(
        core_edit[cols_show],
        use_container_width=True,
        hide_index=True,
        column_config=column_config
    )

    # Save button
    col1, _ = st.columns([1, 3])
    if col1.button("💾 Enregistrer les cases cochées"):
        for _, row in edited.iterrows():
            ridx = int(row["__rowid"])
            core.at[ridx, "paye"] = bool(row.get("paye", False))
            core.at[ridx, "sms_envoye"] = bool(row.get("sms_envoye", False))
        
        new_df = pd.concat([core, totals], ignore_index=True)
        FileManager.save_data(new_df, PaletteManager.get_palette())
        st.success("✅ Statuts Payé / SMS mis à jour.")
        st.rerun()

    # Show totals if any
    if not totals.empty:
        st.caption("Lignes de totaux (non éditables) :")
        show_totals = totals.copy()
        for col in ["date_arrivee", "date_depart"]:
            show_totals[col] = show_totals[col].apply(DataUtils.format_date_str)
        
        cols_tot = [c for c in cols_order[:-1] if c in show_totals.columns]  # Exclude __rowid
        st.dataframe(show_totals[cols_tot], use_container_width=True)

def main():
    """Main application function"""
    try:
        # Sidebar file operations
        st.sidebar.title("📁 Fichier")
        df_tmp, _ = FileManager.load_data()
        
        # Download button
        try:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                DataProcessor.ensure_schema(df_tmp).to_excel(writer, index=False, sheet_name=config.DATA_SHEET)
                palette_df = pd.DataFrame([
                    {"plateforme": k, "couleur": v} 
                    for k, v in sorted(PaletteManager.get_palette().items())
                ])
                palette_df.to_excel(writer, index=False, sheet_name=config.PALETTE_SHEET)
            
            st.sidebar.download_button(
                "💾 Télécharger reservations.xlsx",
                data=buf.getvalue(),
                file_name="reservations.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            logger.error(f"Download preparation failed: {e}")
            st.sidebar.error("Export XLSX indisponible")

        # Navigation
        st.sidebar.title("🧭 Navigation")
        onglet = st.sidebar.radio(
            "Aller à",
            ["📋 Réservations", "➕ Ajouter", "✏️ Modifier / Supprimer",
             "📅 Calendrier", "📊 Rapport", "👥 Liste clients", 
             "📤 Export ICS", "✉️ SMS", "🎨 Plateformes"]
        )

        # Load data and show selected view
        df, _ = FileManager.load_data()
        
        if onglet == "📋 Réservations":
            vue_reservations(df)
        else:
            st.info(f"Vue '{onglet}' en cours de développement dans cette version optimisée.")
            
    except Exception as e:
        logger.error(f"Application error: {e}")
        st.error(f"Une erreur est survenue : {e}")

if __name__ == "__main__":
    main()