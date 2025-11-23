import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from core.data_manager import cargar_datos, guardar_datos, registrar_log
from pathlib import Path
import base64
import re  # 🔹 Para validaciones con expresiones regulares
from io import BytesIO
from PIL import Image
from streamlit_drawable_canvas import st_canvas
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as reportlab_canvas
from reportlab.lib.pagesizes import A4

BASE_PDF = Path("assets/Consentimiento Fines Promocionales_NICOVA.pdf")
FIRMAS_DIR = Path("firmas")
FIRMAS_DIR.mkdir(exist_ok=True)

PLANES_INFANTIL = [
    ("1 día/semana", "25€"),
    ("2 días/semana", "45€"),
]

DISCIPLINAS_ADULTO = [
    "Boxeo / Defensa Personal",
    "Krav Maga / BJJ",
    "Entrenamiento personal / Funcional",
]

PLANES_ADULTO = {
    "Boxeo / Defensa Personal": [
        ("1 día/semana", "30€/mes"),
        ("2 días/semana", "50€/mes"),
        ("3 días/semana", "65€/mes"),
        ("Mes ilimitado", "75€/mes"),
        ("Trimestre ilimitado", "210€/trimestre"),
        ("Bono 10 clases", "80€ (caduca 3 meses)"),
    ],
    "Krav Maga / BJJ": [
        ("1 día/semana", "30€/mes"),
        ("2 días/semana", "50€/mes"),
    ],
    "Entrenamiento personal / Funcional": [
        ("Sesión suelta 1h", "40€"),
        ("Bono 10 sesiones", "340€"),
        ("Bono 20 sesiones", "620€"),
    ],
}


def _calcular_edad(fecha_nac: date) -> int:
    hoy = date.today()
    return hoy.year - fecha_nac.year - (
        (hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day)
    )


def _reset_plan_state():
    st.session_state.plan_disciplina = None
    st.session_state.precio_plan = None


def _reset_disciplina_state():
    st.session_state.disciplina = None
    _reset_plan_state()


def _reset_fecha_state():
    st.session_state.fecha_nacimiento = None
    st.session_state.edad = None
    st.session_state.tipo_cliente = None
    _reset_disciplina_state()


def _reset_firma_state(reset_canvas: bool = False):
    st.session_state["firma_realizada"] = False
    st.session_state["firma_imagen"] = None
    if reset_canvas:
        st.session_state["canvas_firma_key"] = st.session_state.get("canvas_firma_key", 0) + 1


def _guardar_firma_imagen(image_array, destino: Path) -> None:
    imagen = Image.fromarray(image_array.astype("uint8"))
    imagen.save(destino, format="PNG")


def _generar_pdf_firmado(pdf_base: Path, firma_path: Path, destino: Path, nombre: str, apellidos: str, dni: str, timestamp: str) -> None:
    reader = PdfReader(str(pdf_base))
    writer = PdfWriter()
    total_paginas = len(reader.pages)

    for index, page in enumerate(reader.pages):
        if index == total_paginas - 1:
            packet = BytesIO()
            can = reportlab_canvas.Canvas(packet, pagesize=A4)

            firma_img = Image.open(firma_path)
            firma_ancho = 180
            ratio = firma_img.height / firma_img.width if firma_img.width else 1
            firma_alto = firma_ancho * ratio

            x = 350
            y = 120

            can.drawImage(str(firma_path), x, y, width=firma_ancho, height=firma_alto, mask="auto")
            can.setFont("Helvetica", 10)
            lineas = [
                f"Firmado electrónicamente por {nombre} {apellidos}",
                f"DNI: {dni}",
                f"Fecha y hora: {timestamp}",
            ]
            texto_y = y - 15
            for linea in lineas:
                can.drawString(x, texto_y, linea)
                texto_y -= 12

            can.save()
            packet.seek(0)
            overlay = PdfReader(packet)
            page.merge_page(overlay.pages[0])

        writer.add_page(page)

    with open(destino, "wb") as salida:
        writer.write(salida)

