print("--- ✅ ESTOY EJECUTANDO LA VERSIÓN MÁS NUEVA DEL CÓDIGO (v_vela_enriquecida) ✅ ---")

# ...el resto de tus imports (import os, import logging, etc.) deben ir debajo de esta línea
# mt5-wrapper/main.py (Versión 4.0 - Robusta con Dependencias)
import re

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict

# --- Framework de API ---
from fastapi import FastAPI, Depends, HTTPException
import uvicorn

# --- Librerías de Trading y Configuración ---
import MetaTrader5 as mt5
from dotenv import load_dotenv

# --- Cargar y configurar todo ---
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("mt5_wrapper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- GESTOR DE CONEXIÓN USANDO DEPENDENCIAS DE FASTAPI ---
# Esta es la forma más robusta de manejar recursos por petición para MT5.

def get_mt5_connection():
    """
    Dependencia de FastAPI: se conecta a MT5, cede el control al endpoint,
    y se asegura de desconectar al final, en cada petición.
    """
    mt5_path = os.getenv("MT5_TERMINAL_PATH")
    # --- AÑADE ESTA LÍNEA ---
    logger.info(f"RUTA LEÍDA DEL .ENV: {mt5_path}")
    if not mt5.initialize(path=mt5_path):
        logger.error(f"Fallo al inicializar MT5: {mt5.last_error()}")
        raise HTTPException(status_code=503, detail="No se pudo conectar a MetaTrader 5")
    
    try:
        # 'yield' pasa el objeto 'mt5' ya conectado al código del endpoint
        yield mt5
    finally:
        # Este código se ejecuta SIEMPRE después de que el endpoint termina,
        # incluso si hay un error.
        mt5.shutdown()
        logger.info("Conexión a MT5 cerrada limpiamente.")


app = FastAPI(
    title="MT5-Wrapper API",
    description="API para interactuar con MetaTrader 5 de forma robusta por petición.",
    version="4.0.0"
)

# --- Endpoints de la API ---

@app.get("/")
async def read_root():
    """Endpoint raíz para verificar que la API está funcionando."""
    return {"status": "MT5 Wrapper API está online", "version": app.version}


@app.get("/positions", response_model=List[dict])
async def get_open_positions(mt5_conn: mt5 = Depends(get_mt5_connection)):
    """Obtiene las posiciones de trading actualmente abiertas."""
    positions = mt5_conn.positions_get()
    if positions is None:
        return []

    positions_list = [p._asdict() for p in positions]
    for p in positions_list:
        p['time'] = datetime.fromtimestamp(p['time'], tz=timezone.utc).isoformat()
        p['time_msc'] = datetime.fromtimestamp(p['time_msc'] / 1000, tz=timezone.utc).isoformat()
        p['time_update'] = datetime.fromtimestamp(p['time_update'], tz=timezone.utc).isoformat()
        p['time_update_msc'] = datetime.fromtimestamp(p['time_update_msc'] / 1000, tz=timezone.utc).isoformat()
    
    return positions_list


@app.get("/latest-deals/{count}", response_model=List[dict])
async def get_latest_deals(count: int = 200, mt5_conn: mt5 = Depends(get_mt5_connection)):
    """
    Obtiene los 'count' deals más recientes del historial, usando la hora del
    servidor de MT5 como referencia para máxima fiabilidad.
    """
    try:
        # 1. Obtenemos la hora fiable del servidor de MT5
        rates = mt5_conn.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M1, 0, 1)
        if rates is None or len(rates) == 0:
            # Si falla la obtención de la vela, usamos la hora del sistema como respaldo
            logger.warning("No se pudo obtener la hora de la vela de EURUSD. Usando la hora del sistema.")
            to_date = datetime.now(timezone.utc)
        else:
            # Usamos la hora de la última vela como la referencia más precisa
            server_timestamp = rates[0]['time']
            to_date = datetime.fromtimestamp(server_timestamp, tz=timezone.utc) + timedelta(minutes=1)
            logger.info(f"Usando hora de servidor MT5 (vela EURUSD) como referencia: {to_date.strftime('%Y-%m-%d %H:%M:%S')}")

        # 2. Buscamos en un rango de tiempo amplio para asegurar que no se pierde nada
        from_date = to_date - timedelta(days=90)
        all_deals = mt5_conn.history_deals_get(from_date, to_date)
        
        if all_deals is None or len(all_deals) == 0:
            return []

        # El resto de la función se mantiene igual: ordena por tiempo y formatea
        sorted_deals = sorted(all_deals, key=lambda d: d.time, reverse=True)
        latest_n_deals = sorted_deals[:count]
        
        deals_list = [deal._asdict() for deal in latest_n_deals]
        for deal in deals_list:
            deal['time'] = datetime.fromtimestamp(deal['time'], tz=timezone.utc).isoformat()
            deal['time_msc'] = datetime.fromtimestamp(deal['time_msc'] / 1000, tz=timezone.utc).isoformat()
                
        return deals_list

    except Exception as e:
        logger.error(f"Error crítico en la función get_latest_deals: {e}", exc_info=True)
        # En caso de cualquier error inesperado, devolvemos una lista vacía para no romper el bot.
        return []


