import streamlit as st
from typing import List, Dict, Optional
from core.data_manager import obtener_historial_logs

CRITERIOS = {
    "Nombre": "Nombre",
    "Apellidos": "Apellidos",
    "DNI": "DNI",
    "Teléfono": "Teléfono",
    "Email": "Email",
}

ACCIONES_POR_ROL = {
    "admin": [
        ("dar_baja", "Dar de baja 🔴"),
        ("marcar_pagado", "Marcar pagado ✅"),
        ("marcar_no_pagado", "Marcar NO pagado ❌"),
        ("dar_alta", "Dar de alta 🟢"),
        ("ver_ficha", "Ver ficha 🗂️"),
    ],
    "empleado": [
        ("dar_baja", "Dar de baja 🔴"),
        ("ver_ficha", "Ver ficha 🗂️"),
    ],
}

BUSQUEDA_STATE_KEYS = [
    "busqueda_resultados",
    "busqueda_valor",
    "busqueda_criterio",
    "busqueda_last_view",
]


def _badge(texto: str, color: str) -> str:
    return f"<span style='padding:4px 8px; border-radius:999px; background:{color}; color:white; font-size:0.85em;'>{texto}</span>"


def _filtrar_socios(df, columna: str, valor: str):
    if df.empty or not valor:
        return df.iloc[0:0]
    return df[df[columna].astype(str).str.contains(valor, case=False, na=False)]


def _clear_state(keep_owner: bool = True):
    owner = st.session_state.get("busqueda_owner") if keep_owner else None
    for key in BUSQUEDA_STATE_KEYS:
        st.session_state.pop(key, None)
    if keep_owner and owner is not None:
        st.session_state["busqueda_owner"] = owner
    else:
        st.session_state.pop("busqueda_owner", None)


def _ensure_defaults():
    st.session_state.setdefault("busqueda_criterio", list(CRITERIOS.keys())[0])
    st.session_state.setdefault("busqueda_valor", "")
    st.session_state.setdefault("busqueda_resultados", [])
    st.session_state.setdefault("busqueda_last_view", st.session_state.get("menu_accion"))


def refrescar_busqueda(df):
    """
    Recalcula los resultados del buscador con el criterio actual.
    """
    _ensure_defaults()
    valor = st.session_state.get("busqueda_valor", "").strip()
    criterio = st.session_state.get("busqueda_criterio", list(CRITERIOS.keys())[0])

    if valor:
        columna = CRITERIOS[criterio]
        resultados = _filtrar_socios(df, columna, valor)
        st.session_state.busqueda_resultados = resultados.to_dict("records")
    else:
        st.session_state.busqueda_resultados = []


