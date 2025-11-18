import streamlit as st
from core.data_manager import cargar_datos

def mostrar_socios():
    st.subheader("📋 Listado de socios")

    socios = cargar_datos()
    filtro = st.selectbox("Mostrar:", ["Todos", "Activos", "De baja", "Pagado", "No pagado"])

    if filtro == "Activos":
        st.dataframe(socios[socios["Estado"] == "Activo"])
    elif filtro == "De baja":
        st.dataframe(socios[socios["Estado"] == "Baja"])
    elif filtro == "Pagado":
        st.dataframe(socios[socios["Estado de pago"] == "Pagado"])
    elif filtro == "No pagado":
        st.dataframe(socios[socios["Estado de pago"] == "No pagado"])
    else:
        st.dataframe(socios)
