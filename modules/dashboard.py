# modules/dashboard.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, date

from core.data_manager import cargar_datos


def _configurar_figura():
    fig, ax = plt.subplots()
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    return fig, ax


def grafico_tipo_plan(df):
    st.subheader("🥋 Distribución por tipo de plan")
    if "Plan contratado" not in df.columns or df["Plan contratado"].dropna().empty:
        st.info("No hay datos de planes para mostrar el gráfico.")
        return

    plan_counts = df["Plan contratado"].value_counts()
    fig, ax = _configurar_figura()
    ax.pie(
        plan_counts.values,
        labels=plan_counts.index,
        autopct="%1.1f%%",
        startangle=90,
        textprops={"color": "white", "fontsize": 11},
    )
    ax.axis("equal")
    st.pyplot(fig)
    st.caption("Participación de cada tipo de plan en el total de socios.")


def grafico_disciplinas(df):
    st.subheader("🥊 Distribución por disciplina")
    if "Disciplina" not in df.columns or df["Disciplina"].dropna().empty:
        st.info("No hay datos de disciplinas para generar este gráfico.")
        return
    counts = df["Disciplina"].value_counts()
    fig, ax = _configurar_figura()
    counts.plot(kind="bar", ax=ax, color="#ff4b4b")
    ax.set_ylabel("Número de socios", color="white")
    ax.tick_params(axis="x", rotation=25, colors="white")
    ax.tick_params(axis="y", colors="white")
    for idx, val in enumerate(counts.values):
        ax.text(idx, val + 0.5, f"{val}", ha="center", color="white")
    st.pyplot(fig)


def grafico_planes_populares(df):
    st.subheader("🏆 Planes más contratados")
    columna = "Plan contratado"
    if columna not in df.columns or df[columna].dropna().empty:
        st.info("No hay datos suficientes de planes contratados.")
        return
    counts = df[columna].value_counts().sort_values(ascending=True)
    fig, ax = _configurar_figura()
    counts.plot(kind="barh", ax=ax, color="#ff884b")
    ax.set_xlabel("Socios", color="white")
    ax.tick_params(axis="y", colors="white")
    ax.tick_params(axis="x", colors="white")
    for idx, val in enumerate(counts.values):
        ax.text(val + 0.2, idx, f"{val}", color="white")
    st.pyplot(fig)
    st.caption("Ranking de los planes más populares.")


def grafico_estado_pago(df):
    st.subheader("💳 Estado de pago actual")
    if "Estado de pago" not in df.columns or df["Estado de pago"].dropna().empty:
        st.info("No hay datos de estado de pago.")
        return
    counts = df["Estado de pago"].value_counts()
    fig, ax = _configurar_figura()
    wedges, _, autotexts = ax.pie(
        counts.values,
        labels=counts.index,
        autopct="%1.1f%%",
        startangle=90,
        textprops={"color": "white"},
        wedgeprops=dict(width=0.4),
    )
    ax.axis("equal")
    st.pyplot(fig)


def grafico_altas_bajas(df):
    st.subheader("📅 Altas vs bajas por mes")
    if "Fecha de alta" not in df.columns or not df["Fecha de alta"].notna().any():
        st.info("No hay datos suficientes para calcular las altas.")
        return

    df["Fecha de alta"] = pd.to_datetime(df["Fecha de alta"], errors="coerce")
    df["Mes alta"] = df["Fecha de alta"].dt.to_period("M").astype(str)
    altas = df.groupby("Mes alta").size()

    bajas = None
    if "Fecha de baja" in df.columns:
        df["Fecha de baja"] = pd.to_datetime(df["Fecha de baja"], errors="coerce")
        df["Mes baja"] = df["Fecha de baja"].dt.to_period("M").astype(str)
        bajas = df.dropna(subset=["Fecha de baja"]).groupby("Mes baja").size()

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_alpha(0)
    ax.plot(altas.index, altas.values, label="Altas", marker="o", color="#4CAF50")
    if bajas is not None and not bajas.empty:
        ax.plot(bajas.index, bajas.values, label="Bajas", marker="o", color="#FF6B6B")
    ax.set_xlabel("Mes", color="white")
    ax.set_ylabel("Nº movimientos", color="white")
    ax.tick_params(axis="x", rotation=45, colors="white")
    ax.tick_params(axis="y", colors="white")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)
    st.pyplot(fig)


def grafico_hist_edades(df):
    st.subheader("🎯 Distribución de edades")
    if "Fecha nacimiento" not in df.columns:
        st.info("No hay datos de fecha de nacimiento para calcular edades.")
        return
    fechas = pd.to_datetime(df["Fecha nacimiento"], errors="coerce")
    edades = []
    for fecha in fechas.dropna():
        edad = date.today().year - fecha.year - (
            (date.today().month, date.today().day) < (fecha.month, fecha.day)
        )
        if edad >= 0:
            edades.append(edad)

    if not edades:
        st.info("No hay edades válidas para mostrar.")
        return

    bins = range(0, max(edades) + 5, 5)
    fig, ax = _configurar_figura()
    ax.hist(edades, bins=bins, color="#2ecc71", edgecolor="white", alpha=0.8)
    ax.set_xlabel("Edad", color="white")
    ax.set_ylabel("Número de socios", color="white")
    st.pyplot(fig)


def mostrar_dashboard():
    st.title("📊 Estadísticas del gimnasio")

    df = cargar_datos()
    if df.empty:
        st.warning("No hay datos disponibles todavía.")
        return

    df["Fecha de alta"] = pd.to_datetime(df["Fecha de alta"], errors="coerce")

    total_socios = len(df)
    activos = (df["Estado"] == "Activo").sum()
    de_baja = (df["Estado"] == "Baja").sum()
    altas_30 = (df["Fecha de alta"] >= datetime.now() - timedelta(days=30)).sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("👥 Total socios", total_socios)
    col2.metric("🟢 Activos", int(activos))
    col3.metric("🔴 De baja", int(de_baja))
    col4.metric("🆕 Altas últimos 30 días", int(altas_30))

    st.markdown("---")
    grafico_tipo_plan(df)
    st.markdown("---")
    grafico_disciplinas(df)
    st.markdown("---")
    grafico_planes_populares(df)
    st.markdown("---")
    grafico_estado_pago(df)
    st.markdown("---")
    grafico_altas_bajas(df)
    st.markdown("---")
    grafico_hist_edades(df)