def buscador_socios(
    df,
    rol_usuario: str,
    acciones_permitidas: Optional[List[str]] = None,
    modo: str = "default",
) -> Optional[Dict]:
    """
    Renderiza el buscador unificado y devuelve un diccionario con la acción seleccionada.
    Ejemplo de retorno:
        {"accion": "dar_baja", "socio": {...}}
    """
    current_user = st.session_state.get("username")
    current_view = st.session_state.get("menu_accion")

    if st.session_state.get("busqueda_owner") != current_user:
        _clear_state(keep_owner=False)
        st.session_state["busqueda_owner"] = current_user

    if st.session_state.get("busqueda_last_view") != current_view:
        _clear_state(keep_owner=True)
        st.session_state["busqueda_owner"] = current_user
        st.session_state["busqueda_last_view"] = current_view

    _ensure_defaults()

    col_volver, col_limpiar, col_spacer = st.columns([1.5, 2, 5])
    if col_volver.button("⬅️ Volver atrás", use_container_width=True):
        opciones = st.session_state.get("menu_opciones")
        if opciones:
            st.session_state["menu_accion_target"] = opciones[0]
        _clear_state(keep_owner=False)
        st.rerun()

    if col_limpiar.button("🧹 Limpiar búsqueda", use_container_width=True):
        _clear_state(keep_owner=False)
        st.session_state["busqueda_criterio"] = list(CRITERIOS.keys())[0]
        st.session_state["busqueda_valor"] = ""
        st.session_state.pop("editar_socio", None)
        st.session_state.pop("baja_socio_en_proceso", None)
        st.rerun()

    if df.empty:
        st.info("No hay socios registrados todavía.")
        return None

    with st.form("form_busqueda_unificada"):
        criterio = st.selectbox("Buscar por:", list(CRITERIOS.keys()), key="busqueda_criterio")
        valor = st.text_input("Introduce el valor a buscar", key="busqueda_valor").strip()
        buscar = st.form_submit_button("Buscar socio 🔍")

    if buscar:
        if not valor:
            st.warning("⚠️ Introduce un valor de búsqueda.")
            st.session_state.busqueda_resultados = []
        else:
            columna = CRITERIOS[criterio]
            resultados = _filtrar_socios(df, columna, valor)
            if resultados.empty:
                st.warning("⚠️ No se encontraron socios con ese criterio.")
                st.session_state.busqueda_resultados = []
            else:
                st.success(f"✅ {len(resultados)} socio(s) encontrados.")
                st.session_state.busqueda_resultados = resultados.to_dict("records")

    resultados = st.session_state.busqueda_resultados
    if not resultados:
        st.info("Introduce un valor y pulsa «Buscar socio» para ver resultados.")
        return None

    acciones = ACCIONES_POR_ROL.get((rol_usuario or "").lower(), [])
    if acciones_permitidas is not None:
        acciones = [a for a in acciones if a[0] in acciones_permitidas]
    if modo == "editar":
        acciones = [("ver_ficha", "Editar datos")]

    if not acciones:
        st.info("No hay acciones disponibles para tu rol en este contexto.")
        return None

    for socio in resultados:
        estado_pago = (socio.get("Estado de pago") or "No pagado").strip()
        badge_pago = _badge(
            "Pagado" if estado_pago.lower() == "pagado" else "No pagado",
            "#27ae60" if estado_pago.lower() == "pagado" else "#c0392b",
        )
        badge_estado = _badge(
            socio.get("Estado", "Desconocido"),
            "#27ae60" if socio.get("Estado", "").lower() == "activo" else "#c0392b",
        )
        estado_actual = (socio.get("Estado", "") or "").strip().lower()
        acciones_socio = []
        pago_lower = estado_pago.lower()
        for accion_id, etiqueta in acciones:
            if estado_actual == "baja":
                if accion_id in ("dar_baja", "marcar_pagado", "marcar_no_pagado"):
                    continue
                if accion_id in ("dar_alta", "ver_ficha"):
                    acciones_socio.append((accion_id, etiqueta))
            else:
                if accion_id == "dar_alta":
                    continue
                if accion_id == "marcar_pagado" and pago_lower == "pagado":
                    continue
                if accion_id == "marcar_no_pagado" and pago_lower == "no pagado":
                    continue
                acciones_socio.append((accion_id, etiqueta))

        if not acciones_socio:
            continue

        plan_actual = socio.get("Plan contratado", "")
        precio = socio.get("Precio", "")

        st.markdown(
            f"""
            <div style="
                background-color:#1f1f1f;
                padding:15px;
                border-radius:10px;
                border:1px solid #ff4b4b;
                margin-bottom:12px;">
                <strong>{socio.get('Nombre','')} {socio.get('Apellidos','')}</strong><br>
                <small>DNI: {socio.get('DNI','')} | Teléfono: {socio.get('Teléfono','')} | Email: {socio.get('Email','')}</small><br>
                <small>Disciplina: {socio.get('Disciplina','')} | Plan: {plan_actual}{(' (' + precio + ')') if precio else ''}</small><br>
                <small>Estado socio: {badge_estado} | Estado de pago: {badge_pago}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

        cols = st.columns(len(acciones_socio))
        for (accion_id, etiqueta), col in zip(acciones_socio, cols):
            if col.button(etiqueta, key=f"{accion_id}_{socio.get('DNI','')}"):
                return {"accion": accion_id, "socio": socio}

        historial = obtener_historial_logs(socio.get("DNI", ""))
        if historial:
            st.markdown("<div style='margin-top:-8px; font-weight:600;'>Historial reciente</div>", unsafe_allow_html=True)
            for evento in historial:
                st.markdown(
                    f"""
                    <div style="
                        background-color:#111;
                        padding:10px;
                        border-radius:6px;
                        border:1px solid #333;
                        margin-bottom:6px;
                        font-size:0.9rem;">
                        <strong>{evento.get('Fecha','')}</strong> — {evento.get('Acción','')} · {evento.get('Usuario','')}<br>
                        <span style="opacity:0.8;">{evento.get('Detalle','')}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    return None
