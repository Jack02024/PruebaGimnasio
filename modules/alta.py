import streamlit as st
import pandas as pd
from datetime import datetime, date
import pytz
import time
from core.data_manager import cargar_datos, guardar_datos, registrar_log, upload_pdf_to_drive, ensure_person_folder
from pathlib import Path
import base64
import re  # 🔹 Para validaciones con expresiones regulares
from io import BytesIO
import io
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as reportlab_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from components.signature_pad import signature_pad

BASE_PDF = Path("assets/Consentimiento Fines Promocionales_NICOVA.pdf")

PDF_PROMOCIONALES = "assets/Consentimiento Fines Promocionales_NICOVA.pdf"
PDF_WHATSAPP = "assets/Consentimiento WhatsApp.pdf"
PDF_MENOR14 = "assets/Consentimiento menor de edad, menor de 14 años - Firma madre, padre o tutor legal.pdf"
PDF_14_18 = "assets/Consentimiento menor de edad, mayor de 14 años - Firma padre, madre, tutor legal.pdf"
PDF_PUBLICIDAD = "assets/Documento para el tratamiento publicitario - Firmar.pdf"

DOCS_ADULTO = [
    {"path": PDF_WHATSAPP, "col": "URL Doc WhatsApp", "page": 1, "x": 350, "y": 60},
    {"path": PDF_PUBLICIDAD, "col": "URL Doc Publicidad", "page": 1, "x": 350, "y": 60},
    {"path": PDF_PROMOCIONALES, "col": "URL PDF Consentimiento", "page": 2, "x": 350, "y": 120},
]

DOCS_14_18 = [
    {"path": PDF_WHATSAPP, "col": "URL Doc WhatsApp", "page": 1, "x": 350, "y": 60},
    {"path": PDF_PUBLICIDAD, "col": "URL Doc Publicidad", "page": 1, "x": 350, "y": 60},
    {"path": PDF_14_18, "col": "URL Doc 14-18", "page": 2, "x": 350, "y": 120},
]

DOCS_MENOR14 = [
    {"path": PDF_WHATSAPP, "col": "URL Doc WhatsApp", "page": 1, "x": 350, "y": 60},
    {"path": PDF_PUBLICIDAD, "col": "URL Doc Publicidad", "page": 1, "x": 350, "y": 60},
    {"path": PDF_MENOR14, "col": "URL Doc Menor14", "page": 2, "x": 350, "y": 120},
]

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
        st.session_state["signature_pad_key"] = st.session_state.get("signature_pad_key", 0) + 1