@app.get("/trade-details/{deal_ticket}", response_model=dict)
async def get_trade_details(deal_ticket: int, mt5_conn: mt5 = Depends(get_mt5_connection)):
    """Obtiene detalles de un trade específico por su ticket."""
    from_date = datetime(2020, 1, 1)
    to_date = datetime.now(timezone.utc)
    
    deals = mt5_conn.history_deals_get(from_date, to_date)
    
    if deals is None:
        raise HTTPException(status_code=404, detail=f"No se encontró historial de trades.")

    target_deal = next((d for d in deals if d.ticket == deal_ticket), None)
    
    if target_deal is None:
        raise HTTPException(status_code=404, detail=f"Deal con ticket {deal_ticket} no encontrado.")

    details = dict(target_deal._asdict())
    details['time'] = datetime.fromtimestamp(details['time'], tz=timezone.utc).isoformat()
    details['time_msc'] = datetime.fromtimestamp(details['time_msc'] / 1000, tz=timezone.utc).isoformat()
    
    # Aquí puedes añadir la lógica para obtener SL/TP si es necesario
    
    return details


@app.get("/robots", response_model=Dict[str, List[Dict[str, str | int]]])
async def list_available_robots():
    """
    [VERSIÓN DE DEPURACIÓN]
    Escanea, devuelve una lista de EAs (.ex5) y extrae su MagicNumber.
    """
    logger.info("--- INICIANDO BÚSQUEDA DE ROBOTS (VERSIÓN DEBUG) ---")
    experts_path = os.getenv("MT5_EXPERTS_PATH")
    logger.info(f"Ruta de Experts a escanear: {experts_path}")
    
    if not experts_path or not os.path.isdir(experts_path):
        logger.error("La ruta de Experts no es válida o no está configurada.")
        raise HTTPException(status_code=500, detail="Ruta de Expert Advisors no configurada.")

    registered_robots = []
    try:
        robot_files = [f for f in os.listdir(experts_path) if f.lower().endswith('.ex5')]
        logger.info(f"Archivos .ex5 encontrados: {robot_files}")
        
        for ex5_file in robot_files:
            robot_name = os.path.splitext(ex5_file)[0]
            mq5_path = os.path.join(experts_path, robot_name + ".mq5")
            logger.info(f"Procesando '{robot_name}': buscando .mq5 en '{mq5_path}'")
            
            magic_number = extract_magic_number_from_mq5(mq5_path)
            logger.info(f"Resultado de la extracción para '{robot_name}': {magic_number}")
            
            if magic_number is not None:
                registered_robots.append({"name": robot_name, "magic_number": magic_number})

        logger.info(f"Robots válidos que se devolverán: {registered_robots}")
        return {"robots": registered_robots}

    except Exception as e:
        logger.error(f"Error crítico durante el escaneo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al escanear la carpeta de robots: {e}")
        
