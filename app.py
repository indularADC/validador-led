import pandas as pd
import streamlit as st
import google.genai as genai
import json
import os
from datetime import datetime
from thefuzz import fuzz
from PIL import Image
import io
import sqlite3

# ───────── 1. CONFIGURACIÓN DE PÁGINA ─────────
st.set_page_config(page_title="Validador LED", layout="wide", initial_sidebar_state="collapsed")



st.markdown("""
<style>
/* Contraste botón minimizar/expandir barra lateral */
button[kind="header"],
button[data-testid="collapsedControl"],
button[data-testid="baseButton-header"] {
    background-color: #ffffff !important;
    color: #111827 !important;
    border: 1px solid #cbd5e1 !important;
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.18) !important;
}

button[kind="header"] svg,
button[data-testid="collapsedControl"] svg,
button[data-testid="baseButton-header"] svg {
    fill: #111827 !important;
    stroke: #111827 !important;
}
</style>
""", unsafe_allow_html=True)


st.markdown("""
<style>
/* Mejor contraste botones Subir archivo / Tomar foto */
div[data-baseweb="tab-list"] button {
    background-color: #ffffff !important;
    color: #1f2937 !important;
    border: 1px solid #cbd5e1 !important;
    font-weight: 700 !important;
}

div[data-baseweb="tab-list"] button p,
div[data-baseweb="tab-list"] button span {
    color: #1f2937 !important;
    font-weight: 700 !important;
}

div[data-baseweb="tab-list"] button[aria-selected="true"] {
    background-color: #f97316 !important;
    color: #ffffff !important;
    border-color: #f97316 !important;
}

div[data-baseweb="tab-list"] button[aria-selected="true"] p,
div[data-baseweb="tab-list"] button[aria-selected="true"] span {
    color: #ffffff !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)


# ───────── 2. CONFIGURACIÓN ─────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "auditoria_escaneos.db")
COMBINACIONES_JSON = os.path.join(BASE_DIR, "combinaciones_validas.json")
API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

# ───────── 3. SESSION STATE ─────────
def init_state():
    defaults = {
        "driver_extraido": None,
        "driver_match": None,
        "modelos_disponibles": [],
        "imagen_bytes": None,
        "imagen_origen": None,
        "validacion_ok": False,
        "ultima_validacion_disparada": False,
        "last_params": None,
        "last_placas_input": None,
        "last_paralelos": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

# ───────── 4. ESTILOS ─────────
st.markdown("""
<style>
:root {
    --bg: #f4f6f8;
    --card: #ffffff;
    --text: #17202a;
    --muted: #667085;
    --line: #e4e7ec;
    --primary: #f26b21;
    --primary-dark: #c84f12;
    --success: #14804a;
    --danger: #b42318;
    --info: #175cd3;
}

html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg);
}

[data-testid="stHeader"] {
    background: rgba(244, 246, 248, 0.85);
    backdrop-filter: blur(8px);
}

.block-container {
    padding-top: 1.4rem;
    padding-bottom: 2rem;
    max-width: 1180px;
}

.app-hero {
    background: linear-gradient(135deg, #1d2939 0%, #344054 62%, #f26b21 100%);
    color: white;
    border-radius: 22px;
    padding: 26px 30px;
    margin-bottom: 18px;
    box-shadow: 0 14px 34px rgba(16, 24, 40, .16);
}

.app-title {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.035em;
    margin: 0 0 6px 0;
}

.app-subtitle {
    color: rgba(255,255,255,.82);
    font-size: .98rem;
    margin: 0;
    max-width: 850px;
}

.step-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-bottom: 18px;
}

.step-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 15px 16px;
    box-shadow: 0 4px 12px rgba(16, 24, 40, .05);
}

.step-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border-radius: 999px;
    background: #fff1e8;
    color: var(--primary-dark);
    font-weight: 800;
    font-size: .82rem;
    margin-right: 8px;
}

.step-title {
    font-size: .9rem;
    color: var(--text);
    font-weight: 800;
}

