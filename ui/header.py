# ui/header.py
import streamlit as st
from PIL import Image
import base64
from io import BytesIO
from pathlib import Path

def mostrar_encabezado():
    """Muestra el logo y el título principal de la app."""
    logo_path = Path(__file__).resolve().parents[1] / "assets" / "agboxeo.png"
    logo = Image.open(logo_path)

    buffer = BytesIO()
    logo.save(buffer, format="PNG")
    encoded_logo = base64.b64encode(buffer.getvalue()).decode()

    st.markdown(
        f"""
        <div class="header-container">
            <img src="data:image/png;base64,{encoded_logo}" class="header-logo">
            <span class="header-title">AG BOXEO</span>
        </div>
        """,
        unsafe_allow_html=True
    )
