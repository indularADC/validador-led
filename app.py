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

# ───────── CONFIGURACIÓN ─────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "auditoria_escaneos.db")
COMBINACIONES_JSON = os.path.join(BASE_DIR, "combinaciones_validas.json")

API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

# ───────── INICIALIZAR SESSION STATE ─────────
if 'driver_extraido' not in st.session_state:
    st.session_state.driver_extraido = None
if 'driver_match' not in st.session_state:
    st.session_state.driver_match = None
if 'modelos_disponibles' not in st.session_state:
    st.session_state.modelos_disponibles = []

# ───────── CSS PERSONALIZADO (RESPONSIVE PARA MÓVIL) ─────────
st.markdown("""
<style>
/* Ocultar menú y footer en móvil para más espacio */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

/* Títulos más compactos en móvil */
.main-title {font-size: 1.3rem !important; text-align: center;}
h1, h2, h3 {font-size: 1.1rem !important;}

/* Inputs más grandes y fáciles de tocar en móvil */
.stTextInput input, .stNumberInput input, .stSelectbox select {
    font-size: 1rem !important;
    padding: 0.5rem !important;
    min-height: 44px !important; /* Tamaño mínimo para toque en Android */
}
.stTextInput label, .stNumberInput label, .stSelectbox label {
    font-size: 0.9rem !important;
    font-weight: 500;
}

/* Botones más grandes para dedos */
.stButton button {
    font-size: 1rem !important;
    padding: 0.6rem 1.2rem !important;
    min-height: 48px !important;
    width: 100% !important; /* Botones full-width en móvil */
}

/* Cajas de mensaje legibles */
.success-box, .error-box, .info-box {
    padding: 1rem !important;
    font-size: 0.95rem !important;
    margin: 0.5rem 0 !important;
}
.success-box {background: #28a745 !important; color: white !important;}
.error-box {background: #dc3545 !important; color: white !important;}
.info-box {background: #d1ecf1 !important; color: #0c5460 !important;}

/* Tabla de parámetros scrollable en pantallas pequeñas */
.stTable {overflow-x: auto !important;}
.stTable table {font-size: 0.8rem !important;}

/* Ajuste de columnas en móvil */
@media (max-width: 768px) {
    .stColumns {flex-wrap: wrap !important;}
    .stColumn {min-width: 100% !important; margin-bottom: 0.5rem !important;}
}
</style>
""", unsafe_allow_html=True)

# ───────── BASE DE DATOS ─────────
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

# ───────── VISIÓN IA ─────────
def extraer_driver(img_bytes):
    if not API_KEY:
        st.error("🔑 API Key no configurada")
        return None
        
    client = genai.Client(api_key=API_KEY)
    
    # PROMPT MEJORADO PARA PRECISIÓN
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
        
        # Limpieza básica de comillas o saltos de línea raros
        texto_extraido = texto_extraido.replace('"', '').replace("'", " ").strip()
        return texto_extraido
    except Exception as e:
        st.error(f"❌ Error IA: {e}")
        return None

# ───────── UTILIDADES ─────────
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

# ───────── INTERFAZ PRINCIPAL ─────────
st.set_page_config(page_title="Validador LED", layout="wide", initial_sidebar_state="collapsed")

st.markdown('<h1 class="main-title">⚡ Validador Driver + Placas</h1>', unsafe_allow_html=True)
init_db()

# Campo del operador en pantalla principal (visible en móvil)
operador = st.text_input("👤 Operador", placeholder="Ingresa tu nombre o ID", key="input_operador")

# Botón de reinicio en sidebar (opcional, solo para PC)
with st.sidebar:
    st.markdown("### ⚙️ Opciones")
    if st.button("🔄 Reiniciar app", type="secondary", use_container_width=True):
        st.session_state.driver_extraido = None
        st.session_state.driver_match = None
        st.session_state.modelos_disponibles = []
        st.rerun()

