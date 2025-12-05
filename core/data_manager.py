# core/data_manager.py
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import pandas as pd
from pathlib import Path
import json
import os
import io
import csv
from datetime import datetime, timedelta
import pytz
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# --- Configuración ---
# Scopes OAuth para Drive (subida/listado de archivos creados) y Sheets (lectura/escritura).
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]
BASE_DIR = Path(__file__).resolve().parents[1]
OAUTH_CREDS_PATH = BASE_DIR / "oauth_credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
SHEET_NAME = "socios_gimnasio"
QUEUE_PATH = BASE_DIR / "offline_queue.json"
DRIVE_FOLDER_NAME = "FIRMAS_PDF"
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
BACKUP_SHEETS_FOLDER_NAME = "BACKUPS_SHEETS"
_credentials = None
_sheets_service = None
_drive_service = None
_spreadsheet_id_cache = None
_sheet_title_cache = None
LAST_BACKUP_SHEETS_FILENAME = "last_backup_sheets.txt"


def fecha_hoy_madrid() -> str:
    tz = pytz.timezone("Europe/Madrid")
    return datetime.now(tz).strftime("%d-%m-%Y")

def _load_json_from_env(env_var: str):
    raw = os.environ.get(env_var)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _save_token_if_local(creds: Credentials):
    # Solo guardamos token.json si estamos trabajando con archivo local
    try:
        data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
        }
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # En entornos donde no se quiera escribir, simplemente se omite.
        pass


