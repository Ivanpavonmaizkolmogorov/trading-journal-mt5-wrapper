# mt5-wrapper/main.py (Versión Definitiva con Conexión Persistente)

import os
import logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from typing import List

# --- Framework de API ---
from fastapi import FastAPI, HTTPException
import uvicorn

# --- Librerías de Trading y Configuración ---
import MetaTrader5 as mt5
from dotenv import load_dotenv

# --- Cargar variables de entorno del archivo .env ---
load_dotenv()

# --- Configuración del Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mt5_wrapper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- GESTIÓN DEL CICLO DE VIDA DE LA API (CONEXIÓN PERSISTENTE) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona la conexión a MT5 al iniciar y detener la API.
    """
    # Código que se ejecuta al iniciar la API
    logger.info("Iniciando conexión persistente con MetaTrader 5...")
    mt5_path = os.getenv("MT5_EXE_PATH")
    if not mt5_path:
        logger.critical("FALLO CRÍTICO: La variable de entorno MT5_EXE_PATH no está definida.")
        # Sin la ruta, la inicialización puede fallar.
        # Podríamos decidir detener la app, pero por ahora solo advertimos.
    
    if not mt5.initialize(path=mt5_path):
        logger.critical(f"FALLO CRÍTICO al inicializar MT5: {mt5.last_error()}")
    else:
        version = mt5.version()
        logger.info(f"Conexión con MetaTrader 5 build {version[1]} establecida.")
    
    yield # La API se ejecuta aquí
    
    # Código que se ejecuta al detener la API (ej. con Ctrl+C)
    logger.info("Cerrando conexión con MetaTrader 5...")
    mt5.shutdown()


# --- Inicializar la aplicación FastAPI con el ciclo de vida ---
app = FastAPI(
    title="MT5-Wrapper API",
    description="API para interactuar con MetaTrader 5 de forma estable y persistente.",
    version="2.0.0", # Nueva versión mayor por cambio de arquitectura
    lifespan=lifespan
)


# --- Endpoints de la API ---

@app.get("/")
async def read_root():
    """Endpoint raíz para verificar que la API está funcionando."""
    return {"status": "MT5 Wrapper API está online", "version": app.version}


@app.get("/positions", response_model=List[dict])
async def get_open_positions():
    """Obtiene las posiciones de trading actualmente abiertas."""
    positions = mt5.positions_get()
    if positions is None:
        logger.warning("mt5.positions_get() devolvió None. Comprobar conexión con el terminal.")
        return []

    positions_list = [p._asdict() for p in positions]
    for p in positions_list:
        # Convertimos todos los timestamps a strings ISO en UTC
        p['time'] = datetime.fromtimestamp(p['time'], tz=timezone.utc).isoformat()
        p['time_msc'] = datetime.fromtimestamp(p['time_msc'] / 1000, tz=timezone.utc).isoformat()
        p['time_update'] = datetime.fromtimestamp(p['time_update'], tz=timezone.utc).isoformat()
        p['time_update_msc'] = datetime.fromtimestamp(p['time_update_msc'] / 1000, tz=timezone.utc).isoformat()
    
    return positions_list


@app.get("/latest-deals/{count}", response_model=List[dict])
async def get_latest_deals(count: int = 200):
    """
    Obtiene los 'count' deals más recientes del historial.
    Esta es la implementación correcta y eficiente.
    """
    # 1. Definimos un rango de búsqueda amplio para no perder nada.
    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=90) # 90 días es más que suficiente
    
    # 2. Obtenemos TODOS los deals de ese rango.
    all_deals = mt5.history_deals_get(from_date, to_date)
    
    if all_deals is None or len(all_deals) == 0:
        return []
    
    # 3. Ordenamos los deals en Python por tiempo para encontrar los más recientes.
    sorted_deals = sorted(all_deals, key=lambda d: d.time, reverse=True)
    
    # 4. Nos quedamos solo con los 'count' más recientes.
    latest_n_deals = sorted_deals[:count]
    
    # 5. Convertimos a diccionario y formateamos las fechas para JSON.
    deals_list = [deal._asdict() for deal in latest_n_deals]
    for deal in deals_list:
        deal['time'] = datetime.fromtimestamp(deal['time'], tz=timezone.utc).isoformat()
        deal['time_msc'] = datetime.fromtimestamp(deal['time_msc'] / 1000, tz=timezone.utc).isoformat()
            
    return deals_list


@app.get("/trade-details/{deal_ticket}", response_model=dict)
async def get_trade_details(deal_ticket: int):
    """Obtiene detalles de un trade específico por su ticket."""
    # Como ya tenemos una conexión persistente, esta llamada es rápida y fiable.
    deals = mt5.history_deals_get(0, datetime.now(timezone.utc), ticket=deal_ticket)
    
    if deals is None or len(deals) == 0:
        raise HTTPException(status_code=404, detail=f"Deal con ticket {deal_ticket} no encontrado.")

    # El resultado es una tupla, tomamos el primer elemento
    details = dict(deals[0]._asdict())

    # Formateamos los datos para consistencia
    details['time'] = datetime.fromtimestamp(details['time'], tz=timezone.utc).isoformat()
    details['time_msc'] = datetime.fromtimestamp(details['time_msc'] / 1000, tz=timezone.utc).isoformat()
    
    # Extraemos SL y TP del objeto order asociado si es necesario (o lo dejamos para el cliente)
    # Por ahora, mantenemos la simplicidad y devolvemos los datos del deal.

    return details


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Iniciando MT5 Wrapper API en http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)