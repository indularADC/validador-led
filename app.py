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

# ───────── 1. CONFIGURACIÓN DE PÁGINA (DEBE IR PRIMERO) ─────────
st.set_page_config(page_title="Validador LED", layout="wide", initial_sidebar_state="collapsed")

# ───────── 2. CONFIGURACIÓN ─────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "auditoria_escaneos.db")
COMBINACIONES_JSON = os.path.join(BASE_DIR, "combinaciones_validas.json")

API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

# ───────── 3. INICIALIZAR SESSION STATE ─────────
if 'driver_extraido' not in st.session_state:
    st.session_state.driver_extraido = None
if 'driver_match' not in st.session_state:
    st.session_state.driver_match = None
if 'modelos_disponibles' not in st.session_state:
    st.session_state.modelos_disponibles = []
if 'imagen_bytes' not in st.session_state:
    st.session_state.imagen_bytes = None
if 'imagen_origen' not in st.session_state:
    st.session_state.imagen_origen = None

# ───────── 4. CSS PERSONALIZADO ─────────
st.markdown("""
<style>
/* Reducir tamaños de texto */
.main-title {font-size: 1.5rem !important;}
.stTextInput label, .stNumberInput label, .stSelectbox label {font-size: 0.75rem !important;}
.stTextInput input, .stNumberInput input, .stSelectbox select {font-size: 0.8rem !important;}
.stButton button {font-size: 0.85rem !important; padding: 0.3rem 0.8rem !important;}
.success-box {background: #28a745 !important; color: white !important; padding: 0.8rem; border-radius: 5px; font-size: 0.85rem; font-weight: bold; text-align: center;}
.error-box {background: #dc3545 !important; color: white !important; padding: 0.8rem; border-radius: 5px; font-size: 0.85rem; font-weight: bold; text-align: center;}
.info-box {background: #d1ecf1; padding: 0.8rem; border-radius: 5px; font-size: 0.8rem; color: #0c5460;}
h1, h2, h3 {font-size: 1.3rem !important;}
.stDataFrame {font-size: 0.75rem !important;}
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
        st.error("🔑 API Key no configurada")
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
        
        # Limpieza básica de comillas o saltos de línea raros
        texto_extraido = texto_extraido.replace('"', '').replace("'", " ").strip()
        return texto_extraido
    except Exception as e:
        st.error(f"❌ Error IA: {e}")
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
    """Guarda una copia estable de la imagen para evitar perderla entre reruns de Streamlit."""
    if archivo is None:
        return

    nuevos_bytes = archivo.getvalue()

    # Si cambia la imagen, limpiar resultado anterior para forzar una nueva lectura de IA.
    if nuevos_bytes != st.session_state.imagen_bytes:
        st.session_state.imagen_bytes = nuevos_bytes
        st.session_state.imagen_origen = origen
        st.session_state.driver_extraido = None
        st.session_state.driver_match = None
        st.session_state.modelos_disponibles = []

def limpiar_imagen():
    st.session_state.imagen_bytes = None
    st.session_state.imagen_origen = None
    st.session_state.driver_extraido = None
    st.session_state.driver_match = None
    st.session_state.modelos_disponibles = []

# ───────── 8. INTERFAZ PRINCIPAL ─────────
st.markdown('<h1 class="main-title">⚡ Validador Driver + Placas</h1>', unsafe_allow_html=True)
init_db()

# Sidebar - Operador
with st.sidebar:
    operador = st.text_input("👤 Operador", placeholder="Nombre", label_visibility="collapsed")
    st.markdown("---")
    if st.button("🔄 Reiniciar", type="secondary", use_container_width=True):
        limpiar_imagen()
        st.rerun()

# PESTAÑAS: Subir archivo o Tomar foto con cámara
tab1, tab2 = st.tabs(["📂 Subir archivo", "📸 Tomar foto"])

with tab1:
    # Opción tradicional: subir desde galería o archivos del celular/computadora
    uploaded_file = st.file_uploader(
        "📸 Foto del Driver",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed",
        key="uploaded_file"
    )
    guardar_imagen_en_estado("archivo", uploaded_file)

with tab2:
    # Opción para tomar una foto directa con la cámara del celular.
    # Importante: st.camera_input provoca reruns; por eso se guarda en session_state.
    camera_photo = st.camera_input(
        "📷 Posiciona el driver y toma la foto",
        key="camera_photo"
    )
    guardar_imagen_en_estado("camara", camera_photo)

img_bytes = st.session_state.imagen_bytes

# Visualización de imagen cargada
if img_bytes:
    origen = "cámara" if st.session_state.imagen_origen == "camara" else "archivo"
    st.success(f"✅ Imagen cargada desde {origen}")
    with st.expander("🖼️ Ver imagen completa", expanded=False):
        try:
            img_full = Image.open(io.BytesIO(img_bytes))
            st.image(img_full, width=400)
        except Exception as e:
            st.error(f"❌ No se pudo abrir la imagen: {e}")
            limpiar_imagen()
            st.stop()

# Cargar combinaciones
combinaciones = cargar_combinaciones()
if not combinaciones:
    st.error("❌ No se encontró el archivo combinaciones_validas.json o está vacío")
    st.stop()

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

# Botón para extraer driver
if img_bytes and not st.session_state.driver_match:
    if st.button("🔍 Extraer Driver", type="primary", use_container_width=True, key="btn_extraer_driver"):
        if not operador:
            st.error("⚠️ Ingresá el operador en el menú lateral primero")
            st.stop()
        
        imagen_a_procesar = st.session_state.imagen_bytes
        if not imagen_a_procesar:
            st.error("⚠️ La imagen se perdió durante la recarga. Tomá la foto nuevamente.")
            st.stop()

        with st.spinner("🤖 Leyendo..."):
            driver_leido = extraer_driver(imagen_a_procesar)
        
        if driver_leido:
            st.session_state.driver_extraido = driver_leido
            driver_match = buscar_driver_ia(driver_leido, combinaciones)
            
            if driver_match:
                st.session_state.driver_match = driver_match
                st.session_state.modelos_disponibles = obtener_modelos_placas(combinaciones)
                st.success(f"✅ {driver_match}")
                st.rerun()
            else:
                st.error(f"❌ Driver no encontrado: {driver_leido}")
                st.write("Drivers disponibles:", list(combinaciones.keys())[:5])
