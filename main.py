# mt5-wrapper/main.py (Versión Final y Eficiente)

import os
import logging
from datetime import datetime, timezone
from typing import List, Optional

# --- Framework de API ---
from fastapi import FastAPI, HTTPException
import uvicorn
import pandas as pd # Necesario para la conversión de datos

# --- Librerías de Trading y Configuración ---
import MetaTrader5 as mt5
from dotenv import load_dotenv

# --- Cargar variables de entorno ---
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
    version="1.3.0" # Version incrementada para reflejar los cambios
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
    mt5.shutdown()
    
    if positions is None:
        return []

    positions_list = [dict(p._asdict()) for p in positions]
    for p in positions_list:
        p['time'] = datetime.fromtimestamp(p['time'], tz=timezone.utc).isoformat()
        p['time_msc'] = datetime.fromtimestamp(p['time_msc'] / 1000, tz=timezone.utc).isoformat()
        p['time_update'] = datetime.fromtimestamp(p['time_update'], tz=timezone.utc).isoformat()
        p['time_update_msc'] = datetime.fromtimestamp(p['time_update_msc'] / 1000, tz=timezone.utc).isoformat()
    
    return positions_list


@app.get("/history")
async def get_history_deals(start_date: str, end_date: str):
    """(Endpoint antiguo) Obtiene el historial de operaciones en un rango de fechas."""
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
        d['time'] = datetime.fromtimestamp(d['time'], tz=timezone.utc).isoformat()
        d['time_msc'] = datetime.fromtimestamp(d['time_msc'] / 1000, tz=timezone.utc).isoformat()
    
    return deals_list

# --- ✅ NUEVO ENDPOINT EFICIENTE ---
@app.get("/history/latest")
async def get_latest_history_deals(count: int = 50):
    """
    Obtiene solo los últimos 'count' deals del historial.
    Es mucho más eficiente que obtener todo el historial por fechas.
    """
    if not connect_to_mt5():
        raise HTTPException(status_code=503, detail="No se pudo conectar a MetaTrader 5")

    deals = mt5.history_deals_get(datetime.now(), datetime.fromtimestamp(0), count=count)
    mt5.shutdown()

    if deals is None or len(deals) == 0:
        return []
    
    deals_df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    deals_df['time'] = pd.to_datetime(deals_df['time'], unit='s').dt.tz_localize('utc').isoformat()
    deals_df['time_msc'] = pd.to_datetime(deals_df['time_msc'], unit='ms').dt.tz_localize('utc').dt.isoformat()
    deals_df = deals_df.where(pd.notna(deals_df), None)

    return deals_df.to_dict('records')


@app.get("/trade-details/{deal_ticket}")
async def get_trade_details(deal_ticket: int):
    """Obtiene detalles de un trade específico por su ticket."""
    if not connect_to_mt5():
        raise HTTPException(status_code=503, detail="No se pudo conectar a MetaTrader 5")
    
    # Buscamos el deal en el historial reciente
    deals = mt5.history_deals_get(datetime.now(), datetime.fromtimestamp(0), count=200) # Busca en los últimos 200 deals
    mt5.shutdown()

    if deals is None:
        raise HTTPException(status_code=404, detail=f"No se encontró historial de trades.")

    target_deal = next((d for d in deals if d.ticket == deal_ticket), None)
    
    if target_deal is None:
        raise HTTPException(status_code=404, detail=f"Deal con ticket {deal_ticket} no encontrado en el historial reciente.")

    # Convertimos el deal a diccionario y formateamos las fechas
    details = dict(target_deal._asdict())
    details['time'] = datetime.fromtimestamp(details['time'], tz=timezone.utc).isoformat()
    details['time_msc'] = datetime.fromtimestamp(details['time_msc'] / 1000, tz=timezone.utc).isoformat()
    
    # Asignamos SL y TP si existen en el objeto, si no, None
    details['stop_loss'] = details.get('sl', 0.0)
    details['take_profit'] = details.get('tp', 0.0)

    # Renombramos para consistencia con el bot
    details['open_time'] = details['time']
    details['close_time'] = details['time']
    details['deal_ticket'] = details['ticket']
    details['magic'] = details['magic']
    
    return details


@app.get("/robots", response_model=dict[str, List[str]])
async def list_available_robots():
    """
    Escanea el directorio de Expert Advisors y devuelve una lista de los
    archivos .ex5 encontrados.
    """
    experts_path = os.getenv("MT5_EXPERTS_PATH")

    if not experts_path or not os.path.isdir(experts_path):
        logger.error(f"La ruta de los Experts no está configurada o no es válida: {experts_path}")
        raise HTTPException(status_code=500, detail="La ruta a la carpeta de Expert Advisors no está configurada en el servidor.")

    try:
        logger.info(f"Escaneando robots en la ruta: {experts_path}")
        robot_files = [
            f for f in os.listdir(experts_path)
            if os.path.isfile(os.path.join(experts_path, f)) and f.lower().endswith('.ex5')
        ]
        robot_names = [os.path.splitext(name)[0] for name in robot_files]
        logger.info(f"Encontrados {len(robot_names)} robots: {robot_names}")
        return {"robots": robot_names}
    except Exception as e:
        logger.error(f"Ocurrió un error inesperado al escanear la carpeta de robots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ocurrió un error interno en el servidor al intentar listar los robots.")


if __name__ == "__main__":
    logger.info("Iniciando MT5 Wrapper API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)