# mt5-wrapper/main.py

import os
import logging
from datetime import datetime
from typing import List

# --- Framework de API ---
from fastapi import FastAPI, HTTPException
import uvicorn

# --- Librerías de Trading y Configuración ---
import MetaTrader5 as mt5
from dotenv import load_dotenv

# --- Cargar variables de entorno (como la ruta a los robots) ---
load_dotenv()

# --- Configuración del Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mt5_wrapper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Inicializar la aplicación FastAPI ---
app = FastAPI(
    title="MT5-Wrapper API",
    description="API para interactuar con MetaTrader 5 y exponer datos de trading.",
    version="1.1.0"
)


# --- Lógica de Conexión a MetaTrader 5 ---
def connect_to_mt5():
    """Inicializa y comprueba la conexión con el terminal MetaTrader 5."""
    if not mt5.initialize():
        logger.error("Fallo al inicializar MetaTrader 5")
        mt5.shutdown()
        return False
    
    version = mt5.version()
    logger.info(f"Conectado a MetaTrader 5 build {version[1]}")
    return True


# --- Endpoints de la API ---

@app.get("/")
def read_root():
    """Endpoint raíz para verificar que la API está funcionando."""
    return {"status": "MT5 Wrapper API está online", "version": app.version}


@app.get("/positions")
async def get_open_positions():
    """Obtiene las posiciones de trading actualmente abiertas."""
    if not connect_to_mt5():
        raise HTTPException(status_code=503, detail="No se pudo conectar a MetaTrader 5")
    
    positions = mt5.positions_get()
    mt5.shutdown() # Siempre cerrar la conexión después de usar
    
    if positions is None:
        return []

    # Convierte los datos a un formato JSON serializable
    positions_list = [dict(p._asdict()) for p in positions]
    for p in positions_list:
        p['time'] = datetime.fromtimestamp(p['time']).isoformat()
        p['time_msc'] = datetime.fromtimestamp(p['time_msc'] / 1000).isoformat()
        p['time_update'] = datetime.fromtimestamp(p['time_update']).isoformat()
        p['time_update_msc'] = datetime.fromtimestamp(p['time_update_msc'] / 1000).isoformat()
    
    return positions_list


@app.get("/history")
async def get_history_deals(start_date: str, end_date: str):
    """Obtiene el historial de operaciones en un rango de fechas."""
    if not connect_to_mt5():
        raise HTTPException(status_code=503, detail="No se pudo conectar a MetaTrader 5")
    
    from_date = datetime.strptime(start_date, "%Y-%m-%d")
    to_date = datetime.strptime(end_date, "%Y-%m-%d")

    deals = mt5.history_deals_get(from_date, to_date)
    mt5.shutdown()

    if deals is None:
        return []

    deals_list = [dict(d._asdict()) for d in deals]
    for d in deals_list:
        d['time'] = datetime.fromtimestamp(d['time']).isoformat()
        d['time_msc'] = datetime.fromtimestamp(d['time_msc'] / 1000).isoformat()
    
    return deals_list

# Puedes ampliar este endpoint si necesitas más detalles
@app.get("/trade-details/{deal_ticket}")
async def get_trade_details(deal_ticket: int):
    """Obtiene detalles de un trade específico por su ticket."""
    # Esta es una implementación de ejemplo. Deberás completarla
    # con la lógica exacta que usabas para obtener todos los detalles.
    logger.info(f"Buscando detalles para el ticket: {deal_ticket}")
    # Aquí iría tu lógica para buscar el trade, su apertura, SL, TP, etc.
    # Por ahora, devolvemos un mock.
    mock_detail = {
        "deal_ticket": deal_ticket,
        "symbol": "EURUSD-", 
        "profit": 123.45,
        "order_type": "BUY",
        "close_reason": "Take Profit",
        "volume": 0.1,
        "position_id": 12345,
        "open_price": 1.07500,
        "stop_loss": 1.07000,
        "take_profit": 1.08500,
        "close_price": 1.08500,
        "commission": -1.50,
        "open_time": datetime.now().isoformat(),
        "close_time": datetime.now().isoformat()
    }
    return mock_detail


# ===================================================================
# ===                ✅ NUEVO ENDPOINT PARA ROBOTS ✅              ===
# ===================================================================
@app.get("/robots", response_model=dict[str, List[str]])
async def list_available_robots():
    """
    Escanea el directorio de Expert Advisors y devuelve una lista de los
    archivos .ex5 encontrados, que representan a los robots disponibles.
    """
    # Carga la ruta desde el archivo .env
    experts_path = os.getenv("MT5_EXPERTS_PATH")

    if not experts_path or not os.path.isdir(experts_path):
        logger.error(f"La ruta de los Experts no está configurada o no es válida: {experts_path}")
        raise HTTPException(
            status_code=500,
            detail="La ruta a la carpeta de Expert Advisors no está configurada correctamente en el servidor del wrapper."
        )

    try:
        logger.info(f"Escaneando robots en la ruta: {experts_path}")
        
        # Encuentra todos los archivos que terminan en .ex5 y no son subdirectorios
        robot_files = [
            f for f in os.listdir(experts_path)
            if os.path.isfile(os.path.join(experts_path, f)) and f.lower().endswith('.ex5')
        ]
        
        # Limpia la extensión .ex5 para devolver solo los nombres
        robot_names = [os.path.splitext(name)[0] for name in robot_files]
        
        logger.info(f"Encontrados {len(robot_names)} robots: {robot_names}")
        return {"robots": robot_names}

    except Exception as e:
        logger.error(f"Ocurrió un error inesperado al escanear la carpeta de robots: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Ocurrió un error interno en el servidor al intentar listar los robots."
        )

# --- Ejecutar la API ---
if __name__ == "__main__":
    logger.info("Iniciando MT5 Wrapper API...")
    # Escucha en todas las interfaces de red (0.0.0.0) para ser accesible desde fuera del VPS
    uvicorn.run(app, host="0.0.0.0", port=8000)