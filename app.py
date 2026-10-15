import os, sqlite3, hashlib, hmac, secrets, calendar
from datetime import date, datetime, timedelta
from io import BytesIO
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title='TLOG | Gestão de Atividades', page_icon='📊', layout='wide', initial_sidebar_state='expanded')
DB = os.environ.get('TLOG_DB_PATH', os.path.join(os.path.dirname(__file__), 'atividades.db'))

CSS = """
<style>
/* Fundo principal */
[data-testid="stAppViewContainer"] {
    background-color: #F3F5FA !important;
    color: #18243C !important;
}

/* Área central */
[data-testid="stAppViewContainer"] .block-container {
    padding-top: 4rem !important;
    padding-bottom: 2rem !important;
    max-width: 1550px !important;
}

/* Textos gerais */
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 {
    color: #18243C;
}

/* Barra lateral */
[data-testid="stSidebar"] {
    background-color: #10182E !important;
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
    color: #FFFFFF !important;
}

/* Campos e seletores */
[data-baseweb="input"] input,
[data-baseweb="select"] > div,
textarea {
    background-color: #FFFFFF !important;
    color: #18243C !important;
}

/* Rótulos */
[data-testid="stWidgetLabel"] p {
    color: #26364F !important;
    font-weight: 500 !important;
}

/* Abas */
button[data-baseweb="tab"] {
    color: #26364F !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #607BF0 !important;
}

/* Cabeçalho TLOG */
.tlog-head {
    background: #10182E !important;
    color: #FFFFFF !important;
    border-radius: 9px;
    padding: 18px 24px;
    margin-bottom: 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.tlog-head * {
    color: #FFFFFF !important;
}

/* Banner principal */
.tlog-banner {
    background: linear-gradient(
        105deg, #607BF0, #7C4AA7
    ) !important;
    border-radius: 11px;
    padding: 24px;
    margin-bottom: 20px;
}

.tlog-banner,