# =====================================================================
#  ✅ NUEVO ENDPOINT PARA ENRIQUECER DATOS DE APERTURA (VERSIÓN FINAL Y ROBUSTA)
# =====================================================================
@app.get("/enriched-position-details/{position_id}", response_model=Dict)
async def get_enriched_position_details(position_id: int, mt5_conn: mt5 = Depends(get_mt5_connection)):
    """
    Obtiene los detalles completos y enriquecidos de una posición abierta,
    buscando el deal y la orden de apertura originales de forma segura.
    """
    try:
        # 1. Obtener la posición por su ID (ticket)
        positions = mt5_conn.positions_get(ticket=position_id)
        if not positions:
            raise HTTPException(status_code=404, detail=f"Posición con ID {position_id} no encontrada.")
        position_info = positions[0]

        # 2. Inicializar los datos con la información básica de la posición
        enriched_data = {
            "ticket": position_info.ticket,
            "time": datetime.fromtimestamp(position_info.time, tz=timezone.utc).isoformat(),
            "type": position_info.type,
            "magic": position_info.magic,
            "volume": position_info.volume,
            "price_open": position_info.price_open,
            "sl": position_info.sl,
            "tp": position_info.tp,
            "symbol": position_info.symbol,
            "comment": position_info.comment
        }

        # 3. Intentar enriquecer los datos buscando la orden original
        position_deals = mt5_conn.history_deals_get(position=position_id)
        if position_deals and len(position_deals) > 0:
            # El deal de apertura es el que tiene entry==0 (DEAL_ENTRY_IN)
            opening_deal = next((d for d in position_deals if d.entry == 0), None)
            if opening_deal:
                # Con el deal de entrada, obtenemos el ticket de la orden que lo originó
                order_ticket = opening_deal.order
                order_info_tuple = mt5_conn.history_orders_get(ticket=order_ticket)
                if order_info_tuple and len(order_info_tuple) > 0:
                    opening_order = order_info_tuple[0]
                    # Si encontramos la orden, actualizamos los datos con información más precisa
                    enriched_data["sl"] = opening_order.sl
                    enriched_data["tp"] = opening_order.tp
                    enriched_data["comment"] = opening_order.comment
        
        return enriched_data

    except Exception as e:
        logger.error(f"Error crítico enriqueciendo la posición {position_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al procesar los detalles de la posición: {e}")


@app.get("/enriched-trade-details/{deal_ticket}", response_model=Dict)
async def get_enriched_trade_details(deal_ticket: int, mt5_conn: mt5 = Depends(get_mt5_connection)):
    """
    Obtiene los detalles completos y enriquecidos de un trade cerrado,
    buscando el deal de apertura y la orden original.
    """
    try:
        deal_info = mt5_conn.history_deals_get(ticket=deal_ticket)
        if not deal_info or len(deal_info) == 0:
            raise HTTPException(status_code=404, detail=f"Deal con ticket {deal_ticket} no encontrado.")
        
        closing_deal = deal_info[0]
        position_id = closing_deal.position_id

        position_deals = mt5_conn.history_deals_get(position=position_id)
        opening_deal = None
        opening_order = None
        if position_deals:
            opening_deal = next((d for d in position_deals if d.entry == 0), None) # entry=0 es una apertura
            if opening_deal:
                order_ticket = opening_deal.order
                order_info = mt5_conn.history_orders_get(ticket=order_ticket)
                opening_order = order_info[0] if order_info and len(order_info) > 0 else None

        enriched_data = {
            "deal_ticket": closing_deal.ticket,
            "position_id": position_id,
            "symbol": closing_deal.symbol,
            "volume": closing_deal.volume,
            "magic_number": closing_deal.magic,
            "profit": closing_deal.profit,
            "commission": closing_deal.commission,
            "swap": closing_deal.swap,
            "close_price": closing_deal.price,
            "close_time_utc": datetime.fromtimestamp(closing_deal.time, tz=timezone.utc).isoformat(),
            "close_reason": closing_deal.reason,
            "order_type": opening_deal.type if opening_deal else closing_deal.type,
            "open_price": opening_deal.price if opening_deal else None,
            "open_time_utc": datetime.fromtimestamp(opening_deal.time, tz=timezone.utc).isoformat() if opening_deal else None,
            "stop_loss": opening_order.sl if opening_order else 0.0,
            "take_profit": opening_order.tp if opening_order else 0.0,
        }
        return enriched_data

    except Exception as e:
        logger.error(f"Error enriqueciendo el deal {deal_ticket}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al procesar los detalles del trade.")

def extract_magic_number_from_mq5(file_path: str) -> int | None:
    """
    [VERSIÓN 2.1 FINAL]
    Abre un archivo .mq5 y extrae el 'MagicNumber' probando las codificaciones 
    en el orden de prioridad correcto.
    """
    content = None
    # Cambiamos el orden: Probamos utf-16 PRIMERO, que es el que indican los logs.
    for encoding in ['utf-16', 'utf-8-sig', 'cp1252']: 
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            logger.info(f"Archivo '{file_path}' leído con éxito usando codificación '{encoding}'.")
            break 
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    
    if content is None:
        logger.error(f"Fallo crítico: No se pudo leer el archivo {file_path} con los códecs probados.")
        return None

    match = re.search(r"input\s+int\s+MagicNumber\s*=\s*(\d+)\s*;", content, re.IGNORECASE)
    
    if match:
        return int(match.group(1))
    else:
        logger.warning(f"No se encontró el patrón 'MagicNumber' en el archivo '{file_path}'.")
        return None

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Iniciando MT5 Wrapper API en http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port)

