# modules/baja.py
import streamlit as st
import time
from datetime import datetime
from core.data_manager import cargar_datos, guardar_datos, registrar_log
from modules.busqueda import buscador_socios, refrescar_busqueda


def _mostrar_ficha_detalle(socio: dict):
    st.markdown(
        f"""
        <div style="
            background-color:#141414;
            padding:15px;
            border-radius:10px;
            border:1px solid #ff4b4b;
            margin-top:10px;">
            <strong>Nombre completo:</strong> {socio.get('Nombre','')} {socio.get('Apellidos','')}<br>
            <strong>DNI:</strong> {socio.get('DNI','')}<br>
            <strong>Teléfono:</strong> {socio.get('Teléfono','')}<br>
            <strong>Email:</strong> {socio.get('Email','')}<br>
            <strong>Plan contratado:</strong> {socio.get('Plan contratado','')}<br>
            <strong>Estado actual:</strong> {socio.get('Estado','')}<br>
            <strong>Estado de pago:</strong> {socio.get('Estado de pago','')}<br>
            <strong>Fecha último pago:</strong> {socio.get('Fecha último pago','') or '—'}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _mostrar_progreso(duracion=0.01):
    barra = st.progress(0)
    for i in range(100):
        time.sleep(duracion)
        barra.progress(i + 1)


def mostrar_baja():
    st.subheader("🔍 Buscar socio")

    socios = cargar_datos()
    rol = (st.session_state.get("role") or "").lower()

    if "baja_socio_en_proceso" not in st.session_state:
        st.session_state.baja_socio_en_proceso = None

    evento = buscador_socios(socios, rol_usuario=rol)

    if evento:
        socio = evento["socio"]
        if evento["accion"] == "dar_baja":
            st.session_state.baja_socio_en_proceso = socio
        elif evento["accion"] == "ver_ficha":
            st.info("📄 Ficha del socio seleccionado:")
            _mostrar_ficha_detalle(socio)
        elif evento["accion"] == "marcar_pagado":
            fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            socios.loc[socios["DNI"] == socio["DNI"], "Estado de pago"] = "Pagado"
            socios.loc[socios["DNI"] == socio["DNI"], "Fecha último pago"] = fecha_actual
            guardar_datos(socios)
            registrar_log(
                usuario=st.session_state.get("username", "desconocido"),
                accion="pagado",
                dni=socio["DNI"],
                detalle="Estado cambiado de No pagado → Pagado",
            )
            st.success(f"💰 Pago registrado para {socio['Nombre']} {socio['Apellidos']}.")
            st.toast("Pago registrado.")
            _mostrar_progreso(0.01)
            socios_actualizados = cargar_datos()
            refrescar_busqueda(socios_actualizados)
            st.rerun()
        elif evento["accion"] == "marcar_no_pagado":
            socios.loc[socios["DNI"] == socio["DNI"], "Estado de pago"] = "No pagado"
            guardar_datos(socios)
            registrar_log(
                usuario=st.session_state.get("username", "desconocido"),
                accion="no pagado",
                dni=socio["DNI"],
                detalle="Estado cambiado de Pagado → No pagado",
            )
            st.info(f"🔁 Estado revertido a 'No pagado' para {socio['Nombre']} {socio['Apellidos']}.")
            st.toast("Estado de pago cambiado a No pagado.")
            _mostrar_progreso(0.01)
            socios_actualizados = cargar_datos()
            refrescar_busqueda(socios_actualizados)
            st.rerun()
        elif evento["accion"] == "dar_alta":
            socios.loc[socios["DNI"] == socio["DNI"], "Estado"] = "Activo"
            guardar_datos(socios)
            registrar_log(
                usuario=st.session_state.get("username", "desconocido"),
                accion="alta",
                dni=socio["DNI"],
                detalle="Estado cambiado a Activo (reactivado)",
            )
            st.success(f"🟢 {socio['Nombre']} ha sido dado de alta.")
            st.toast("Socio reactivado correctamente.")
            _mostrar_progreso(0.01)
            socios_actualizados = cargar_datos()
            refrescar_busqueda(socios_actualizados)
            st.rerun()

    if not st.session_state.get("busqueda_resultados"):
        st.session_state.baja_socio_en_proceso = None

    socio_en_proceso = st.session_state.get("baja_socio_en_proceso")
    if not socio_en_proceso:
        st.info("Selecciona un socio y pulsa «Dar de baja» para continuar.")
        return

    st.warning(
        f"⚠️ ¿Confirmas dar de baja a **{socio_en_proceso.get('Nombre','')} {socio_en_proceso.get('Apellidos','')} "
        f"({socio_en_proceso.get('DNI','')})**?"
    )

    col1, col2 = st.columns(2)
    if col1.button("Cancelar"):
        st.session_state.baja_socio_en_proceso = None
        st.rerun()

    if col2.button("Confirmar baja ✅"):
        socios.loc[socios["DNI"] == socio_en_proceso["DNI"], "Estado"] = "Baja"
        guardar_datos(socios)
        registrar_log(
            usuario=st.session_state.get("username", "desconocido"),
            accion="baja",
            dni=socio_en_proceso["DNI"],
            detalle="Estado cambiado a Baja (baja manual)",
        )
        st.success(f"✅ {socio_en_proceso.get('Nombre','')} ha sido dado de baja.")
        st.toast("Baja registrada correctamente.")
        _mostrar_progreso(0.015)

        st.session_state.baja_socio_en_proceso = None
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.username = None
        st.session_state.full_name = None
        st.rerun()
