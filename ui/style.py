import streamlit as st

def aplicar_estilos():
    st.markdown(
        """
        <style>
        /* --- Fondo general --- */
        .stApp {
            background: linear-gradient(135deg, #000000, #380000, #8B0000);
            color: white;
            font-family: 'Helvetica Neue', sans-serif;
            padding: 2rem 1.5rem;
        }

        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
        }

        /* --- Etiquetas e inputs --- */
        label, .stTextInput label, .stSelectbox label, .stForm label {
            color: rgba(255, 255, 255, 0.9) !important;
            font-weight: 600;
            font-size: 1.1rem;
        }

        .stTextInput > div > div > input,
        .stSelectbox > div > div > select,
        .stDateInput input {
            background-color: #1a1a1a !important;
            color: white !important;
            border: 2px solid #ff4b4b !important;
            border-radius: 10px;
            padding: 0.9rem 1rem;
            font-size: 1.1rem;
        }

        .stSelectbox div[data-baseweb="select"] > div {
            min-height: 60px;
        }

        .css-1inq1f2, .css-16idsys, .css-1v3fvcr {
            font-size: 1.05rem !important;
        }

        /* --- Botones --- */
        div.stButton > button {
            background-color: #ff4b4b;
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: bold;
            transition: all 0.2s ease-in-out;
            padding: 0.9rem 1.5rem;
            width: 100%;
            font-size: 1.05rem;
        }

        div.stButton > button:hover {
            background-color: #ff1e1e;
            transform: scale(1.03);
        }

        /* --- Títulos --- */
        h1, h2, h3 {
            color: #ffffff;
            text-align: center;
            font-weight: bold;
        }

        /* --- Encabezado con logo --- */
        .header-container {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 18px;
            margin-bottom: 25px;
            margin-top: 50px;
        }

        .header-logo {
            width: 70px;
            height: 70px;
            border-radius: 50%;
            object-fit: contain;
            border: 2px solid #ff4b4b;
            transition: all 0.3s ease-in-out;
            box-shadow: 0 0 10px rgba(255, 75, 75, 0.6);
        }

        .header-logo:hover {
            transform: scale(1.08);
            border-color: #ff1e1e;
            box-shadow: 0 0 20px rgba(255, 75, 75, 0.8);
        }

        .header-title {
            font-size: 2.2em;
            font-weight: 900;
            letter-spacing: 1px;
            color: white;
            text-shadow: 0 0 10px rgba(255,255,255,0.3);
        }

        /* --- Texto del checkbox en blanco --- */
        .stCheckbox div[data-testid="stMarkdownContainer"] p {
            color: white !important;
        }

        /* --- Métricas del dashboard en blanco --- */
        div[data-testid="stMetric"] div[data-testid="stMetricLabel"],
        div[data-testid="stMetric"] div[data-testid="stMetricValue"],
        div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
