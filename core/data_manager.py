# core/data_manager.py
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from pathlib import Path
import json

# --- Configuración ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
BASE_DIR = Path(__file__).resolve().parents[1]
CREDS_PATH = BASE_DIR / "credenciales.json"
SHEET_NAME = "socios_gimnasio"
QUEUE_PATH = BASE_DIR / "offline_queue.json"

# --- Verificación del archivo de credenciales ---
if not CREDS_PATH.exists():
    import streamlit as st
    st.error(f"No se encontró el archivo de credenciales en: {CREDS_PATH}")
    st.stop()

# --- Conexión global ---
try:
    _credentials = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    _client = gspread.authorize(_credentials)
    _sheet = _client.open(SHEET_NAME).sheet1
    try:
        _logs_sheet = _client.open(SHEET_NAME).worksheet("Logs")
    except gspread.exceptions.WorksheetNotFound:
        _logs_sheet = _client.open(SHEET_NAME).add_worksheet(title="Logs", rows=1000, cols=5)
        _logs_sheet.append_row(["Fecha", "Usuario", "Acción", "DNI", "Detalle"])
except Exception as e:
    import streamlit as st
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()

# --- Esquema fijo ---
COLUMNS = [
    "Nombre",
    "Apellidos",
    "DNI",
    "Teléfono",
    "Email",
    "Tipo de plan",
    "Disciplina",
    "Plan contratado",
    "Precio",
    "Fecha nacimiento",
    "Fecha de alta",
    "Estado",
    "Estado de pago",
    "Fecha último pago",
]

PLAN_PERIODOS_MESES = {
    "Mensual": 1,
    "Trimestral": 3,
    "Anual": 12,
}


def _load_queue():
    if QUEUE_PATH.exists():
        try:
            with open(QUEUE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_queue(data):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _enqueue_operation(op_type: str, payload: dict):
    queue = _load_queue()
    queue.append({"type": op_type, "payload": payload})
    _save_queue(queue)
    try:
        import streamlit as st

        st.session_state["offline_flag"] = True
    except Exception:
        pass


def _clear_offline_flag():
    try:
        import streamlit as st

        st.session_state["offline_flag"] = False
    except Exception:
        pass


def _empty_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garantiza la presencia y el orden del esquema fijo."""
    df = df.copy()
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[COLUMNS]


def _flush_dataframe(df: pd.DataFrame) -> None:
    df = _ensure_columns(df)
    data_rows = df.fillna("").astype(str).values.tolist() if not df.empty else []
    _sheet.clear()
    _sheet.update([COLUMNS] + data_rows)


def _aplicar_reglas_pago(df: pd.DataFrame):
    actualizado = False
    now = pd.Timestamp.now()

    if "Estado de pago" not in df.columns:
        df["Estado de pago"] = "No pagado"
        actualizado = True
    else:
        df["Estado de pago"] = df["Estado de pago"].replace("", "No pagado")

    if "Fecha último pago" not in df.columns:
        df["Fecha último pago"] = ""
        actualizado = True

    for idx, row in df.iterrows():
        plan = str(row.get("Tipo de plan", "")).strip()
        estado_actual = str(row.get("Estado de pago", "")).strip() or "No pagado"
        fecha_pago = str(row.get("Fecha último pago", "")).strip()

        if plan not in PLAN_PERIODOS_MESES:
            if estado_actual not in ("Pagado", "No pagado"):
                df.at[idx, "Estado de pago"] = "No pagado"
                actualizado = True
            continue

        if not fecha_pago:
            if estado_actual != "No pagado":
                df.at[idx, "Estado de pago"] = "No pagado"
                actualizado = True
            continue

        fecha_dt = pd.to_datetime(fecha_pago, errors="coerce")
        if pd.isna(fecha_dt):
            if estado_actual != "No pagado":
                df.at[idx, "Estado de pago"] = "No pagado"
                actualizado = True
            continue

        meses = PLAN_PERIODOS_MESES[plan]
        next_due = fecha_dt + pd.DateOffset(months=meses)
        if now >= next_due and estado_actual != "No pagado":
            df.at[idx, "Estado de pago"] = "No pagado"
            actualizado = True

    return df, actualizado


def cargar_datos() -> pd.DataFrame:
    """
    Obtiene todos los registros del Sheet garantizando el esquema fijo.
    """
    try:
        registros = _sheet.get_all_records()
    except Exception:
        return _empty_dataframe()

    if not registros:
        return _empty_dataframe()

    df = pd.DataFrame(registros)
    columnas_faltantes = [col for col in COLUMNS if col not in df.columns]
    df = _ensure_columns(df)
    df, actualizado = _aplicar_reglas_pago(df)
    if actualizado or columnas_faltantes:
        _flush_dataframe(df)
    return df


def guardar_datos(df_nuevos: pd.DataFrame) -> None:
    """
    Sobrescribe la hoja con el DataFrame proporcionado.
    """
    if df_nuevos is None:
        df_nuevos = _empty_dataframe()

    try:
        _flush_dataframe(df_nuevos)
        if not _load_queue():
            _clear_offline_flag()
    except Exception as e:
        _enqueue_operation(
            "guardar_datos",
            {"data": df_nuevos.fillna("").to_dict("records"), "error": str(e)},
        )
        print(f"[WARN] Guardar datos en cola offline: {e}")


def registrar_log(usuario: str, accion: str, dni: str, detalle: str = "") -> None:
    """Registra acciones en la hoja 'Logs' sin interrumpir el flujo principal."""
    try:
        timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        fila = [timestamp, usuario or "desconocido", accion, dni, detalle]
        _logs_sheet.append_row(fila)
    except Exception as e:
        _enqueue_operation(
            "log",
            {
                "usuario": usuario,
                "accion": accion,
                "dni": dni,
                "detalle": detalle,
                "error": str(e),
            },
        )
        print(f"[WARN] No se pudo registrar el log ({accion} - {dni}): {e}")


def sincronizar_pendientes():
    queue = _load_queue()
    if not queue:
        return 0

    restantes = []
    procesadas = 0
    for op in queue:
        try:
            if op["type"] == "guardar_datos":
                df = pd.DataFrame(op["payload"]["data"])
                _flush_dataframe(df)
            elif op["type"] == "log":
                timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                fila = [
                    timestamp,
                    op["payload"].get("usuario") or "desconocido",
                    op["payload"].get("accion"),
                    op["payload"].get("dni"),
                    op["payload"].get("detalle"),
                ]
                _logs_sheet.append_row(fila)
            procesadas += 1
        except Exception as e:
            op["payload"]["error"] = str(e)
            restantes.append(op)

    _save_queue(restantes)
    if not restantes:
        _clear_offline_flag()
    return procesadas


def hay_pendientes_offline() -> bool:
    return bool(_load_queue())


def obtener_historial_logs(dni: str, limite: int = 5):
    try:
        registros = _logs_sheet.get_all_records()
    except Exception:
        return []
    filtrados = [r for r in registros if str(r.get("DNI")) == str(dni)]
    filtrados.sort(key=lambda x: x.get("Fecha", ""), reverse=True)
    return filtrados[:limite]
