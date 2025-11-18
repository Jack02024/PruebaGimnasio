import streamlit as st
from modules.baja import mostrar_baja


def mostrar_control_pagos():
    """
    Mantiene compatibilidad con el menú anterior.
    Toda la gestión ahora se realiza desde el buscador unificado.
    """
    st.info("ℹ️ La gestión de pagos se realiza desde la vista «🔍 Buscar socio».")
    mostrar_baja()