def _load_credentials() -> Credentials:
    """
    Carga credenciales OAuth desde:
    - Variables de entorno (OAUTH_TOKEN_JSON y OAUTH_CREDENTIALS_JSON), o
    - Archivos locales token.json y oauth_credentials.json.
    Refresca el token si es necesario.
    """
    global _credentials
    if _credentials and _credentials.valid:
        return _credentials

    token_data = _load_json_from_env("OAUTH_TOKEN_JSON")
    creds_info = _load_json_from_env("OAUTH_CREDENTIALS_JSON")

    # Fallback a archivos locales si no hay variables
    if token_data is None and TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, "r", encoding="utf-8") as f:
                token_data = json.load(f)
        except Exception:
            token_data = None

    if creds_info is None and OAUTH_CREDS_PATH.exists():
        try:
            with open(OAUTH_CREDS_PATH, "r", encoding="utf-8") as f:
                creds_info = json.load(f)
        except Exception:
            creds_info = None

    if token_data is None:
        raise RuntimeError("No se encontraron credenciales OAuth (token.json / OAUTH_TOKEN_JSON). Ejecuta autoriza_oauth.py.")

    creds = Credentials.from_authorized_user_info(token_data, scopes=SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token_if_local(creds)
        else:
            raise RuntimeError("Credenciales OAuth inválidas o sin refresh token. Ejecuta autoriza_oauth.py de nuevo.")

    _credentials = creds
    return _credentials

# --- Esquema fijo ---
COLUMNS = [
    "Nombre",
    "Apellidos",
    "DNI",
    "Teléfono",
    "Email",
    "Disciplina",
    "Plan contratado",
    "Precio",
    "Fecha nacimiento",
    "Fecha de alta",
    "Banco",
    "Titular",
    "IBAN",
    "Localidad",
    "Estado",
    "Estado de pago",
    "Fecha último pago",
    "URL PDF Consentimiento",
    "URL Doc WhatsApp",
    "URL Doc Publicidad",
    "URL Doc Menor14",
    "URL Doc 14-18",
]

COLUMN_SYNONYMS = {
    "plan": "Plan contratado",
    "plan contratado": "Plan contratado",
    "plancontratado": "Plan contratado",
    "plan_contratado": "Plan contratado",
}

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


def _canonical_column_name(nombre: str) -> str:
    """
    Limpia el nombre de columna y devuelve la forma canónica esperada.
    Actualmente se enfoca en asegurar el uso único de «Plan contratado».
    """
    if not nombre:
        return nombre
    limpio = " ".join(nombre.strip().replace("_", " ").split())
    clave = limpio.lower()
    return COLUMN_SYNONYMS.get(clave, limpio)


def _normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Renombra columnas con alias conocidos al esquema oficial y consolida duplicadas.
    Evita que coexistan columnas como «Plan» y «Plan contratado».
    """
    if df is None:
        return df

    df = df.copy()
    columnas_originales = list(df.columns)
    for col in columnas_originales:
        canonica = _canonical_column_name(col)
        if canonica == col:
            continue
        if canonica in df.columns:
            destino = df[canonica]
            mask = destino.isna() | (destino.astype(str).str.strip() == "")
            df.loc[mask, canonica] = df.loc[mask, col]
            df.drop(columns=[col], inplace=True)
        else:
            df.rename(columns={col: canonica}, inplace=True)
    return df


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garantiza la presencia y el orden del esquema fijo."""
    if df is None:
        df = _empty_dataframe()
    df = _normalize_dataframe_columns(df)
    df = df.copy()
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[COLUMNS]


def _flush_dataframe(df: pd.DataFrame) -> None:
    df = _ensure_columns(df)
    data_rows = df.fillna("").astype(str).values.tolist() if not df.empty else []
    spreadsheet_id = _get_spreadsheet_id()
    sheet_title = _get_sheet_title(spreadsheet_id)
    service = _get_sheets_service()

    # Limpiar rango actual (encabezados + datos)
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!A:Z",
    ).execute()

    if data_rows:
        values = [COLUMNS] + data_rows
    else:
        values = [COLUMNS]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()


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
        plan = str(row.get("Plan contratado", "")).strip()
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
        spreadsheet_id = _get_spreadsheet_id()
        sheet_title = _get_sheet_title(spreadsheet_id)
        service = _get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_title}!A:Z",
        ).execute()
        values = result.get("values", [])
    except Exception:
        return _empty_dataframe()

    if not values:
        return _empty_dataframe()

    header = values[0]
    rows = values[1:] if len(values) > 1 else []
    # Normaliza el número de columnas por fila para evitar errores de longitud.
    safe_rows = []
    num_cols = len(header)
    for r in rows:
        if len(r) < num_cols:
            r = r + [""] * (num_cols - len(r))
        elif len(r) > num_cols:
            r = r[:num_cols]
        safe_rows.append(r)

    df = pd.DataFrame(safe_rows, columns=header)
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
        timestamp = pd.Timestamp.now(tz=pytz.timezone("Europe/Madrid")).strftime("%d-%m-%Y %H:%M:%S")
        fila = [timestamp, usuario or "desconocido", accion, dni, detalle]
        spreadsheet_id = _get_spreadsheet_id()
        _ensure_logs_sheet(spreadsheet_id)
        service = _get_sheets_service()
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Logs!A:E",
            valueInputOption="RAW",
            body={"values": [fila]},
        ).execute()
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
                timestamp = pd.Timestamp.now(tz=pytz.timezone("Europe/Madrid")).strftime("%d-%m-%Y %H:%M:%S")
                fila = [
                    timestamp,
                    op["payload"].get("usuario") or "desconocido",
                    op["payload"].get("accion"),
                    op["payload"].get("dni"),
                    op["payload"].get("detalle"),
                ]
                registrar_log(
                    usuario=op["payload"].get("usuario"),
                    accion=op["payload"].get("accion"),
                    dni=op["payload"].get("dni"),
                    detalle=op["payload"].get("detalle"),
                )
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
        spreadsheet_id = _get_spreadsheet_id()
        _ensure_logs_sheet(spreadsheet_id)
        service = _get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Logs!A:E",
        ).execute()
        values = result.get("values", [])
        if not values or len(values) < 2:
            return []
        header = values[0]
        rows = values[1:]
        registros = [dict(zip(header, row + [""] * (len(header) - len(row)))) for row in rows]
    except Exception:
        return []
    filtrados = [r for r in registros if str(r.get("DNI")) == str(dni)]
    filtrados.sort(key=lambda x: x.get("Fecha", ""), reverse=True)
    return filtrados[:limite]


def _get_drive_service():
    global _drive_service
    if _drive_service:
        return _drive_service
    creds = _load_credentials()
    _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_service


def _get_sheets_service():
    global _sheets_service
    if _sheets_service:
        return _sheets_service
    creds = _load_credentials()
    _sheets_service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return _sheets_service


def _find_spreadsheet_id_by_name(name: str) -> str:
    service = _get_drive_service()
    query = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    )
    result = service.files().list(q=query, fields="files(id, name)", pageSize=1).execute()
    files = result.get("files", [])
    if not files:
        raise FileNotFoundError(f"No se encontró la hoja de cálculo con nombre {name}")
    return files[0]["id"]