def _generar_pdf_firmado(
    pdf_base: Path,
    firma_buffer: BytesIO,
    nombre: str,
    apellidos: str,
    dni: str,
    timestamp: str,
    page: int | None = None,
    x: int = 350,
    y: int = 120,
) -> bytes:
    reader = PdfReader(str(pdf_base))
    writer = PdfWriter()
    total_paginas = len(reader.pages)

    target_page_index = (page - 1) if page else (total_paginas - 1)

    for index, page in enumerate(reader.pages):
        if index == target_page_index:
            packet = BytesIO()
            can = reportlab_canvas.Canvas(packet, pagesize=A4)

            firma_buffer.seek(0)
            firma_img = Image.open(firma_buffer)
            firma_ancho = 180
            ratio = firma_img.height / firma_img.width if firma_img.width else 1
            firma_alto = firma_ancho * ratio

            firma_buffer.seek(0)
            image_reader = ImageReader(firma_buffer)
            can.drawImage(image_reader, x, y, width=firma_ancho, height=firma_alto, mask="auto")
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

    salida = BytesIO()
    writer.write(salida)
    salida.seek(0)
    return salida.getvalue()

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
                # Preparar cola de documentos (fase 1, no se usa aún en el flujo)
                if edad >= 18:
                    st.session_state.doc_queue = DOCS_ADULTO
                elif edad > 14:
                    st.session_state.doc_queue = DOCS_14_18
                else:
                    st.session_state.doc_queue = DOCS_MENOR14
                st.session_state.doc_index = 0
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
    if "signature_pad_key" not in st.session_state:
        st.session_state.signature_pad_key = 0

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
            nombre = st.text_input("Nombre", value=st.session_state.get("form_nombre", ""))
            apellidos = st.text_input("Apellidos", value=st.session_state.get("form_apellidos", ""))
            dni = st.text_input("DNI", value=st.session_state.get("form_dni", ""))
            telefono = st.text_input("Teléfono", value=st.session_state.get("form_telefono", ""))
            email = st.text_input("Email", value=st.session_state.get("form_email", ""))
            continuar = st.form_submit_button("Continuar ➡️")

        if continuar:
            # Persistir valores del formulario en sesión
            st.session_state.form_nombre = nombre
            st.session_state.form_apellidos = apellidos
            st.session_state.form_dni = dni
            st.session_state.form_telefono = telefono
            st.session_state.form_email = email

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
                    "Fecha de alta": datetime.now(tz=pytz.timezone("Europe/Madrid")).strftime("%d-%m-%Y %H:%M:%S"),
                    "Banco": "",
                    "Titular": "",
                    "IBAN": "",
                    "Localidad": "",
                    "URL PDF Consentimiento": "",
                    "URL Doc WhatsApp": "",
                    "URL Doc Publicidad": "",
                    "URL Doc Menor14": "",
                    "URL Doc 14-18": "",
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
            banco = st.text_input("Banco", value=st.session_state.get("form_banco", datos.get("Banco", "")))
            titular = st.text_input("Titular", value=st.session_state.get("form_titular", datos.get("Titular", "")))
            iban_input = st.text_input("IBAN", value=st.session_state.get("form_iban", datos.get("IBAN", "ES")), max_chars=24)
            localidad_input = st.text_input("Localidad", value=st.session_state.get("form_localidad", datos.get("Localidad", "")))
            continuar_banco = st.form_submit_button("Continuar ➡️")

        if continuar_banco:
            st.session_state.form_banco = banco
            st.session_state.form_titular = titular
            st.session_state.form_iban = iban_input
            st.session_state.form_localidad = localidad_input
            errores = []
            if not banco.strip():
                errores.append("El banco es obligatorio.")
            if not titular.strip():
                errores.append("El titular es obligatorio.")
            # Normalizar localidad
            localidad_normalizada = localidad_input.strip().capitalize() if localidad_input else ""
            if not localidad_normalizada:
                errores.append("La localidad es obligatoria.")
            # Validar IBAN fijo ES + 22 dígitos
            iban_limpio = (iban_input or "").replace(" ", "").upper()
            if not iban_limpio:
                errores.append("El IBAN es obligatorio.")
            else:
                if not iban_limpio.startswith("ES"):
                    iban_limpio = "ES" + iban_limpio.replace("ES", "")
                if len(iban_limpio) != 24:
                    errores.append("El IBAN debe contener exactamente 24 caracteres (ES + 22 dígitos).")
                elif not iban_limpio[2:].isdigit():
                    errores.append("Los 22 caracteres después de 'ES' deben ser numéricos.")

            if errores:
                for err in errores:
                    st.error(err)
            else:
                st.session_state.nuevo_socio.update(
                    {
                        "Banco": banco.strip(),
                        "Titular": titular.strip(),
                        "IBAN": iban_limpio,
                        "Localidad": localidad_normalizada,
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

        st.info(
            "Para una mejor gestión, rogamos que, si se quiere dar de baja un socio "
            "se comunique del día 01 al día 25 del mes anterior. "
            "Si no se comunica en ese plazo, se cobrará el mes correspondiente."
        )
        with st.expander("Información legal sobre el tratamiento de datos"):
            st.caption(
                "La identidad del responsable que trata sus datos personales es: NICOVA SPORT BOXING SL, "
                "con CIF/NIF B09817800, Dirección C/ Caleruega, 51, Población MADRID, Código Postal 28033, "
                "Provincia MADRID y Correo electrónico agboxeo@gmail.com. "
                "En esta organización tratamos la información que nos facilitan las personas interesadas con los fines "
                "de comprobar que se están llevando a cabo todas las medidas técnicas necesarias para la correcta gestión "
                "de los datos personales con el software aplicado; enviar información comercial y/o publicitaria mediante "
                "correo electrónico; gestionar cualquier problema de índole jurídica que afecte a la empresa; gestionar, "
                "mantener y reparar los sistemas de almacenamiento informático; llevar a cabo la gestión fiscal y contable "
                "propia; cumplir el principio de limitación del plazo de conservación de los datos personales; cumplir los "
                "requisitos del RGPD y LOPD; realizar la gestión administrativa de clientes particulares y llevar a cabo la "
                "venta o prestación del servicio contratado. La legitimación para el tratamiento de sus datos es una obligación "
                "legal del responsable, el contrato suscrito por usted, el interés legítimo del responsable y/o su previo "
                "consentimiento. Sus datos personales se incorporarán a los siguientes ficheros, titularidad de la organización: "
                "Gestión contable propia; Gestión fiscal propia; Mantenimiento informático; Asuntos jurídicos propios; Correos "
                "electrónicos; Seguridades en el software y hardware; Destrucción de documentos; Protección de Datos Personales; "
                "Clientes. Los datos personales que tratamos en nuestra organización proceden del propio interesado. Usted puede "
                "ejercer los derechos de acceso, rectificación, supresión, portabilidad, limitación, oposición al tratamiento, "
                "y oposición a la toma de decisiones automatizadas, así como interponer reclamaciones ante la autoridad de control. "
                "En su caso, puede retirar el consentimiento otorgado. Puede consultar toda la información detallada en la web o "
                "enviando un e-mail a la dirección arriba indicada."
            )

        col1, col2 = st.columns(2)
        if col1.button("⬅️ Volver"):
            st.session_state.paso = 2
            _reset_firma_state(reset_canvas=True)
            st.rerun()
        if col2.button("Confirmar y continuar ✅"):
            st.session_state.paso = 4
            st.session_state.doc_index = 0
            st.rerun()

    # --- Paso 4: Firma de documentos (stepper múltiple con una sola firma final) ---
    elif st.session_state.paso == 4:
        st.markdown("### 📄 Firma de documentos")
        doc_queue = st.session_state.get("doc_queue") or [
            {"path": str(BASE_PDF), "col": "URL PDF Consentimiento", "page": None, "x": 350, "y": 120}
        ]
        doc_index = st.session_state.get("doc_index", 0)
        if "doc_respuestas" not in st.session_state:
            st.session_state.doc_respuestas = {}

        # Navegación: volver al resumen solo en el primer documento; atrás en los siguientes
        if doc_index == 0:
            if st.button("⬅️ Volver al resumen"):
                st.session_state.paso = 3
                st.session_state.doc_index = 0
                _reset_firma_state(reset_canvas=True)
                st.rerun()
        else:
            if st.button("⬅️ Atrás"):
                st.session_state.doc_index = max(0, doc_index - 1)
                _reset_firma_state(reset_canvas=True)
                st.rerun()

        if doc_index >= len(doc_queue):
            # Ya no hay documentos pendientes; continuar con guardado final
            nuevo = st.session_state.nuevo_socio

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
            st.success("✅ Alta completada y documentos firmados correctamente.")
            st.toast("Nuevo socio registrado correctamente.")

            # --- Limpiar flujo ---
            st.session_state.paso = 1
            for key in [
                "form_nombre",
                "form_apellidos",
                "form_dni",
                "form_telefono",
                "form_email",
                "form_banco",
                "form_titular",
                "form_iban",
                "form_localidad",
                "nuevo_socio",
                "disciplina",
                "plan_disciplina",
                "precio_plan",
                "fecha_nacimiento",
                "edad",
                "tipo_cliente",
                "fecha_temp",
                "doc_queue",
                "doc_index",
                "doc_respuestas",
            ]:
                st.session_state.pop(key, None)
            _reset_firma_state(reset_canvas=True)
            st.session_state.show_modal = True
            st.session_state.modal_timestamp = None
            st.rerun()

        doc = doc_queue[doc_index]
        total_docs = len(doc_queue)
        st.markdown(f"**Documento {doc_index + 1} / {total_docs}**")
        st.info("Revisa el documento y selecciona tu decisión.")

        pdf_path = Path(doc["path"])
        if pdf_path.exists():
            with open(pdf_path, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode("utf-8")
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600px" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
        else:
            st.error(f"❌ No se encontró el documento en {pdf_path}")

        # Selección con checkboxes mutuamente excluyentes
        # Leer siempre directamente de los checkboxes (estado actual)
        col_acepto, col_no_acepto = st.columns(2)
        acepto = col_acepto.checkbox("Acepto", key=f"acepto_{doc_index}")
        no_acepto = col_no_acepto.checkbox("No acepto", key=f"no_acepto_{doc_index}")

        es_ultimo = doc_index == (total_docs - 1)

        if es_ultimo:
            st.markdown("### ✍️ Firma digital")
            st.write("✍️ Firma del socio (usa el ratón o el dedo en pantalla táctil)")

            firma_data = signature_pad(key=f"firma_component_{st.session_state.signature_pad_key}", default={"image": None})
            if firma_data and isinstance(firma_data, dict) and firma_data.get("image"):
                try:
                    header, b64data = firma_data["image"].split(",", 1)
                    img_bytes = base64.b64decode(b64data)
                    firma_image = Image.open(BytesIO(img_bytes)).convert("RGB")
                    st.session_state.firma_data = firma_data["image"]
                    st.session_state.firma_imagen = img_bytes
                    st.session_state.firma_realizada = True
                except Exception:
                    if "firma_data" not in st.session_state:
                        st.session_state.firma_data = None
                    st.session_state.firma_realizada = False
                    st.warning("⚠️ No se pudo procesar la firma. Intenta de nuevo.")
            else:
                if "firma_data" not in st.session_state:
                    st.session_state.firma_data = None
                st.session_state.firma_realizada = False
                st.info("Dibuja tu firma. Se guardará automáticamente al levantar el lápiz o el dedo.")

            if st.button("🧽 Limpiar firma"):
                _reset_firma_state(reset_canvas=True)
                st.rerun()

            aceptar_rgpd = st.checkbox("He leído y acepto el tratamiento de mis datos personales (RGPD)")

            if st.button("Finalizar firma"):
                # Validación XOR: exactamente uno marcado
                if (acepto and no_acepto) or (not acepto and not no_acepto):
                    st.error("Debes seleccionar solo una opción: Acepto o No acepto.")
                    return
                estado_actual = "ACEPTADO" if acepto else "RECHAZADO"
                st.session_state.doc_respuestas[doc["col"]] = estado_actual
                st.session_state.nuevo_socio[doc["col"]] = estado_actual

                # Verificar que todos los documentos tienen respuesta
                if any(d["col"] not in st.session_state.doc_respuestas for d in doc_queue):
                    st.warning("Faltan decisiones en documentos anteriores.")
                    return

                # Si algún doc está aceptado, debe haber firma y checkbox RGPD marcado
                algun_aceptado = any(
                    st.session_state.doc_respuestas.get(d["col"]) == "ACEPTADO" for d in doc_queue
                )
                if algun_aceptado:
                    if not aceptar_rgpd:
                        st.warning("⚠️ Debes aceptar el tratamiento de datos (RGPD) para continuar.")
                        return
                    if not st.session_state.get("firma_data"):
                        st.error("⚠️ Debes firmar el documento para continuar.")
                        return

                progress = st.progress(0)
                firma_buffer = None
                if algun_aceptado:
                    firma_buffer = io.BytesIO(base64.b64decode(st.session_state["firma_data"].split(",", 1)[1]))

                folder_id = ensure_person_folder(
                    st.session_state.nuevo_socio["Nombre"],
                    st.session_state.nuevo_socio["Apellidos"],
                    st.session_state.nuevo_socio["DNI"],
                )

                for idx_doc, d in enumerate(doc_queue):
                    estado_doc = st.session_state.doc_respuestas.get(d["col"])
                    if estado_doc != "ACEPTADO":
                        st.session_state.nuevo_socio[d["col"]] = ""
                        continue
                    if firma_buffer is None:
                        continue
                    progress.progress(int((idx_doc / max(1, len(doc_queue))) * 100))
                    pdf_path_iter = Path(d["path"])
                    pdf_bytes = _generar_pdf_firmado(
                        pdf_path_iter,
                        firma_buffer,
                        st.session_state.nuevo_socio["Nombre"],
                        st.session_state.nuevo_socio["Apellidos"],
                        st.session_state.nuevo_socio["DNI"],
                        datetime.now(tz=pytz.timezone("Europe/Madrid")).strftime("%d-%m-%Y %H:%M:%S"),
                        page=d.get("page"),
                        x=d.get("x", 350),
                        y=d.get("y", 120),
                    )
                    pdf_filename = f"{pdf_path_iter.stem}_{st.session_state.nuevo_socio['DNI']}.pdf"
                    pdf_url = upload_pdf_to_drive(pdf_bytes, pdf_filename, folder_id=folder_id)
                    st.session_state.nuevo_socio[d["col"]] = pdf_url or ""

                progress.progress(100)
                st.session_state.doc_index = len(doc_queue)
                st.rerun()
        else:
            if st.button("Continuar al siguiente documento"):
                # Validación XOR: exactamente uno marcado
                if (acepto and no_acepto) or (not acepto and not no_acepto):
                    st.error("Debes seleccionar solo una opción: Acepto o No acepto.")
                    return
                estado_actual = "ACEPTADO" if acepto else "RECHAZADO"
                st.session_state.doc_respuestas[doc["col"]] = estado_actual
                st.session_state.nuevo_socio[doc["col"]] = estado_actual
                st.session_state.doc_index = doc_index + 1
                st.rerun()
