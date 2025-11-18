import streamlit as st
import json
import os
import re
import time
import bcrypt

USUARIOS_PATH = "usuarios.json"
FORM_DEFAULTS = {
    "nombre_nuevo_usuario": "",
    "user_nuevo_usuario": "",
    "pass1_nuevo_usuario": "",
    "pass2_nuevo_usuario": "",
    "rol_nuevo_usuario": "admin",
}

# --- Cargar usuarios ---
def cargar_usuarios():
    if not os.path.exists(USUARIOS_PATH):
        return {"usuarios": []}
    try:
        with open(USUARIOS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"usuarios": []}

# --- Guardar usuarios ---
def guardar_usuarios(data):
    with open(USUARIOS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- Hashing de contraseñas ---
def hash_password(password: str) -> str:
    """Genera un hash seguro usando bcrypt antes de persistir la contraseña."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def es_hash_bcrypt(valor: str) -> bool:
    """Determina si el valor almacenado ya corresponde a un hash bcrypt."""
    return isinstance(valor, str) and valor.startswith("$2")


def verificar_password(password_plana: str, password_guardada: str) -> bool:
    """
    Comprueba la contraseña ingresada contra la almacenada.
    Acepta hashes bcrypt y contraseñas antiguas en texto plano para facilitar la migración.
    """
    if not password_guardada:
        return False
    if es_hash_bcrypt(password_guardada):
        try:
            return bcrypt.checkpw(password_plana.encode("utf-8"), password_guardada.encode("utf-8"))
        except ValueError:
            return False
    # Compatibilidad con contraseñas antiguas (texto plano)
    return password_plana == password_guardada

# --- Validar contraseña segura ---
def validar_contraseña(password):
    patron = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$'
    return re.match(patron, password)

# --- Calcular nivel de fuerza (para la barra) ---
def calcular_fuerza(password):
    fuerza = 0
    if len(password) >= 8:
        fuerza += 1
    if re.search(r'[A-Z]', password):
        fuerza += 1
    if re.search(r'[a-z]', password):
        fuerza += 1
    if re.search(r'\d', password):
        fuerza += 1
    if re.search(r'[\W_]', password):
        fuerza += 1
    return fuerza

# --- Helpers ---
def limpiar_formulario_nuevo_usuario():
    for key, default in FORM_DEFAULTS.items():
        st.session_state[key] = default

# --- Interfaz principal ---
def mostrar_gestion_usuarios():
    st.subheader("👥 Gestión de usuarios del sistema")

    data = cargar_usuarios()
    usuarios = data.get("usuarios", [])
    usuario_actual = st.session_state.get("username", None)

    # --- Si el usuario acaba de crearse, limpiar los campos ---
    if st.session_state.get("usuario_creado"):
        limpiar_formulario_nuevo_usuario()
        st.session_state["usuario_creado"] = False

    # --- Crear nuevo usuario ---
    with st.expander("➕ Crear nuevo usuario"):
        nuevo_nombre = st.text_input("Nombre completo", key="nombre_nuevo_usuario")
        nuevo_user = st.text_input("Nombre de usuario", key="user_nuevo_usuario")
        nuevo_pass1 = st.text_input("Contraseña", type="password", key="pass1_nuevo_usuario")
        nuevo_pass2 = st.text_input("Repetir contraseña", type="password", key="pass2_nuevo_usuario")
        nuevo_rol = st.selectbox("Rol", ["admin", "empleado"], key="rol_nuevo_usuario")

        # --- Barra de fuerza ---
        if nuevo_pass1:
            fuerza = calcular_fuerza(nuevo_pass1)
            colores = ["#ff4b4b", "#ff884b", "#ffb84b", "#a4ff4b", "#4bff4b"]
            etiquetas = ["Muy débil", "Débil", "Media", "Buena", "Fuerte"]
            nivel = min(fuerza - 1, 4)
            st.markdown(
                f"""
                <div style='margin-top:-10px; margin-bottom:5px;'>
                    <div style='background:#333; border-radius:8px; height:10px;'>
                        <div style='width:{fuerza*20}%; height:10px; border-radius:8px; background:{colores[nivel]}'></div>
                    </div>
                    <p style='color:{colores[nivel]}; margin-top:4px; font-size:0.9em;'>Nivel: {etiquetas[nivel]}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.caption("🔒 La contraseña debe tener **mínimo 8 caracteres**, incluir **una mayúscula**, **una minúscula**, **un número** y **un símbolo**.")

        # --- Botón de creación ---
        if st.button("✅ Crear usuario"):
            if not nuevo_nombre or not nuevo_user or not nuevo_pass1:
                st.warning("⚠️ Todos los campos son obligatorios.")
            elif nuevo_pass1 != nuevo_pass2:
                st.error("❌ Las contraseñas no coinciden.")
            elif not validar_contraseña(nuevo_pass1):
                st.warning("⚠️ La contraseña no cumple los requisitos mínimos de seguridad.")
            elif any(u["username"] == nuevo_user for u in usuarios):
                st.warning("⚠️ Ese nombre de usuario ya existe.")
            else:
                usuarios.append({
                    "username": nuevo_user.strip(),
                    # Almacenar siempre el hash resultante, nunca la contraseña en texto plano
                    "password": hash_password(nuevo_pass1.strip()),
                    "role": nuevo_rol,
                    "full_name": nuevo_nombre.strip()
                })
                guardar_usuarios({"usuarios": usuarios})

                # ✅ Modal centrado con barra
                st.markdown(
                    """
                    <div style="
                        position: fixed;
                        top: 0; left: 0;
                        width: 100%; height: 100%;
                        background-color: rgba(0, 0, 0, 0.7);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        z-index: 9999;">
                        <div style="
                            background-color: #111;
                            color: #00FF7F;
                            padding: 30px;
                            border-radius: 15px;
                            text-align: center;
                            width: 400px;
                            box-shadow: 0px 0px 15px rgba(0, 255, 127, 0.6);">
                            <h3>✅ Usuario creado correctamente</h3>
                            <p style='color:#ccc;'>Guardando cambios...</p>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Barra de progreso
                progress = st.progress(0)
                for i in range(100):
                    time.sleep(0.015)
                    progress.progress(i + 1)

                # ✅ Marca para limpiar en el próximo render
                st.session_state["usuario_creado"] = True
                time.sleep(0.5)
                st.rerun()

    st.markdown("---")

    # --- Listado de usuarios existentes ---
    st.markdown("### 📋 Usuarios registrados")
    if usuarios:
        for i, u in enumerate(usuarios):
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            col1.write(f"👤 **{u['full_name']}**")
            col2.write(f"🧾 {u['username']}")
            col3.write(f"🔑 Rol: {u['role'].capitalize()}")

            if u["username"] != usuario_actual:
                if col4.button("🗑️ Eliminar", key=f"del_{i}"):
                    st.session_state["confirmar_eliminacion"] = u["username"]
                    st.session_state["usuario_index"] = i
                    st.rerun()
            else:
                col4.write("🚫")

        # --- Confirmación de eliminación ---
        if "confirmar_eliminacion" in st.session_state:
            usuario_a_borrar = st.session_state["confirmar_eliminacion"]
            st.error(f"⚠️ ¿Seguro que deseas eliminar al usuario **{usuario_a_borrar}**?")
            colA, colB = st.columns(2)
            with colA:
                if st.button("✅ Sí, eliminar"):
                    usuarios.pop(st.session_state["usuario_index"])
                    guardar_usuarios({"usuarios": usuarios})
                    st.success(f"Usuario '{usuario_a_borrar}' eliminado correctamente.")
                    del st.session_state["confirmar_eliminacion"]
                    del st.session_state["usuario_index"]
                    st.rerun()
            with colB:
                if st.button("❌ Cancelar"):
                    del st.session_state["confirmar_eliminacion"]
                    del st.session_state["usuario_index"]
                    st.info("Operación cancelada.")
                    st.rerun()
    else:
        st.info("No hay usuarios registrados aún.")