def _get_spreadsheet_id() -> str:
    global _spreadsheet_id_cache
    if _spreadsheet_id_cache:
        return _spreadsheet_id_cache
    if SPREADSHEET_ID:
        _spreadsheet_id_cache = SPREADSHEET_ID
        return _spreadsheet_id_cache
    _spreadsheet_id_cache = _find_spreadsheet_id_by_name(SHEET_NAME)
    return _spreadsheet_id_cache


def _get_sheet_title(spreadsheet_id: str) -> str:
    global _sheet_title_cache
    if _sheet_title_cache:
        return _sheet_title_cache
    service = _get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = meta.get("sheets", [])
    if not sheets:
        raise RuntimeError("La hoja de cálculo no tiene pestañas.")
    _sheet_title_cache = sheets[0]["properties"]["title"]
    return _sheet_title_cache


def _ensure_logs_sheet(spreadsheet_id: str, logs_title: str = "Logs"):
    service = _get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = meta.get("sheets", [])
    exists = any(s["properties"]["title"] == logs_title for s in sheets)
    if exists:
        return
    body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": logs_title,
                        "gridProperties": {"rowCount": 1000, "columnCount": 5},
                    }
                }
            }
        ]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
    # Añadir cabeceras
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{logs_title}!A1:E1",
        valueInputOption="RAW",
        body={"values": [["Fecha", "Usuario", "Acción", "DNI", "Detalle"]]},
    ).execute()


