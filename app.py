import streamlit as st
from pathlib import Path
import os
import time

# --- Módulos internos ---
from ui.style import aplicar_estilos
from ui.header import mostrar_encabezado
from modules.dashboard import mostrar_dashboard
from modules.alta import mostrar_alta
from modules.baja import mostrar_baja
from modules.ver_socios import mostrar_socios
from modules.usuarios import (
    cargar_usuarios,
    guardar_usuarios,
    verificar_password,
    hash_password,
    es_hash_bcrypt,
)
from modules.editar import mostrar_editar
from core.data_manager import sincronizar_pendientes, hay_pendientes_offline

# --- Configuración de página ---
st.set_page_config(page_title="Gestión Gimnasio", page_icon="💪", layout="centered")

# --- Estilo y encabezado ---
aplicar_estilos()
mostrar_encabezado()

# --- Rutas de archivos ---
BASE_DIR = Path(__file__).resolve().parent
USERS_PATH = BASE_DIR / "usuarios.json"
CREDS_PATH = BASE_DIR / "credenciales.json"

# --- Verificaciones de archivos críticos ---
if not USERS_PATH.exists():
    st.error(f"❌ No se encontró el archivo de usuarios en: {USERS_PATH}")
    st.stop()

if not CREDS_PATH.exists() and "GOOGLE_CREDS" not in os.environ:
    st.error(f"❌ No se encontró el archivo de credenciales en: {CREDS_PATH}")
    st.stop()

# --- Estado de sesión ---
for key in ["logged_in", "role", "username", "full_name"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "logged_in" else False

# --- LOGIN ---
def login_screen():
    st.title("🔐 Acceso al sistema")

    try:
        data = cargar_usuarios()
        usuarios = data.get("usuarios", [])
    except Exception as e:
        st.error(f"Error al cargar usuarios.json: {e}")
        st.stop()

    user = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Entrar"):
        encontrado = None
        for u in usuarios:
            if u["username"] != user:
                continue
            if verificar_password(password, u.get("password", "")):
                if not es_hash_bcrypt(u.get("password", "")):
                    u["password"] = hash_password(password)
                    guardar_usuarios({"usuarios": usuarios})
                encontrado = u
                break
        if encontrado:
            st.session_state.logged_in = True
            st.session_state.username = encontrado["username"]
            st.session_state.role = encontrado["role"]
            st.session_state.full_name = encontrado["full_name"]
            st.success(f"Bienvenido, {encontrado['full_name']} ✅")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos ❌")

def logout():
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.full_name = None
    for key in [
        "busqueda_resultados",
        "busqueda_valor",
        "busqueda_criterio",
        "busqueda_owner",
        "busqueda_last_view",
        "menu_accion",
        "menu_opciones",
        "baja_socio_en_proceso",
    ]:
        if key in st.session_state:
            del st.session_state[key]

# --- Mostrar login si no ha iniciado sesión ---
if not st.session_state.logged_in:
    login_screen()
    st.stop()

# --- Menú lateral (solo visible tras login) ---
st.sidebar.write(f"👤 Usuario: {st.session_state.full_name}")
st.sidebar.write(f"🔑 Rol: {st.session_state.role.capitalize()}")

sincronizados = sincronizar_pendientes()
if sincronizados:
    st.toast(f"✅ {sincronizados} cambio(s) sincronizados correctamente.")
if st.session_state.get("offline_flag") or hay_pendientes_offline():
    st.warning("⚠ La red está inestable. Cambios guardados localmente y pendientes de sincronizar.")

# --- Modal tras alta ---
if "show_modal" not in st.session_state:
    st.session_state.show_modal = False
if "modal_timestamp" not in st.session_state:
    st.session_state.modal_timestamp = None

if st.session_state.show_modal:
    if st.session_state.modal_timestamp is None:
        st.session_state.modal_timestamp = time.time()

    st.markdown(
        """
        <style>
        .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.65);
            z-index: 9998;
            pointer-events: none;
        }
        .modal-container {
            position: fixed;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        }
        .modal-card {
            background: #fdfdfd;
            color: #111;
            border-radius: 18px;
            padding: 30px 40px;
            text-align: center;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.25);
            width: min(90%, 520px);
            font-size: 1.05rem;
            line-height: 1.4;
        }
        .modal-card h3 {
            margin-bottom: 8px;
            font-size: 1.4rem;
        }
        .modal-card p {
            margin-bottom: 18px;
        }
        </style>
        <div class="modal-overlay"></div>
        <div class="modal-container">
            <div class="modal-card">
                <h3>✔️ Socio dado de alta correctamente</h3>
                <p>Confirma para finalizar la sesión.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    wait_seconds = 1.5
    elapsed = time.time() - st.session_state.modal_timestamp
    remaining = max(0, wait_seconds - elapsed)
    if remaining > 0:
        time.sleep(remaining)

    st.session_state.show_modal = False
    st.session_state.modal_timestamp = None
    logout()
    st.rerun()
    st.stop()

# --- Menú dinámico según rol ---
if st.session_state.role == "admin":
    opciones = [
        "Registrar alta",
        "🔍 Buscar socio",
        "✏️ Editar socio",
        "Ver socios",
        "Gestión de usuarios 👥",
        "📊 Estadísticas del gimnasio"
    ]
elif st.session_state.role == "empleado":
    opciones = ["Registrar alta", "🔍 Buscar socio"]
else:
    opciones = ["Registrar alta"]

st.session_state["menu_opciones"] = opciones

if "menu_accion_target" in st.session_state:
    st.session_state["menu_accion"] = st.session_state.pop("menu_accion_target")

opcion = st.sidebar.selectbox("Acción", opciones, key="menu_accion")
st.sidebar.button("Cerrar sesión", on_click=logout)

# --- Contenido dinámico ---
if opcion == "Registrar alta":
    mostrar_alta()
elif opcion == "🔍 Buscar socio":
    mostrar_baja()
elif opcion == "Ver socios":
    mostrar_socios()
elif opcion == "✏️ Editar socio":
    mostrar_editar()
elif opcion == "📊 Estadísticas del gimnasio":
    mostrar_dashboard()
elif opcion == "Gestión de usuarios 👥":
    from modules.usuarios import mostrar_gestion_usuarios
    mostrar_gestion_usuarios()