def mostrar_alta():
    st.subheader("📄 Ficha Inscripción - Escuela AG BOXEO")

    # --- Formato visual de campos ---
    st.markdown(
        """
        <style>
        /* DNI siempre en mayúsculas */
        input[aria-label="DNI"] {
            text-transform: uppercase !important;
        }

        /* Email siempre en minúsculas */
        input[aria-label="Email"] {
            text-transform: lowercase !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    for key, default in [
        ("disciplina", None),
        ("plan_disciplina", None),
        ("precio_plan", None),
        ("fecha_nacimiento", None),
        ("edad", None),
        ("tipo_cliente", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    socios = cargar_datos()

    # --- PASO 0: Fecha de nacimiento ---
    if not st.session_state.fecha_nacimiento:
        st.info("Introduce la fecha de nacimiento para determinar el plan adecuado.")
        fecha_default = st.session_state.get("fecha_temp", date(2005, 1, 1))
        fecha_nac = st.date_input(
            "Fecha de nacimiento",
            value=fecha_default,
            max_value=date.today(),
            key="input_fecha_nac",
        )
        st.session_state.fecha_temp = fecha_nac
        if st.button("Continuar ➡️", key="continuar_edad"):
            edad = _calcular_edad(fecha_nac)
            if edad < 8:
                st.error("Edad mínima: 8 años.")
            else:
                st.session_state.fecha_nacimiento = fecha_nac.isoformat()
                st.session_state.edad = edad
                st.session_state.tipo_cliente = "infantil" if edad <= 14 else "adulto"
                _reset_disciplina_state()
                if st.session_state.tipo_cliente == "infantil":
                    st.session_state.disciplina = "Infantil"
                st.session_state.pop("fecha_temp", None)
                st.rerun()
        st.stop()

    st.success(
        f"Edad detectada: {st.session_state.edad} años "
        f"({'Infantil' if st.session_state.tipo_cliente == 'infantil' else 'Adulto'})"
    )
    if st.button("Cambiar fecha de nacimiento", key="btn_cambiar_fecha"):
        _reset_fecha_state()
        st.rerun()

    # --- PASO 1: Disciplina (solo adultos) ---
    if st.session_state.tipo_cliente == "adulto" and not st.session_state.disciplina:
        st.info("Selecciona la disciplina del socio adulto.")
        opciones = ["Selecciona una opción"] + DISCIPLINAS_ADULTO
        seleccion = st.selectbox("Disciplina", opciones, key="disciplina_temp")
        col_a, col_b = st.columns([1, 1])
        if col_a.button("⬅️ Cambiar edad", key="volver_edad_adulto"):
            _reset_fecha_state()
            st.rerun()
        if col_b.button("Continuar ➡️", key="continuar_disciplina_adulto"):
            if seleccion == "Selecciona una opción":
                st.warning("Debes seleccionar una disciplina.")
            else:
                st.session_state.disciplina = seleccion
                _reset_plan_state()
                st.session_state.pop("disciplina_temp", None)
                st.rerun()
        st.stop()

    # --- PASO 1b: Selección de plan ---
    if not st.session_state.plan_disciplina:
        if st.session_state.tipo_cliente == "infantil":
            planes = PLANES_INFANTIL
            st.info("Planes disponibles para alumnos infantiles (8-14 años).")
        else:
            planes = PLANES_ADULTO.get(st.session_state.disciplina, [])
            st.success(f"Disciplina seleccionada: {st.session_state.disciplina}")

        opciones_planes = ["Selecciona un plan"] + [f"{p[0]} — {p[1]}" for p in planes]
        seleccion_plan = st.selectbox("Plan disponible", opciones_planes, key="plan_temp")

        col_plan_edad, col_plan_disciplina, col_plan_continuar = st.columns([1, 1, 1])
        if col_plan_edad.button("Cambiar edad", key="plan_cambiar_edad"):
            _reset_fecha_state()
            st.rerun()
        if (
            st.session_state.tipo_cliente == "adulto"
            and col_plan_disciplina.button("Cambiar disciplina", key="plan_cambiar_disciplina")
        ):
            _reset_disciplina_state()
            st.rerun()
        if col_plan_continuar.button("Continuar ➡️", key="plan_confirmar"):
            if seleccion_plan == "Selecciona un plan":
                st.warning("Debes seleccionar un plan para continuar.")
            else:
                idx = opciones_planes.index(seleccion_plan) - 1
                plan_nombre, plan_precio = planes[idx]
                st.session_state.plan_disciplina = plan_nombre
                st.session_state.precio_plan = plan_precio
                st.session_state.pop("plan_temp", None)
                st.rerun()
        st.stop()

    if "firma_realizada" not in st.session_state:
        _reset_firma_state()
    if "canvas_firma_key" not in st.session_state:
        st.session_state.canvas_firma_key = 0

    # --- Paso 1: Formulario inicial ---
    if "paso" not in st.session_state:
        st.session_state.paso = 1

    if st.session_state.paso == 1:
        resumen = (
            f"Fecha de nacimiento: **{st.session_state.fecha_nacimiento}** · "
            f"Edad: **{st.session_state.edad} años** "
            f"({'Infantil' if st.session_state.tipo_cliente == 'infantil' else 'Adulto'}) · "
            f"Disciplina: **{st.session_state.disciplina}** · "
            f"Plan: **{st.session_state.plan_disciplina} ({st.session_state.precio_plan})**"
        )
        st.info(resumen)
        col_cambiar_plan, col_cambiar_fecha = st.columns([1, 1])
        if col_cambiar_plan.button("Cambiar disciplina o plan", key="cambiar_disciplina_plan"):
            if st.session_state.tipo_cliente == "adulto":
                _reset_disciplina_state()
            else:
                _reset_plan_state()
            st.rerun()
        if col_cambiar_fecha.button("Cambiar fecha de nacimiento", key="cambiar_fecha_resumen"):
            _reset_fecha_state()
            st.rerun()

        with st.form("form_datos"):
            nombre = st.text_input("Nombre")
            apellidos = st.text_input("Apellidos")
            dni = st.text_input("DNI")
            telefono = st.text_input("Teléfono")
            email = st.text_input("Email")
            continuar = st.form_submit_button("Continuar ➡️")

        if continuar:
            # --- 🔍 Validaciones ---
            errores = []

            if not nombre or not apellidos or not dni or not telefono or not email:
                errores.append("Todos los campos son obligatorios.")
            elif not re.match(r'^[0-9]{8}[A-Z]$', dni.strip().upper()):
                errores.append("El DNI debe tener 8 números seguidos de una letra mayúscula (Ejemplo: 12345678Z).")
            elif not re.match(r'^[679]{1}[0-9]{8}$', telefono.strip().replace(" ", "")):
                errores.append("El teléfono debe tener 9 dígitos y empezar por 6, 7 o 9.")
            elif not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email.strip().lower()):
                errores.append("El correo electrónico no tiene un formato válido.")
            elif dni.strip().upper() in socios["DNI"].values:
                errores.append("Este socio ya existe (DNI duplicado).")

            if errores:
                for e in errores:
                    st.warning(f"⚠️ {e}")
            else:
                # --- Guardar temporalmente en sesión ---
                st.session_state.nuevo_socio = {
                    "Nombre": nombre.strip(),
                    "Apellidos": apellidos.strip(),
                    "DNI": dni.strip().upper(),
                    "Teléfono": telefono.strip().replace(" ", ""),
                    "Email": email.strip().lower(),
                    "Disciplina": st.session_state.disciplina,
                    "Plan contratado": st.session_state.plan_disciplina,
                    "Precio": st.session_state.precio_plan,
                    "Fecha nacimiento": st.session_state.fecha_nacimiento,
                    "Fecha de alta": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Banco": "",
                    "Titular": "",
                    "IBAN": "",
                    "Localidad": "",
                    "Estado": "Activo",
                    "Estado de pago": "No pagado",
                    "Fecha último pago": ""
                }
                st.session_state.paso = 2
                st.rerun()

    # --- Paso 2: Datos bancarios ---
    elif st.session_state.paso == 2:
        if "nuevo_socio" not in st.session_state:
            st.warning("Primero completa el formulario anterior.")
            st.session_state.paso = 1
            st.rerun()

        st.info("Introduce los datos bancarios del socio.")
        if st.button("⬅️ Volver al formulario anterior"):
            st.session_state.paso = 1
            st.rerun()

        datos = st.session_state.nuevo_socio
        with st.form("form_datos_bancarios"):
            banco = st.text_input("Banco", value=datos.get("Banco", ""))
            titular = st.text_input("Titular", value=datos.get("Titular", ""))
            iban = st.text_input("IBAN", value=datos.get("IBAN", ""))
            localidad = st.text_input("Localidad", value=datos.get("Localidad", ""))
            continuar_banco = st.form_submit_button("Continuar ➡️")

        if continuar_banco:
            errores = []
            if not banco.strip():
                errores.append("El banco es obligatorio.")
            if not titular.strip():
                errores.append("El titular es obligatorio.")
            iban_limpio = iban.replace(" ", "").upper()
            if not iban_limpio:
                errores.append("El IBAN es obligatorio.")
            elif not re.match(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}$", iban_limpio):
                errores.append("El IBAN no parece válido. Usa el formato estándar (Ej: ES00...).")
            if not localidad.strip():
                errores.append("La localidad es obligatoria.")

            if errores:
                for err in errores:
                    st.error(err)
            else:
                st.session_state.nuevo_socio.update(
                    {
                        "Banco": banco.strip(),
                        "Titular": titular.strip(),
                        "IBAN": iban_limpio,
                        "Localidad": localidad.strip(),
                    }
                )
                st.session_state.paso = 3
                st.rerun()

    # --- Paso 3: Confirmar datos ---
    elif st.session_state.paso == 3:
        st.info("📋 Revisa los datos antes de continuar:")
        nuevo = st.session_state.nuevo_socio
        st.write(f"**Nombre:** {nuevo['Nombre']}")
        st.write(f"**Apellidos:** {nuevo['Apellidos']}")
        st.write(f"**DNI:** {nuevo['DNI']}")
        st.write(f"**Teléfono:** {nuevo['Teléfono']}")
        st.write(f"**Email:** {nuevo['Email']}")
        st.write(f"**Disciplina:** {nuevo['Disciplina']}")
        st.write(
            f"**Plan contratado:** {nuevo['Plan contratado']} ({nuevo['Precio']})"
        )
        st.write(f"**Banco:** {nuevo.get('Banco','')}")
        st.write(f"**Titular:** {nuevo.get('Titular','')}")
        st.write(f"**IBAN:** {nuevo.get('IBAN','')}")
        st.write(f"**Localidad:** {nuevo.get('Localidad','')}")

        col1, col2 = st.columns(2)
        if col1.button("⬅️ Volver"):
            st.session_state.paso = 2
            _reset_firma_state(reset_canvas=True)
            st.rerun()
        if col2.button("Confirmar y continuar ✅"):
            st.session_state.paso = 4
            st.rerun()

    # --- Paso 4: Documento RGPD + Aceptación ---
    elif st.session_state.paso == 4:
        st.markdown("### 📄 Documento legal — Consentimiento RGPD")
        if st.button("⬅️ Volver al resumen"):
            st.session_state.paso = 3
            _reset_firma_state(reset_canvas=True)
            st.rerun()

        if BASE_PDF.exists():
            with open(BASE_PDF, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode("utf-8")
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600px" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
        else:
            st.error("❌ No se encontró el documento RGPD en la carpeta assets.")

        st.markdown("### ✍️ Firma digital")
        st.write("✍️ Firma del socio (usa el ratón o el dedo en pantalla táctil)")

        canvas_result = st_canvas(
            fill_color="#000000",
            stroke_width=2,
            stroke_color="#000000",
            background_color="#FFFFFF",
            height=180,
            width=600,
            drawing_mode="freedraw",
            key=f"canvas_firma_{st.session_state.canvas_firma_key}",
        )

        if canvas_result.image_data is not None:
            hay_trazo = bool(
                canvas_result.json_data
                and canvas_result.json_data.get("objects")
                and len(canvas_result.json_data.get("objects")) > 0
            )
            if hay_trazo:
                st.session_state.firma_imagen = canvas_result.image_data
                st.session_state.firma_realizada = True
            else:
                st.session_state.firma_realizada = False

        if st.button("🧽 Limpiar firma"):
            _reset_firma_state(reset_canvas=True)
            st.rerun()

        aceptar = st.checkbox("He leído y acepto el documento legal de consentimiento RGPD")

        if st.button("Guardar alta ✅"):
            if not aceptar:
                st.warning("⚠️ Debes aceptar el documento para continuar.")
            elif not st.session_state.get("firma_realizada"):
                st.warning("⚠️ Debes firmar el documento para continuar.")
            else:
                nuevo = st.session_state.nuevo_socio
                firma_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                firma_png = FIRMAS_DIR / f"firma_{nuevo['DNI']}.png"
                pdf_firmado = FIRMAS_DIR / f"Consentimiento_Firmado_{nuevo['DNI']}.pdf"

                progress = st.progress(0)
                progress.progress(15)

                _guardar_firma_imagen(st.session_state["firma_imagen"], firma_png)
                progress.progress(45)

                _generar_pdf_firmado(
                    BASE_PDF,
                    firma_png,
                    pdf_firmado,
                    nuevo["Nombre"],
                    nuevo["Apellidos"],
                    nuevo["DNI"],
                    firma_timestamp,
                )
                progress.progress(85)

                socios = pd.concat([socios, pd.DataFrame([nuevo])], ignore_index=True)
                guardar_datos(socios)
                detalle = (
                    f"Disciplina: {nuevo['Disciplina']}, Plan: {nuevo['Plan contratado']} "
                    f"({nuevo['Precio']}), Fecha nacimiento: {nuevo['Fecha nacimiento']}, "
                    f"Email: {nuevo['Email']}, Teléfono: {nuevo['Teléfono']}"
                )
                registrar_log(
                    usuario=st.session_state.get("username", "desconocido"),
                    accion="alta",
                    dni=nuevo["DNI"],
                    detalle=detalle,
                )
                progress.progress(100)

                st.success("✅ Alta completada y documento firmado correctamente.")
                st.toast("Nuevo socio registrado correctamente.")

                # --- Limpiar flujo ---
                st.session_state.paso = 1
                st.session_state.pop("nuevo_socio", None)
                st.session_state.pop("disciplina", None)
                st.session_state.pop("plan_disciplina", None)
                st.session_state.pop("precio_plan", None)
                st.session_state.pop("fecha_nacimiento", None)
                st.session_state.pop("edad", None)
                st.session_state.pop("tipo_cliente", None)
                st.session_state.pop("fecha_temp", None)
                _reset_firma_state(reset_canvas=True)
                st.session_state.show_modal = True
                st.session_state.modal_timestamp = None
                st.rerun()
