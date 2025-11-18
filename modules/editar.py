import streamlit as st
import re
from datetime import date
from core.data_manager import cargar_datos, guardar_datos, registrar_log
from modules.busqueda import buscador_socios, refrescar_busqueda
from modules.alta import (
    PLANES_INFANTIL,
    PLANES_ADULTO,
    DISCIPLINAS_ADULTO,
    _calcular_edad,
)


def _validar_formulario(nombre, apellidos, telefono, email, fecha_nac, plan_tuple, infantil, disciplina):
    errores = []
    if not nombre.strip() or not apellidos.strip():
        errores.append("Nombre y apellidos son obligatorios.")
    if not re.match(r"^[679][0-9]{8}$", telefono.strip()):
        errores.append("El teléfono debe tener 9 dígitos y empezar por 6, 7 o 9.")
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email.strip()):
        errores.append("El correo electrónico no tiene un formato válido.")
    if not fecha_nac:
        errores.append("Debes indicar una fecha de nacimiento válida.")
    else:
        edad = _calcular_edad(fecha_nac)
        if edad < 8 or edad > 100:
            errores.append("La edad debe estar entre 8 y 100 años.")
        elif infantil and plan_tuple and plan_tuple[0] not in [p[0] for p in PLANES_INFANTIL]:
            errores.append("Un socio infantil solo puede tener planes infantiles.")
        elif not infantil and disciplina in DISCIPLINAS_ADULTO:
            planes_validos = [p[0] for p in PLANES_ADULTO.get(disciplina, [])]
            if plan_tuple and plan_tuple[0] not in planes_validos:
                errores.append("Plan no válido para la disciplina seleccionada.")
    if not plan_tuple:
        errores.append("Selecciona un plan válido.")
    return errores


def _obtener_planes(disciplina: str, infantil: bool):
    if infantil:
        return PLANES_INFANTIL
    if disciplina in PLANES_ADULTO:
        return PLANES_ADULTO[disciplina]
    return []