def _ensure_drive_folder(folder_name: str) -> str:
    """
    Obtiene el ID de la carpeta de Drive donde se alojan los PDFs.
    - Si existe la variable de entorno DRIVE_FOLDER_ID, la usa directamente (carpeta propiedad del usuario que autorizó).
    - En caso contrario, busca/crea una carpeta con nombre `folder_name` bajo el Drive del usuario OAuth.
    """
    if DRIVE_FOLDER_ID:
        return DRIVE_FOLDER_ID

    service = _get_drive_service()
    query = (
        f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = service.files().list(q=query, fields="files(id, name)", pageSize=1).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    # Creará la carpeta bajo la cuenta del usuario OAuth
    file_metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    created = service.files().create(body=file_metadata, fields="id").execute()
    return created["id"]


def _ensure_drive_folder_named(folder_name: str, parent_id: str | None = None) -> str:
    """Crea/obtiene una carpeta por nombre (opcionalmente dentro de un parent)."""
    service = _get_drive_service()
    parent_clause = f" and '{parent_id}' in parents" if parent_id else ""
    query = (
        f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false{parent_clause}"
    )
    res = service.files().list(q=query, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    created = service.files().create(body=metadata, fields="id").execute()
    return created["id"]


def leer_fecha_ultimo_backup() -> str | None:
    """Lee la fecha del último backup desde last_backup_sheets.txt en Drive. Devuelve None si no existe."""
    try:
        service = _get_drive_service()
        backup_folder = _ensure_drive_folder_named(BACKUP_SHEETS_FOLDER_NAME)
        query = (
            f"'{backup_folder}' in parents and name = '{LAST_BACKUP_SHEETS_FILENAME}' "
            f"and trashed = false"
        )
        res = service.files().list(q=query, fields="files(id,name)", pageSize=1).execute()
        files = res.get("files", [])
        if not files:
            return None
        file_id = files[0]["id"]
        request = service.files().get_media(fileId=file_id)
        file_bytes = io.BytesIO()
        downloader = MediaIoBaseDownload(file_bytes, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_bytes.seek(0)
        contenido = file_bytes.read().decode("utf-8").strip()
        return contenido or None
    except Exception as e:
        print(f"[WARN] No se pudo leer la fecha del último backup: {e}")
        return None


def guardar_fecha_ultimo_backup(fecha_str: str) -> None:
    """Guarda la fecha del último backup en last_backup_sheets.txt en Drive."""
    try:
        service = _get_drive_service()
        backup_folder = _ensure_drive_folder_named(BACKUP_SHEETS_FOLDER_NAME)
        media = MediaIoBaseUpload(io.BytesIO(fecha_str.encode("utf-8")), mimetype="text/plain", resumable=False)
        metadata = {"name": LAST_BACKUP_SHEETS_FILENAME, "parents": [backup_folder]}

        # Si ya existe, eliminarlo antes de crear el nuevo
        query = (
            f"'{backup_folder}' in parents and name = '{LAST_BACKUP_SHEETS_FILENAME}' "
            f"and trashed = false"
        )
        res = service.files().list(q=query, fields="files(id,name)", pageSize=1).execute()
        files = res.get("files", [])
        if files:
            service.files().delete(fileId=files[0]["id"]).execute()

        service.files().create(body=metadata, media_body=media, fields="id").execute()
    except Exception as e:
        print(f"[WARN] No se pudo guardar la fecha del último backup: {e}")


def ensure_person_folder(nombre: str, apellidos: str, dni: str) -> str:
    """
    Crea (o recupera) una carpeta específica del socio dentro de la carpeta principal.
    Nombre de carpeta: "{Nombre} {Apellidos}_{DNI}".
    """
    base_folder_id = _ensure_drive_folder(DRIVE_FOLDER_NAME)
    service = _get_drive_service()
    folder_name = f"{nombre} {apellidos}_{dni}"
    query = (
        f"'{base_folder_id}' in parents and name = '{folder_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = service.files().list(q=query, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [base_folder_id],
    }
    created = service.files().create(body=metadata, fields="id").execute()
    return created["id"]


def upload_pdf_to_drive(pdf_bytes: bytes, filename: str, folder_id: str = None) -> str:
    """
    Sube pdf_bytes a una carpeta fija de Drive y devuelve la URL de visualización.
    """
    try:
        folder_id = folder_id or _ensure_drive_folder(DRIVE_FOLDER_NAME)
        service = _get_drive_service()
        media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=False)
        file_metadata = {"name": filename, "parents": [folder_id]}
        created = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
            .execute()
        )
        file_id = created.get("id")
        if not file_id:
            return ""
        return f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"
    except Exception as e:
        print(f"[WARN] Error subiendo PDF a Drive: {e}")
        return ""


def crear_backup_diario_sheets():
    """Genera un CSV de la hoja principal y lo guarda en BACKUPS_SHEETS con fecha YYYY-MM-DD."""
    try:
        if not SPREADSHEET_ID:
            print("[WARN] No se ha definido SPREADSHEET_ID, no se puede crear backup de Sheets.")
            return
        sheets_service = _get_sheets_service()
        drive_service = _get_drive_service()
        backup_folder = _ensure_drive_folder_named(BACKUP_SHEETS_FOLDER_NAME)

        # Leer la hoja principal
        sheet_title = _get_sheet_title(_get_spreadsheet_id())
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_title}!A:Z",
        ).execute()
        values = result.get("values", [])

        # Convertir a CSV en memoria
        output = io.StringIO()
        writer = csv.writer(output)
        for row in values:
            writer.writerow(row)
        csv_data = output.getvalue()
        output.close()

        nombre_backup = f"socios_gimnasio_backup_{fecha_hoy_madrid()}.csv"
        media = MediaIoBaseUpload(io.BytesIO(csv_data.encode("utf-8")), mimetype="text/csv", resumable=False)
        file_metadata = {"name": nombre_backup, "parents": [backup_folder]}
        drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        print(f"[INFO] Backup diario de Sheets creado: {nombre_backup}")
    except Exception as e:
        print(f"[WARN] Backup diario de Sheets falló: {e}")


def limpiar_backups_antiguos():
    """Elimina backups antiguos: Sheets >30 días."""
    try:
        service = _get_drive_service()
        # Sheets (30 días)
        folder_sheets = _ensure_drive_folder_named(BACKUP_SHEETS_FOLDER_NAME)
        limite_sheets = datetime.utcnow() - timedelta(days=30)
        res = service.files().list(
            q=f"'{folder_sheets}' in parents and trashed = false",
            fields="files(id, name, createdTime)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        for f in res.get("files", []):
            try:
                fecha = datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00"))
                if fecha < limite_sheets:
                    service.files().delete(fileId=f["id"], supportsAllDrives=True).execute()
            except Exception:
                continue
    except Exception as e:
        print(f"[WARN] Limpieza de backups falló: {e}")


# --- Inicialización sencilla para validar conexión al arranque ---
try:
    _get_sheets_service()
    _get_spreadsheet_id()
    _get_sheet_title(_get_spreadsheet_id())
    _ensure_logs_sheet(_get_spreadsheet_id())
except Exception as e:
    import streamlit as st
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()