.step-desc {
    margin-top: 8px;
    color: var(--muted);
    font-size: .78rem;
    line-height: 1.35;
}

.card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 18px;
    margin-bottom: 16px;
    box-shadow: 0 5px 16px rgba(16, 24, 40, .055);
}

.card-title {
    font-size: 1rem;
    font-weight: 800;
    color: var(--text);
    margin-bottom: 6px;
}

.card-help {
    color: var(--muted);
    font-size: .82rem;
    margin-bottom: 12px;
}

.status-ok, .status-error, .status-info {
    border-radius: 14px;
    padding: 14px 16px;
    font-size: .9rem;
    font-weight: 800;
    margin: 12px 0;
}
.status-ok {background: #ecfdf3; color: var(--success); border: 1px solid #abefc6;}
.status-error {background: #fef3f2; color: var(--danger); border: 1px solid #fecdca;}
.status-info {background: #eff8ff; color: var(--info); border: 1px solid #b2ddff;}

.driver-pill {
    display: inline-block;
    background: #101828;
    color: #ffffff;
    border-radius: 999px;
    padding: 9px 14px;
    font-size: .86rem;
    font-weight: 800;
    margin-top: 4px;
}

.preview-img img {
    border-radius: 14px;
    border: 1px solid var(--line);
}

[data-testid="stSidebar"] {
    background: #101828;
}
[data-testid="stSidebar"] * {
    color: white !important;
}
[data-testid="stSidebar"] input {
    color: #101828 !important;
    background: white !important;
}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] [data-testid="stWidgetLabel"], [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: white !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
}
.stTabs [data-baseweb="tab"] {
    background: #ffffff;
    border-radius: 999px;
    padding: 8px 16px;
    border: 1px solid var(--line);
    height: auto;
}
.stTabs [aria-selected="true"] {
    background: #fff1e8 !important;
    color: var(--primary-dark) !important;
    border-color: #ffd6bd !important;
}

.stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] button {
    border-radius: 12px !important;
    border: 0 !important;
    font-weight: 800 !important;
    min-height: 42px;
}

.stButton > button[kind="primary"], div[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: var(--primary) !important;
    color: white !important;
}

.stButton > button:hover, div[data-testid="stFormSubmitButton"] button:hover {
    filter: brightness(.97);
}

input, textarea, select, [data-baseweb="select"] > div {
    border-radius: 11px !important;
}

/* Contraste de etiquetas y campos en fondo claro */
label, [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p {
    color: #17202a !important;
    font-weight: 750 !important;
}
[data-testid="stNumberInput"] label, [data-testid="stSelectbox"] label {
    color: #17202a !important;
}
[data-baseweb="select"] span, [data-baseweb="select"] div {
    color: #17202a !important;
}
[data-testid="stNumberInput"] input {
    color: #17202a !important;
    background: #ffffff !important;
}

.plate-card {
    border: 1px solid var(--line);
    border-radius: 15px;
    padding: 12px 12px 10px 12px;
    margin-bottom: 10px;
    background: #ffffff;
}
.plate-title {
    color: var(--text);
    font-weight: 900;
    font-size: .9rem;
    margin-bottom: 7px;
}
.qty-label {
    color: var(--muted);
    font-size: .78rem;
    font-weight: 800;
    margin-top: 8px;
    margin-bottom: 3px;
}
.qty-row .stButton button {
    min-height: 38px !important;
    border: 1px solid var(--line) !important;
    background: #f9fafb !important;
    color: #17202a !important;
}
.qty-row [data-testid="stNumberInput"] input {
    min-height: 38px !important;
}

.param-table table {
    border-radius: 14px;
    overflow: hidden;
}

/* Contraste adicional: botón/expander de imagen y selectores */
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p {
    color: #17202a !important;
    font-weight: 800 !important;
}
[data-testid="stExpander"] button, [data-testid="stExpander"] svg {
    color: #17202a !important;
}
[data-baseweb="select"] > div {
    background: #ffffff !important;
    border: 1px solid #d0d5dd !important;
}
[data-baseweb="select"] input, [data-baseweb="select"] span, [data-baseweb="select"] div {
    color: #17202a !important;
    -webkit-text-fill-color: #17202a !important;
}
.plate-table {
    border: 1px solid var(--line);
    border-radius: 15px;
    overflow: hidden;
    background: #ffffff;
    margin-bottom: 12px;
}
.plate-table-head {
    display: grid;
    grid-template-columns: 1.9fr 1fr;
    background: #f2f4f7;
    border-bottom: 1px solid var(--line);
}
.plate-table-head div {
    color: #17202a;
    font-size: .78rem;
    font-weight: 900;
    padding: 10px 12px;
}
.plate-row {
    border-bottom: 1px solid #eef0f3;
    padding: 8px 0;
}
.plate-row:last-child {border-bottom: 0;}
.qty-control {
    display: grid;
    grid-template-columns: 38px 1fr 38px;
    align-items: center;
    border: 1px solid #d0d5dd;
    border-radius: 11px;
    overflow: hidden;
    min-height: 42px;
    background: #ffffff;
}
.qty-display {
    text-align: center;
    color: #17202a;
    font-weight: 900;
    font-size: 1rem;
}
.qty-control .stButton button {
    min-height: 40px !important;
    border-radius: 0 !important;
    border: 0 !important;
    background: #f9fafb !important;
    color: #17202a !important;
    font-size: 1.05rem !important;
    font-weight: 900 !important;
}
.qty-control .stButton button:hover {background: #eef2f6 !important;}
.qty-control-minus .stButton button {color: #b42318 !important; background: #fff7f7 !important;}
.qty-control-plus .stButton button {color: #087443 !important; background: #f6fef9 !important;}



.step-done {border-color: #abefc6; background: #ecfdf3;}
.step-done .step-number {background: var(--success); color: white;}
.step-pending {opacity: .72;}
.chain-row {margin-top: -4px; margin-bottom: 14px;}
.compact-card {padding: 14px 16px; margin-bottom: 12px;}
.photo-summary {background: #f9fafb; border: 1px dashed var(--line); border-radius: 14px; padding: 10px 12px; color: var(--muted); font-size: .82rem; margin: 8px 0 10px 0;}
[data-testid="stExpander"] {border-radius: 14px !important; border: 1px solid var(--line) !important; background: #ffffff !important;}
div[data-testid="stForm"] {margin-top: -6px;}
div[data-testid="stForm"] [data-testid="column"] {padding-top: 0 !important;}
[data-testid="stNumberInput"] input {min-height: 42px; font-weight: 800; text-align: center;}
.completion-wrap {position: relative; overflow: hidden; border-radius: 18px; padding: 22px; margin: 14px 0; text-align: center; background: linear-gradient(135deg, #ecfdf3, #ffffff); border: 1px solid #abefc6; animation: completePulse 1.25s ease-in-out 2;}
.completion-ring {width: 54px; height: 54px; margin: 0 auto 8px auto; border-radius: 999px; background: var(--success); color: white; display: flex; align-items: center; justify-content: center; font-size: 1.7rem; font-weight: 900; animation: popCheck .55s ease-out both;}
.completion-text {color: var(--success); font-weight: 900; font-size: 1.05rem;}
.completion-subtext {color: var(--muted); font-size: .82rem; margin-top: 4px;}
.completion-wrap:before, .completion-wrap:after {content: ""; position: absolute; width: 8px; height: 8px; border-radius: 999px; background: var(--primary); top: 18px; animation: confettiDrop 1.2s ease-out infinite;}
.completion-wrap:before {left: 22%;}
.completion-wrap:after {right: 22%; animation-delay: .22s;}
@keyframes popCheck {0% {transform: scale(.55); opacity: 0;} 80% {transform: scale(1.08); opacity: 1;} 100% {transform: scale(1); opacity: 1;}}
@keyframes completePulse {0% {box-shadow: 0 0 0 rgba(20,128,74,0);} 50% {box-shadow: 0 0 0 8px rgba(20,128,74,.08);} 100% {box-shadow: 0 0 0 rgba(20,128,74,0);}}
@keyframes confettiDrop {0% {transform: translateY(-8px) rotate(0deg); opacity: 0;} 20% {opacity: 1;} 100% {transform: translateY(70px) rotate(180deg); opacity: 0;}}

@media (max-width: 760px) {
    .app-hero {padding: 20px; border-radius: 18px;}
    .app-title {font-size: 1.45rem;}
    .step-row {grid-template-columns: 1fr;}
    .block-container {padding-left: 1rem; padding-right: 1rem;}
}

/* Ajuste v6: cantidades alineadas y filas compactas */
.plate-table-head {
    display: grid;
    grid-template-columns: 1.65fr .95fr;
    background: #f2f4f7;
    border: 1px solid var(--line);
    border-radius: 12px 12px 0 0;
    overflow: hidden;
    margin-top: 8px;
}
.plate-table-head div {
    color: #17202a !important;
    font-size: .78rem;
    font-weight: 900;
    padding: 8px 10px;
}
.plate-row-compact {
    border-left: 1px solid var(--line);
    border-right: 1px solid var(--line);
    border-bottom: 1px solid #eef0f3;
    background: #ffffff;
    padding: 7px 10px 3px 10px;
}
.plate-row-compact:last-of-type {
    border-radius: 0 0 12px 12px;
}
.plate-row-compact [data-testid="stHorizontalBlock"] {
    align-items: center !important;
}
.plate-row-compact [data-testid="column"] {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}
.plate-row-compact div[data-testid="stSelectbox"] {
    margin-bottom: 0 !important;
}
.plate-row-compact .stButton > button {
    min-height: 34px !important;
    height: 34px !important;
    width: 34px !important;
    padding: 0 !important;
    border-radius: 9px !important;
    border: 1px solid #d0d5dd !important;
    background: #101828 !important;
    color: #ffffff !important;
    font-size: 1rem !important;
    font-weight: 900 !important;
}
.qty-display-inline {
    height: 34px;
    min-height: 34px;
    border: 1px solid #d0d5dd;
    border-radius: 9px;
    background: #ffffff;
    color: #17202a !important;
    font-weight: 900;
    font-size: .95rem;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 34px;
}
[data-baseweb="select"] > div {
    background: #ffffff !important;
    border: 1px solid #98a2b3 !important;
    min-height: 38px !important;
}
[data-baseweb="select"] * {
    color: #17202a !important;
    -webkit-text-fill-color: #17202a !important;
}
[data-testid="stExpander"] summary {
    background: #101828 !important;
    border-radius: 12px !important;
    padding: 10px 14px !important;
}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span, [data-testid="stExpander"] summary svg {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

</style>
""", unsafe_allow_html=True)

# ───────── 5. BASE DE DATOS ─────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS escaneos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, operador TEXT, driver_detectado TEXT,
        config_placas TEXT, paralelos INT, es_valido BOOLEAN,
        parametros TEXT
    )''')
    conn.commit()
    conn.close()


def log_escaneo(operador, driver, config, paralelos, valido, params):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''INSERT INTO escaneos
                    (timestamp, operador, driver_detectado, config_placas, paralelos, es_valido, parametros)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (datetime.now().isoformat(), operador, driver, json.dumps(config), paralelos, valido, json.dumps(params)))
    conn.commit()
    conn.close()

# ───────── 6. VISIÓN IA ─────────
def extraer_driver(img_bytes):
    if not API_KEY:
        st.error("API Key no configurada")
        return None

    client = genai.Client(api_key=API_KEY)
    prompt = """
Eres un experto en identificación de Drivers LED Tridonic y Philips.
Analiza la imagen y extrae el MODELO EXACTO impreso en la etiqueta.

INSTRUCCIONES CRÍTICAS:
1. Lee el texto principal grande. Ignora direcciones pequeñas o códigos de barras (ej: 'Made in China').
2. Presta mucha atención a los números. No inventes. Si ves 'LC 35/200-350/121', escribe eso. No cambies el 35 por un 19.
3. Busca las palabras clave 'flexCC', 'Ip', 'SNC', 'SELV'.
4. Fíjate en la tabla de selección de corriente (SWITCH SETTING) si existe.
   - Si dice '0.25A ON', podría ser parte del modelo.
   - Si dice 'SNC3' o 'SNC4', inclúyelo al final.

EJEMPLOS DE FORMATO ESPERADO:
- "LC 35/200-350/121 flexCC Ip SNC3"
- "CERTA 40W 350mA 115V 230V"

Devuelve SOLO la cadena de texto del modelo. Nada más.
"""

    try:
        img = Image.open(io.BytesIO(img_bytes))
        response = client.models.generate_content(model="models/gemini-3.1-flash-lite", contents=[prompt, img])
        texto_extraido = response.text.strip()
        texto_extraido = texto_extraido.replace('"', '').replace("'", " ").strip()
        return texto_extraido
    except Exception as e:
        st.error(f"Error IA: {e}")
        return None

# ───────── 7. UTILIDADES ─────────
@st.cache_data
def cargar_combinaciones():
    if not os.path.exists(COMBINACIONES_JSON):
        return {}
    with open(COMBINACIONES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def obtener_modelos_placas(combinaciones):
    modelos = set()
    for data in combinaciones.values():
        for comb in data.get("combinaciones_validas", []):
            for p in comb.get("placas", []):
                if p.get("modelo"):
                    modelos.add(p["modelo"])
    return sorted(list(modelos))


def buscar_driver_ia(texto_ia, combinaciones, umbral=75):
    texto_ia = texto_ia.lower()
    mejor_match, mejor_score = None, 0
    for driver_key in combinaciones.keys():
        score = fuzz.partial_ratio(texto_ia, driver_key.lower())
        if score > mejor_score:
            mejor_score, mejor_match = score, driver_key
    return mejor_match if mejor_score >= umbral else None


def guardar_imagen_en_estado(origen, archivo):
    if archivo is None:
        return

    nuevos_bytes = archivo.getvalue()
    if nuevos_bytes != st.session_state.imagen_bytes:
        st.session_state.imagen_bytes = nuevos_bytes
        st.session_state.imagen_origen = origen
        st.session_state.driver_extraido = None
        st.session_state.driver_match = None
        st.session_state.modelos_disponibles = []
        st.session_state.validacion_ok = False
        st.session_state.ultima_validacion_disparada = False
        st.session_state.last_params = None
        st.session_state.last_placas_input = None
        st.session_state.last_paralelos = None


def limpiar_imagen():
    st.session_state.imagen_bytes = None
    st.session_state.imagen_origen = None
    st.session_state.driver_extraido = None
    st.session_state.driver_match = None
    st.session_state.modelos_disponibles = []
    st.session_state.validacion_ok = False
    st.session_state.ultima_validacion_disparada = False


def render_status(tipo, texto):
    clase = {"ok": "status-ok", "error": "status-error", "info": "status-info"}.get(tipo, "status-info")
    st.markdown(f'<div class="{clase}">{texto}</div>', unsafe_allow_html=True)



def render_step_chain():
    img_ok = bool(st.session_state.imagen_bytes)
    driver_ok = bool(st.session_state.driver_match)
    valid_ok = bool(st.session_state.validacion_ok)

    steps = [
        (1, "Imagen cargada correctamente", "Foto nítida, etiqueta completa y buena luz.", img_ok),
        (2, "Driver identificado correctamente", "La IA reconoció el modelo contra la base.", driver_ok),
        (3, "Combinación válida", "Placas y paralelos coinciden con una configuración permitida.", valid_ok),
    ]

    html = '<div class="step-row chain-row">'
    for num, title, desc, ok in steps:
        cls = "step-card step-done" if ok else "step-card step-pending"
        mark = "✓" if ok else str(num)
        html += (
            f'<div class="{cls}">'
            f'<div><span class="step-number">{mark}</span><span class="step-title">{title}</span></div>'
            f'<div class="step-desc">{desc}</div>'
            f'</div>'
        )
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_success_animation():
    st.markdown(
        '<div class="completion-wrap">'
        '<div class="completion-ring">✓</div>'
        '<div class="completion-text">Proceso completo</div>'
        '<div class="completion-subtext">Imagen leída, driver identificado y combinación validada.</div>'
        '</div>',
        unsafe_allow_html=True
    )


def invalidar_validacion():
    st.session_state.validacion_ok = False
    st.session_state.last_params = None
    st.session_state.last_placas_input = None
    st.session_state.last_paralelos = None


def ajustar_cantidad(key, delta):
    actual = int(st.session_state.get(key, 0) or 0)
    st.session_state[key] = max(0, min(20, actual + delta))
    invalidar_validacion()


def render_qty_control(key_cant):
    if key_cant not in st.session_state:
        st.session_state[key_cant] = 0

    col_minus, col_val, col_plus = st.columns([0.48, 0.82, 0.48], gap="small")
    with col_minus:
        st.button("−", key=f"{key_cant}_minus", use_container_width=True, on_click=ajustar_cantidad, args=(key_cant, -1))
    with col_val:
        st.markdown(f'<div class="qty-display-inline">{int(st.session_state.get(key_cant, 0) or 0)}</div>', unsafe_allow_html=True)
    with col_plus:
        st.button("+", key=f"{key_cant}_plus", use_container_width=True, on_click=ajustar_cantidad, args=(key_cant, 1))
    return int(st.session_state.get(key_cant, 0) or 0)


def render_placa_table(modelos):
    st.markdown(
        '<div class="plate-table-head">'
        '<div>Placa seleccionada</div><div>Cantidad</div>'
        '</div>',
        unsafe_allow_html=True
    )

    resultados = []
    for idx in range(1, 5):
        key_mod = f"placa{idx}_mod"
        key_cant = f"placa{idx}_cant"
        if key_cant not in st.session_state:
            st.session_state[key_cant] = 0

        st.markdown('<div class="plate-row-compact">', unsafe_allow_html=True)
        col_mod, col_qty = st.columns([1.65, .95], gap="small", vertical_alignment="center")
        with col_mod:
            modelo = st.selectbox(
                f"Placa {idx}",
                ["--"] + modelos,
                key=key_mod,
                label_visibility="collapsed",
                on_change=invalidar_validacion
            )
        with col_qty:
            cantidad = render_qty_control(key_cant)
        st.markdown('</div>', unsafe_allow_html=True)
        resultados.append((modelo, cantidad))

    return resultados

# ───────── 8. INTERFAZ ─────────
init_db()

st.markdown("""
<div class="app-hero">
    <div class="app-title">Validador Driver + Placas</div>
    <p class="app-subtitle">Lectura asistida por IA para identificar el driver, seleccionar placas y validar combinaciones eléctricas permitidas.</p>
</div>
""", unsafe_allow_html=True)

render_step_chain()

with st.sidebar:
    st.markdown("### Operador")
    operador = st.text_input("Nombre", placeholder="Ingresar operador", label_visibility="collapsed")
    st.markdown("---")
    st.markdown("### Acciones")
    if st.button("Reiniciar lectura", type="secondary", use_container_width=True):
        limpiar_imagen()
        st.rerun()

combinaciones = cargar_combinaciones()
if not combinaciones:
    render_status("error", "No se encontró el archivo combinaciones_validas.json o está vacío.")
    st.stop()

left_col, right_col = st.columns([1.05, .95], gap="large")

with left_col:
    st.markdown('<div class="card compact-card"><div class="card-title">1. Subir imagen</div><div class="card-help">Tomá o subí una foto nítida, con buena luz y la etiqueta completa visible.</div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Subir archivo", "Tomar foto"])

    with tab1:
        uploaded_file = st.file_uploader(
            "Foto del driver",
            type=["jpg", "jpeg", "png"],
            label_visibility="collapsed",
            key="uploaded_file"
        )
        guardar_imagen_en_estado("archivo", uploaded_file)

    with tab2:
        camera_photo = st.camera_input(
            "Tomar foto",
            key="camera_photo",
            label_visibility="collapsed"
        )
        guardar_imagen_en_estado("camara", camera_photo)

    img_bytes = st.session_state.imagen_bytes

    if img_bytes:
        origen = "cámara" if st.session_state.imagen_origen == "camara" else "archivo"
        st.markdown(f'<div class="photo-summary">Imagen cargada desde {origen}. La vista queda minimizada para no ocupar espacio.</div>', unsafe_allow_html=True)
        try:
            img_full = Image.open(io.BytesIO(img_bytes))
            with st.expander("Abrir imagen completa", expanded=False):
                st.markdown('<div class="preview-img">', unsafe_allow_html=True)
                st.image(img_full, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
        except Exception as e:
            render_status("error", f"No se pudo abrir la imagen: {e}")
            limpiar_imagen()
            st.stop()

        col_a, col_b = st.columns([2, 1])
        with col_a:
            extraer = st.button(
                "Extraer driver",
                type="primary",
                use_container_width=True,
                key="btn_extraer_driver",
                disabled=bool(st.session_state.driver_match)
            )
        with col_b:
            if st.button("Cambiar imagen", use_container_width=True):
                limpiar_imagen()
                st.rerun()

        if extraer:
            if not operador:
                render_status("error", "Ingresá el operador en el menú lateral antes de procesar.")
                st.stop()

            imagen_a_procesar = st.session_state.imagen_bytes
            if not imagen_a_procesar:
                render_status("error", "La imagen se perdió durante la recarga. Tomá la foto nuevamente.")
                st.stop()

            with st.spinner("Leyendo etiqueta del driver..."):
                driver_leido = extraer_driver(imagen_a_procesar)

            if driver_leido:
                st.session_state.driver_extraido = driver_leido
                driver_match = buscar_driver_ia(driver_leido, combinaciones)

                if driver_match:
                    st.session_state.driver_match = driver_match
                    st.session_state.modelos_disponibles = obtener_modelos_placas(combinaciones)
                    st.session_state.validacion_ok = False
                    st.session_state.last_params = None
                    st.rerun()
                else:
                    render_status("error", f"Driver no encontrado: {driver_leido}")
                    with st.expander("Ver ejemplos de drivers disponibles"):
                        st.write(list(combinaciones.keys())[:10])
    else:
        render_status("info", "Todavía no hay imagen cargada.")

    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.validacion_ok and st.session_state.last_params:
        render_success_animation()
        params_found = st.session_state.last_params
        params_df = pd.DataFrame({
            "Uled": [f"{params_found['uled']} Vcc"],
            "Pled": [f"{params_found['pled']} VA"],
            "Flujo": [f"{params_found['flujo']} lm"],
            "Plinea": [f"{params_found['plinea']} W" if params_found['plinea'] != "ND" else "ND"],
            "FP": [f"{params_found['fp']}" if params_found['fp'] != "ND" else "ND"],
            "TDH": [f"{params_found['tdh']}%" if params_found['tdh'] != "ND" else "ND"]
        })
        st.markdown('<div class="card compact-card"><div class="card-title">Parámetros de operación</div><div class="param-table">', unsafe_allow_html=True)
        st.table(params_df)
        st.markdown('</div></div>', unsafe_allow_html=True)

with right_col:
    st.markdown('<div class="card compact-card"><div class="card-title">2. Resultado de lectura</div>', unsafe_allow_html=True)

    if st.session_state.driver_match:
        st.markdown(f'<div class="driver-pill">{st.session_state.driver_match}</div>', unsafe_allow_html=True)
        if st.session_state.driver_extraido:
            st.caption(f"Texto leído por IA: {st.session_state.driver_extraido}")
    elif st.session_state.driver_extraido:
        render_status("error", "La IA leyó la etiqueta, pero no se encontró coincidencia en la base.")
        st.caption(f"Texto leído por IA: {st.session_state.driver_extraido}")
    else:
        render_status("info", "El resultado aparecerá acá después de extraer el driver.")

    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.driver_match and st.session_state.modelos_disponibles:
        st.markdown('<div class="card compact-card"><div class="card-title">3. Seleccionar placas y cantidades</div><div class="card-help">Los selectores quedan a la derecha de la imagen. Usá − / + para ajustar cantidades.</div>', unsafe_allow_html=True)

        placa_rows = render_placa_table(st.session_state.modelos_disponibles)
        placa1_mod, placa1_cant = placa_rows[0]
        placa2_mod, placa2_cant = placa_rows[1]
        placa3_mod, placa3_cant = placa_rows[2]
        placa4_mod, placa4_cant = placa_rows[3]

        paralelos = st.number_input("Caminos en paralelo", min_value=1, max_value=10, value=1, step=1, key="paralelos", on_change=invalidar_validacion)
        submitted = st.button("Validar combinación", type="primary", use_container_width=True)

        if submitted:
            if not operador:
                render_status("error", "Ingresá el operador en el menú lateral.")
                st.stop()

            placas_input = []
            for mod, cant in [
                (placa1_mod, placa1_cant),
                (placa2_mod, placa2_cant),
                (placa3_mod, placa3_cant),
                (placa4_mod, placa4_cant),
            ]:
                if mod != "--" and cant > 0:
                    placas_input.append({"modelo": mod, "en_serie": cant})

            if not placas_input:
                render_status("error", "Seleccioná al menos una placa.")
                st.stop()

            placas_input.sort(key=lambda x: x["modelo"])
            driver_data = combinaciones[st.session_state.driver_match]

            match_found = None
            params_found = None

            for comb in driver_data["combinaciones_validas"]:
                json_placas = [p for p in comb["placas"] if p.get("en_serie", 0) > 0]
                json_placas.sort(key=lambda x: x["modelo"])

                if json_placas == placas_input and comb["caminos_paralelo"] == paralelos:
                    match_found = comb
                    params_found = comb["parametros"]
                    break

            if match_found:
                st.session_state.validacion_ok = True
                st.session_state.last_params = params_found
                st.session_state.last_placas_input = placas_input
                st.session_state.last_paralelos = paralelos
                log_escaneo(operador, st.session_state.driver_match, placas_input, paralelos, True, params_found)
                st.balloons()
                st.rerun()
            else:
                st.session_state.validacion_ok = False
                st.session_state.last_params = None
                render_status("error", "COMBINACIÓN NO VÁLIDA")
                st.markdown("**Ejemplos válidos para este driver:**")
                for i, comb in enumerate(driver_data["combinaciones_validas"][:3], 1):
                    placas_str = " + ".join([f"{p['en_serie']}x {p['modelo']}" for p in comb["placas"] if p.get("en_serie", 0) > 0])
                    st.write(f"{i}. {placas_str} | Paralelos: {comb['caminos_paralelo']}")
                log_escaneo(operador, st.session_state.driver_match, placas_input, paralelos, False, None)

        if st.session_state.validacion_ok:
            render_status("ok", "COMBINACIÓN VÁLIDA")

        st.markdown('</div>', unsafe_allow_html=True)



# --- Contraste tabla parámetros ---
st.markdown("""
<style>
.parametros-container table {
    background: #ffffff !important;
    color: #000000 !important;
}
.parametros-container th {
    background: #f3f4f6 !important;
    color: #1f2937 !important;
    font-weight: 700 !important;
}
.parametros-container td {
    color: #000000 !important;
    border: 1px solid #d1d5db !important;
}
</style>
""", unsafe_allow_html=True)