def mostrar_editar():
    st.subheader("✏️ Editar socio")

    if st.session_state.get("role") != "admin":
        st.warning("No tienes permisos para editar socios.")
        return

    socios = cargar_datos()

    if "editar_socio" not in st.session_state:
        st.session_state.editar_socio = None

    st.markdown(
        """
        <div style="display:flex; gap:10px; margin-bottom:15px; flex-wrap:wrap;">
            <div style="background:#1f1f1f; padding:10px 14px; border-radius:999px; border:1px solid #ff4b4b;">Paso 1 · Buscar socio</div>
            <div style="background:#1f1f1f; padding:10px 14px; border-radius:999px; border:1px solid #ff4b4b;">Paso 2 · Editar datos</div>
            <div style="background:#1f1f1f; padding:10px 14px; border-radius:999px; border:1px solid #ff4b4b;">Paso 3 · Confirmar cambios</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    evento = buscador_socios(
        socios,
        rol_usuario="admin",
        acciones_permitidas=["ver_ficha"],
        modo="editar",
    )

    if evento and evento["accion"] == "ver_ficha":
        st.session_state.editar_socio = evento["socio"]

    socio = st.session_state.get("editar_socio")
    if not socio:
        st.info("Selecciona un socio con «Ver ficha» para editar sus datos.")
        return

    disciplina = socio.get("Disciplina", "Sin definir")
    estado = socio.get("Estado", "Desconocido")
    fecha_nac_str = socio.get("Fecha nacimiento") or socio.get("Fecha de nacimiento")
    fecha_guardada = None
    edad = None
    if fecha_nac_str:
        try:
            fecha_guardada = date.fromisoformat(fecha_nac_str)
            edad = _calcular_edad(fecha_guardada)
        except Exception:
            fecha_guardada = None
    if not fecha_guardada:
        fecha_guardada = date(2005, 1, 1)
    infantil = edad is not None and edad <= 14

    st.markdown(
        f"""
        <div style="
            background-color:#101010;
            border:1px solid #ff4b4b;
            padding:15px;
            border-radius:10px;
            margin-bottom:15px;
        ">
            <strong>{socio.get('Nombre','')} {socio.get('Apellidos','')}</strong><br>
            DNI: {socio.get('DNI','')} · Tel: {socio.get('Teléfono','')} · Email: {socio.get('Email','')}<br>
            Disciplina: {disciplina} · Plan: {socio.get('Plan contratado', socio.get('Tipo de plan',''))} ({socio.get('Precio','')})<br>
            Estado: {estado} · Estado de pago: {socio.get('Estado de pago','')}<br>
            Fecha nacimiento: {fecha_guardada.isoformat()} {(f'(Edad: {edad} años)' if edad is not None else '')}
        </div>
        """,
        unsafe_allow_html=True,
    )

    planes_disponibles = _obtener_planes(disciplina, infantil)
    if not planes_disponibles:
        planes_disponibles = [(socio.get("Plan contratado", "Plan sin definir"), socio.get("Precio", ""))]

    plan_actual_nombre = socio.get("Plan contratado") or socio.get("Tipo de plan") or planes_disponibles[0][0]
    try:
        plan_index = [p[0] for p in planes_disponibles].index(plan_actual_nombre)
    except ValueError:
        plan_index = 0

    opciones_planes = [f"{p[0]} — {p[1]}" for p in planes_disponibles]

    with st.form("form_editar_socio"):
        nombre = st.text_input("Nombre", value=socio.get("Nombre", ""))
        apellidos = st.text_input("Apellidos", value=socio.get("Apellidos", ""))
        telefono = st.text_input("Teléfono", value=socio.get("Teléfono", ""))
        email = st.text_input("Email", value=socio.get("Email", ""))
        st.text_input("Disciplina", value=disciplina, disabled=True)
        plan_seleccion = st.selectbox("Plan contratado", opciones_planes, index=plan_index)
        fecha_nacimiento_input = st.date_input(
            "Fecha de nacimiento",
            value=fecha_guardada,
            max_value=date.today(),
        )

        col1, col2 = st.columns(2)
        guardar = col1.form_submit_button("Guardar cambios ✅")
        cancelar = col2.form_submit_button("Cancelar")

    if cancelar:
        st.session_state.editar_socio = None
        st.rerun()

    if guardar:
        plan_idx = opciones_planes.index(plan_seleccion)
        plan_nombre, plan_precio = planes_disponibles[plan_idx]
        errores = _validar_formulario(
            nombre,
            apellidos,
            telefono,
            email,
            fecha_nacimiento_input,
            (plan_nombre, plan_precio),
            infantil,
            disciplina,
        )
        if errores:
            for err in errores:
                st.error(err)
            return

        df_actualizado = cargar_datos()
        indices = df_actualizado.index[df_actualizado["DNI"] == socio["DNI"]].tolist()
        if len(indices) != 1:
            st.error("No se pudo localizar el registro del socio en la base de datos.")
            return

        idx = indices[0]
        campos = {
            "Nombre": nombre.strip(),
            "Apellidos": apellidos.strip(),
            "Teléfono": telefono.strip(),
            "Email": email.strip().lower(),
            "Tipo de plan": plan_nombre,
            "Plan contratado": plan_nombre,
            "Precio": plan_precio,
            "Fecha nacimiento": fecha_nacimiento_input.isoformat(),
        }

        usuario = st.session_state.get("username", "desconocido")
        cambios_detalle = []
        for campo, nuevo_valor in campos.items():
            valor_anterior = df_actualizado.at[idx, campo] if campo in df_actualizado.columns else ""
            if str(valor_anterior) != str(nuevo_valor):
                df_actualizado.at[idx, campo] = nuevo_valor
                cambios_detalle.append(f"{campo}: {valor_anterior} → {nuevo_valor}")

        if cambios_detalle:
            registrar_log(
                usuario=usuario,
                accion="editar",
                dni=socio["DNI"],
                detalle="; ".join(cambios_detalle),
            )

        guardar_datos(df_actualizado)
        refrescar_busqueda(df_actualizado)
        st.success("Los datos han sido actualizados correctamente.")
        st.toast("Cambios guardados.")
        st.session_state.editar_socio = None
        st.rerun()