# Campo de carga de foto
col1, col2 = st.columns([2, 1])
with col1:
    uploaded = st.file_uploader("📸 Foto del Driver", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
with col2:
    if uploaded:
        st.success("✅ Imagen cargada")
        # Botón para ver imagen completa usando expander
        with st.expander("🖼️ Ver imagen completa", expanded=False):
            img_full = Image.open(io.BytesIO(uploaded.read()))
            st.image(img_full, width=400)
            uploaded.seek(0)  # Resetear para poder leer de nuevo

# Cargar combinaciones
combinaciones = cargar_combinaciones()

# Si hay un driver extraído previamente, mostrar formulario
if st.session_state.driver_match and st.session_state.modelos_disponibles:
    st.markdown(f"""
    <div class="success-box">
    ✅ Driver: {st.session_state.driver_match}
    </div>
    """, unsafe_allow_html=True)
    
    # Formulario de configuración
    with st.form("config_form", clear_on_submit=False):
        st.markdown("### ⚙️ Configuración de Placas")
        
        # Crear filas tipo tabla
        st.markdown("**Placas a utilizar:**")
        
        # Headers
        col_headers = st.columns([3, 1, 3, 1])
        with col_headers[0]:
            st.markdown("**Placa 1**")
        with col_headers[1]:
            st.markdown("**Cant.**")
        with col_headers[2]:
            st.markdown("**Placa 2**")
        with col_headers[3]:
            st.markdown("**Cant.**")
        
        # Fila 1: Placas 1 y 2
        col1, col2, col3, col4 = st.columns([3, 1, 3, 1])
        with col1:
            placa1_mod = st.selectbox("Placa 1", ["--"] + st.session_state.modelos_disponibles, 
                                     key="placa1_mod", label_visibility="collapsed")
        with col2:
            placa1_cant = st.number_input("Cant", min_value=0, max_value=20, value=0, 
                                         key="placa1_cant", label_visibility="collapsed")
        with col3:
            placa2_mod = st.selectbox("Placa 2", ["--"] + st.session_state.modelos_disponibles, 
                                     key="placa2_mod", label_visibility="collapsed")
        with col4:
            placa2_cant = st.number_input("Cant", min_value=0, max_value=20, value=0, 
                                         key="placa2_cant", label_visibility="collapsed")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Headers segunda fila
        col_headers2 = st.columns([3, 1, 3, 1])
        with col_headers2[0]:
            st.markdown("**Placa 3**")
        with col_headers2[1]:
            st.markdown("**Cant.**")
        with col_headers2[2]:
            st.markdown("**Placa 4**")
        with col_headers2[3]:
            st.markdown("**Cant.**")
        
        # Fila 2: Placas 3 y 4
        col5, col6, col7, col8 = st.columns([3, 1, 3, 1])
        with col5:
            placa3_mod = st.selectbox("Placa 3", ["--"] + st.session_state.modelos_disponibles, 
                                     key="placa3_mod", label_visibility="collapsed")
        with col6:
            placa3_cant = st.number_input("Cant", min_value=0, max_value=20, value=0, 
                                         key="placa3_cant", label_visibility="collapsed")
        with col7:
            placa4_mod = st.selectbox("Placa 4", ["--"] + st.session_state.modelos_disponibles, 
                                     key="placa4_mod", label_visibility="collapsed")
        with col8:
            placa4_cant = st.number_input("Cant", min_value=0, max_value=20, value=0, 
                                         key="placa4_cant", label_visibility="collapsed")
        
        # Paralelos
        st.markdown("<br>", unsafe_allow_html=True)
        col_par = st.columns(2)
        with col_par[0]:
            paralelos = st.number_input("🔀 Caminos en Paralelo", min_value=1, max_value=10, value=1)
        
        submitted = st.form_submit_button("✅ Validar", type="primary", use_container_width=True)
        
        if submitted:
            if not operador:
                st.error("⚠️ Ingresá el operador en el menú lateral")
                st.stop()
            
            # Recopilar placas seleccionadas
            placas_input = []
            for mod, cant in [(placa1_mod, placa1_cant), (placa2_mod, placa2_cant), 
                             (placa3_mod, placa3_cant), (placa4_mod, placa4_cant)]:
                if mod != "--" and cant > 0:
                    placas_input.append({"modelo": mod, "en_serie": cant})
            
            if not placas_input:
                st.error("⚠️ Seleccioná al menos una placa")
                st.stop()
            
            # Validar
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
                st.balloons()
                st.markdown('<div class="success-box">✅ COMBINACIÓN VÁLIDA</div>', unsafe_allow_html=True)
                
                st.subheader("📊 Parámetros de Operación")
                
                # Crear tabla de parámetros
                params_df = pd.DataFrame({
                    "Uled": [f"{params_found['uled']} Vcc"],
                    "Pled": [f"{params_found['pled']} VA"],
                    "Flujo": [f"{params_found['flujo']} lm"],
                    "Plinea": [f"{params_found['plinea']} W" if params_found['plinea'] != "ND" else "ND"],
                    "FP": [f"{params_found['fp']}" if params_found['fp'] != "ND" else "ND"],
                    "TDH": [f"{params_found['tdh']}%" if params_found['tdh'] != "ND" else "ND"]
                })
                
                # Mostrar tabla estilizada
                st.table(params_df)
                log_escaneo(operador, st.session_state.driver_match, placas_input, paralelos, True, params_found)
            else:
                st.markdown('<div class="error-box">❌ COMBINACIÓN NO VÁLIDA</div>', unsafe_allow_html=True)
                
                st.info("💡 Ejemplos válidos:")
                for i, comb in enumerate(driver_data["combinaciones_validas"][:3], 1):
                    placas_str = " + ".join([f"{p['en_serie']}x {p['modelo']}" for p in comb["placas"] if p.get("en_serie", 0) > 0])
                    st.write(f"{i}. {placas_str} | Paralelos: {comb['caminos_paralelo']}")
                
                log_escaneo(operador, st.session_state.driver_match, placas_input, paralelos, False, None)

# Botón para extraer driver CON CAMPO EDITABLE (CORREGIDO)
if uploaded and not st.session_state.driver_match:
    # Paso 1: Botón para extraer con IA
    if st.button("🔍 Extraer Driver", type="primary", use_container_width=True):
        if not operador:
            st.error("⚠️ Ingresá el operador en el menú lateral primero")
            st.stop()
        
        with st.spinner("🤖 Leyendo..."):
            driver_leido = extraer_driver(uploaded.read())
        
        if driver_leido:
            # Guardar en session_state para persistencia entre recargas
            st.session_state.driver_extraido = driver_leido
            st.session_state.driver_corregido = driver_leido  # Valor inicial editable
            st.session_state.mostrar_editor = True  # Flag para mostrar editor
            st.rerun()  # Recargar para mostrar el editor
    
    # Paso 2: Mostrar editor si el flag está activo
    if st.session_state.get('mostrar_editor', False) and st.session_state.driver_extraido:
        st.info("📝 Verificá que el modelo detectado sea correcto. Podés editarlo si es necesario.")
        
        # Campo editable que mantiene el valor entre recargas
        driver_corregido = st.text_input(
            "✏️ Modelo detectado (editable):",
            value=st.session_state.driver_corregido,
            help="Si la IA leyó mal, corregí el texto manualmente antes de continuar",
            key="input_driver_corregido"
        )
        
        # Actualizar session_state con lo que escribe el usuario
        st.session_state.driver_corregido = driver_corregido
        
        # Botón para confirmar y buscar
        if st.button("✅ Confirmar y Buscar", type="primary", use_container_width=True):
            driver_match = buscar_driver_ia(st.session_state.driver_corregido, combinaciones)
            
            if driver_match:
                # Guardar resultado y limpiar flags
                st.session_state.driver_match = driver_match
                st.session_state.modelos_disponibles = obtener_modelos_placas(combinaciones)
                st.session_state.mostrar_editor = False  # Ocultar editor
                st.success(f"✅ Driver confirmado: {driver_match}")
                st.rerun()  # Recargar para mostrar formulario de placas
            else:
                st.error(f"❌ Driver no encontrado: {st.session_state.driver_corregido}")
                st.write("💡 Drivers disponibles en la base:")
                for drv in list(combinaciones.keys())[:10]:
                    st.write(f"  • {drv}")