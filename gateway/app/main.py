from fastapi import FastAPI, Depends, HTTPException, Security, Request
from fastapi.security import OAuth2PasswordRequestForm, HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST  # type: ignore[reportMissingImports]
import httpx  # type: ignore[reportMissingImports]
import os
import json
import traceback
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text
from .auth import (
    create_access_token,
    decode_token,
    verify_password,
    generate_totp,
    verify_totp,
)
from .db import SessionLocal, engine
from . import models
from .delivery_routes import router as delivery_router
from .routers.camaras import router as camaras_router

# ------------------------------------------------------
# CONFIGURACIÓN INICIAL
# ------------------------------------------------------

app = FastAPI(title="Gateway LuxChile ERP")

# Configuración de CORS (para entorno local/frontend Vite)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    # Allow localhost/127.0.0.1 and common LAN ranges on any port
    allow_origin_regex=r"https?://(localhost|127\\.0\\.0\\.1|192\\.168\\.[0-9]+\\.[0-9]+|10\\.[0-9]+\\.[0-9]+\\.[0-9]+|172\\.(1[6-9]|2[0-9]|3[0-1])\\.[0-9]+\\.[0-9]+)(:\\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Métricas Prometheus
REQUESTS = Counter("gateway_requests_total", "Total gateway HTTP requests")

security = HTTPBearer()

# Middleware para garantizar UTF-8 en todas las respuestas
class UTF8Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Asegurar que todas las respuestas JSON tengan charset=utf-8
        if response.headers.get('content-type', '').startswith('application/json'):
            response.headers['content-type'] = 'application/json; charset=utf-8'
        return response

app.add_middleware(UTF8Middleware)

# ------------------------------------------------------
# MANEJO GLOBAL DE ERRORES
# ------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logging.error("Unhandled exception: %s", str(exc))
    logging.error(tb)
    show_trace = os.environ.get("DEV", "1") == "1"
    return JSONResponse(
        status_code=500,
        content={
            "detail": "internal_server_error",
            "error": str(exc),
            "trace": tb if show_trace else None,
        },
    )

# ------------------------------------------------------
# AUTENTICACIÓN Y SEGURIDAD
# ------------------------------------------------------

def get_current_user(token: HTTPAuthorizationCredentials = Security(security)):
    try:
        payload = decode_token(token.credentials)
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


def rbac(required_roles: list):
    def checker(user=Depends(get_current_user)):
        roles = user.get("roles", [])
        if not any(r in roles for r in required_roles):
            raise HTTPException(status_code=403, detail="forbidden")
        return user
    return checker


@app.post("/auth/token")
async def token(form_data: OAuth2PasswordRequestForm = Depends()):
    # Ejemplo simple; en producción se valida contra la base de datos
    if form_data.username == "admin" and form_data.password == "admin":
        token = create_access_token(subject=form_data.username, extra={"roles": ["admin"]})
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=400, detail="Incorrect username or password")


@app.post("/auth/totp/setup")
async def totp_setup(user=Depends(get_current_user)):
    return generate_totp()


@app.post("/auth/totp/verify")
async def totp_verify(code: str, user=Depends(get_current_user)):
    secret = user.get("totp_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="no totp configured")
    ok = verify_totp(secret, code)
    return {"ok": ok}

# ------------------------------------------------------
# MÉTRICAS Y SALUD DEL SERVICIO
# ------------------------------------------------------

@app.get("/health")
async def health():
    REQUESTS.inc()
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

# ------------------------------------------------------
# BASE DE DATOS
# ------------------------------------------------------

try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    logging.error("Could not create DB tables at startup: %s", str(e))
    logging.debug("DB create_all exception", exc_info=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------------------------------
# PROXIES HACIA MS-RRHH
# ------------------------------------------------------

@app.api_route("/api/rrhh/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_rrhh(path_name: str, request: Request):
    """Proxy genérico para ms-rrhh"""
    base = os.environ.get("MS_RRHH_URL") or "http://ms-rrhh:8000"
    
    # Construir URL destino
    url = f"{base}/{path_name}"
    query_params = request.url.query
    if query_params:
        url += f"?{query_params}"
        
    try:
        async with httpx.AsyncClient() as client:
            # Forward headers (excluding host to avoid confusion)
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None) 
            
            content = await request.body()
            
            r = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=content,
                timeout=30.0
            )
            
        # Return response
        return Response(
            content=r.content,
            status_code=r.status_code,
            headers=dict(r.headers)
        )
            
    except httpx.RequestError as e:
        logging.error(f"ms-rrhh proxy error: {e}")
        return JSONResponse(status_code=502, content={"error": "ms_rrhh_unreachable", "detail": str(e)})
    except Exception as e:
        logging.error(f"ms-rrhh proxy unexpected error: {e}")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})


# ------------------------------------------------------
# PROXIES HACIA MS-INVENTARIO (MANTENCIONES)
# ------------------------------------------------------

@app.get("/api/maintenance/tasks")
async def get_maintenance_tasks():
    """Proxy para obtener tareas de mantención desde ms-inventario"""
    base = os.environ.get("MS_INVENTARIO_URL") or "http://127.0.0.1:8002"
    ms_url = f"{base}/maintenance/tasks"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(ms_url, timeout=20)
        content = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw_text": r.text}
        return JSONResponse(status_code=r.status_code, content=content)
    except httpx.RequestError as e:
        logging.error("ms-inventario maintenance tasks request failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": "ms_inventario_unreachable", "detail": str(e)})
    except Exception as e:
        logging.exception("Unexpected error when contacting ms-inventario maintenance")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})

@app.post("/api/maintenance/tasks")
async def create_maintenance_task(payload: dict):
    """Proxy para crear nueva tarea de mantención"""
    base = os.environ.get("MS_INVENTARIO_URL") or "http://127.0.0.1:8002"
    ms_url = f"{base}/maintenance/tasks"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(ms_url, json=payload, timeout=20)
        content = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw_text": r.text}
        return JSONResponse(status_code=r.status_code, content=content)
    except httpx.RequestError as e:
        logging.error("ms-inventario create maintenance task request failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": "ms_inventario_unreachable", "detail": str(e)})
    except Exception as e:
        logging.exception("Unexpected error when contacting ms-inventario maintenance")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})

@app.put("/api/maintenance/tasks/{task_id}")
async def update_maintenance_task(task_id: str, payload: dict):
    """Proxy para actualizar tarea de mantención"""
    base = os.environ.get("MS_INVENTARIO_URL") or "http://127.0.0.1:8002"
    ms_url = f"{base}/maintenance/tasks/{task_id}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.put(ms_url, json=payload, timeout=20)
        content = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw_text": r.text}
        return JSONResponse(status_code=r.status_code, content=content)
    except httpx.RequestError as e:
        logging.error("ms-inventario update maintenance task request failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": "ms_inventario_unreachable", "detail": str(e)})
    except Exception as e:
        logging.exception("Unexpected error when contacting ms-inventario maintenance")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})

@app.get("/api/maintenance/tasks/stats")
async def get_maintenance_stats():
    """Proxy para obtener estadísticas de mantención"""
    base = os.environ.get("MS_INVENTARIO_URL") or "http://127.0.0.1:8002"
    ms_url = f"{base}/maintenance/tasks/stats"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(ms_url, timeout=20)
        content = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw_text": r.text}
        return JSONResponse(status_code=r.status_code, content=content)
    except httpx.RequestError as e:
        logging.error("ms-inventario maintenance stats request failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": "ms_inventario_unreachable", "detail": str(e)})
    except Exception as e:
        logging.exception("Unexpected error when contacting ms-inventario maintenance stats")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})

@app.get("/api/maintenance/assets")
async def get_maintenance_assets():
    """Proxy para obtener activos de mantención"""
    base = os.environ.get("MS_INVENTARIO_URL") or "http://127.0.0.1:8002"
    ms_url = f"{base}/maintenance/assets"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(ms_url, timeout=20)
        content = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw_text": r.text}
        return JSONResponse(status_code=r.status_code, content=content)
    except httpx.RequestError as e:
        logging.error("ms-inventario maintenance assets request failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": "ms_inventario_unreachable", "detail": str(e)})
    except Exception as e:
        logging.exception("Unexpected error when contacting ms-inventario maintenance assets")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})

# ------------------------------------------------------
# PROXIES HACIA MS-LOGISTICA
# ------------------------------------------------------

@app.post("/maps/geocode")
async def maps_geocode(payload: dict):
    """Redirige solicitudes de geocodificación al microservicio de logística"""
    base = os.environ.get("MS_LOGISTICA_URL") or os.environ.get("MS_LOGISTICA_BASE")
    ms_url = f"{base}/maps/geocode" if base else "http://127.0.0.1:8001/maps/geocode"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(ms_url, json=payload, timeout=20)
        content = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw_text": r.text}
        return JSONResponse(status_code=r.status_code, content=content)
    except httpx.RequestError as e:
        logging.error("ms-logistica geocode request failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": "ms_logistica_unreachable", "detail": str(e)})
    except Exception as e:
        logging.exception("Unexpected error when contacting ms-logistica geocode")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})


@app.post("/maps/directions")
async def maps_directions(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Redirige solicitudes de direcciones (rutas) al microservicio de logística"""
    base = os.environ.get("MS_LOGISTICA_URL") or os.environ.get("MS_LOGISTICA_BASE")
    ms_url = f"{base}/maps/directions" if base else "http://127.0.0.1:8001/maps/directions"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(ms_url, json=payload, timeout=30)
    except httpx.RequestError as e:
        logging.error("ms-logistica directions request failed: %s", str(e))
        # Registro local del fallo (best effort)
        try:
            rr = models.RouteRequest(
                origin=json.dumps(payload.get("origin"), ensure_ascii=False),
                destination=json.dumps(payload.get("destination"), ensure_ascii=False),
                payload=json.dumps(payload, ensure_ascii=False),
                response=str(e),
                status="error:ms_unreachable",
            )
            db.add(rr)
            db.commit()
        except Exception:
            logging.debug("Failed to persist failed route request", exc_info=True)
        return JSONResponse(status_code=502, content={"error": "ms_logistica_unreachable", "detail": str(e)})

    except Exception as e:
        logging.exception("Unexpected error contacting ms-logistica directions")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})

    # Procesar respuesta
    body_text = r.text
    origin = payload.get("origin")
    destination = payload.get("destination")

    # Persistir la solicitud (best-effort)
    try:
        rr = models.RouteRequest(
            origin=origin,
            destination=destination,
            payload=json.dumps(payload, ensure_ascii=False),
            response=body_text,
            status="ok" if r.status_code == 200 else f"error:{r.status_code}",
        )
        db.add(rr)
        db.commit()
        db.refresh(rr)
    except Exception:
        logging.debug("warning: failed to persist route request", exc_info=True)

    try:
        content = r.json()
    except Exception:
        content = {"raw_text": body_text}
    return JSONResponse(status_code=r.status_code, content=content)

# ------------------------------------------------------
# ADMINISTRACIÓN DE RUTAS REGISTRADAS Y PROXY DE RUTAS
# ------------------------------------------------------

@app.post("/routes/optimize")
async def proxy_routes_optimize(payload: dict):
    base = os.environ.get("MS_LOGISTICA_URL") or os.environ.get("MS_LOGISTICA_BASE")
    ms_url = f"{base}/routes/optimize" if base else "http://127.0.0.1:8001/routes/optimize"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(ms_url, json=payload, timeout=30)
        try:
            content = r.json()
        except Exception:
            content = {"raw_text": r.text}
        return JSONResponse(status_code=r.status_code, content=content)
    except httpx.RequestError as e:
        logging.error("ms-logistica optimize request failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": "ms_logistica_unreachable", "detail": str(e)})
    except Exception as e:
        logging.exception("Unexpected error contacting ms-logistica optimize")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})

@app.get("/routes/{route_id}")
async def proxy_routes_get(route_id: int):
    base = os.environ.get("MS_LOGISTICA_URL") or os.environ.get("MS_LOGISTICA_BASE")
    ms_url = f"{base}/routes/{route_id}" if base else f"http://127.0.0.1:8001/routes/{route_id}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(ms_url, timeout=20)
        try:
            content = r.json()
        except Exception:
            content = {"raw_text": r.text}
        return JSONResponse(status_code=r.status_code, content=content)
    except httpx.RequestError as e:
        logging.error("ms-logistica get route failed: %s", str(e))
        return JSONResponse(status_code=502, content={"error": "ms_logistica_unreachable", "detail": str(e)})
    except Exception as e:
        logging.exception("Unexpected error contacting ms-logistica get route")
        return JSONResponse(status_code=500, content={"error": "internal_proxy_error", "detail": str(e)})

@app.get("/admin/route-requests")
def list_route_requests(limit: int = 100, db: Session = Depends(get_db)):
    items = db.query(models.RouteRequest).order_by(models.RouteRequest.created_at.desc()).limit(limit).all()
    return [
        {
            "id": i.id,
            "origin": i.origin,
            "destination": i.destination,
            "status": i.status,
            "created_at": (lambda dt: dt.isoformat() if dt is not None else None)(getattr(i, "created_at", None)),
        }
        for i in items
    ]


@app.get("/admin/route-requests/{request_id}")
def get_route_request(request_id: int, db: Session = Depends(get_db)):
    item = db.query(models.RouteRequest).filter(models.RouteRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": item.id,
        "origin": item.origin,
        "destination": item.destination,
        "payload": item.payload,
        "response": item.response,
        "status": item.status,
        "created_at": (lambda dt: dt.isoformat() if dt is not None else None)(getattr(item, "created_at", None)),
    }

# ------------------------------------------------------
# ENDPOINT PARA CONDUCTORES ACTIVOS (MS-RRHH)
# ------------------------------------------------------

@app.get("/api/drivers/active")
async def get_active_drivers(db: Session = Depends(get_db)):
    """
    Obtiene conductores activos desde la tabla employees (ms-rrhh)
    Retorna: Lista de conductores con role_id relacionado a 'Conductor'
    """
    try:
        # Query directo a PostgreSQL - tabla employees
        query = text("""
            SELECT 
                e.id,
                e.rut,
                e.nombre,
                e.email,
                e.activo,
                e.role_id,
                r.nombre as role_name
            FROM employees e
            LEFT JOIN roles r ON e.role_id = r.id
            WHERE e.activo = TRUE
            AND (r.nombre ILIKE '%conductor%' OR r.nombre ILIKE '%driver%' OR e.role_id IN (
                SELECT id FROM roles WHERE nombre IN ('Conductor', 'Driver', 'Chofer')
            ))
            ORDER BY e.nombre
        """)
        result = db.execute(query)
        drivers = []
        for row in result:
            drivers.append({
                "id": row[0],
                "rut": row[1],
                "nombre": row[2],
                "email": row[3],
                "activo": row[4],
                "role_id": row[5],
                "role_name": row[6] if len(row) > 6 else None
            })
        
        logging.info(f"✓ Conductores activos encontrados: {len(drivers)}")
        return {"drivers": drivers, "count": len(drivers)}
    
    except Exception as e:
        logging.error(f"❌ Error al obtener conductores: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al consultar conductores: {str(e)}")


@app.post("/api/routes/assign")
async def assign_route_to_driver(payload: dict, db: Session = Depends(get_db)):
    """
    Registra asignación de ruta a conductor en delivery_requests
    Payload: {
        "driver_id": 1,
        "driver_name": "Juan Pérez",
        "origin": "...",
        "destination": "...",
        "route_data": { polyline, distance, duration }
    }
    """
    try:
        from sqlalchemy import text
        driver_id = payload.get("driver_id")
        driver_name = payload.get("driver_name")
        origin = payload.get("origin")
        destination = payload.get("destination")
        route_data = payload.get("route_data", {})
        
        if not driver_id or not origin or not destination:
            raise HTTPException(status_code=400, detail="Faltan campos requeridos: driver_id, origin, destination")
        
        # Insertar en delivery_requests usando columnas correctas de la tabla
        import json
        insert_query = text("""
            INSERT INTO delivery_requests 
                (origin_address, destination_address, driver_id, status, notes)
            VALUES 
                (:origin, :destination, :driver_id, :status, :notes)
            RETURNING id, created_at
        """)
        
        # Convertir origin y destination a string de direcciones si son objetos
        origin_address = origin if isinstance(origin, str) else origin.get('address', str(origin))
        destination_address = destination if isinstance(destination, str) else destination.get('address', str(destination))
        
        result = db.execute(insert_query, {
            "origin": origin_address,
            "destination": destination_address,
            "driver_id": driver_id,
            "status": "assigned",
            "notes": f"Ruta - {driver_name}"
        })
        db.commit()
        
        row = result.fetchone()
        request_id = row[0]
        created_at = row[1]
        tracking_number = f"RT-{request_id:06d}"
        
        logging.info(f"✓ Ruta asignada ID: {request_id}, Conductor: {driver_name} (ID: {driver_id}), Tracking: {tracking_number}")
        
        return {
            "success": True,
            "request_id": request_id,
            "tracking_number": tracking_number,
            "driver_id": driver_id,
            "driver_name": driver_name,
            "created_at": created_at.isoformat() if created_at else None,
            "message": f"Ruta asignada a {driver_name}"
        }
    
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al asignar ruta: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al asignar ruta: {str(e)}")


@app.post("/api/rrhh/sync-route")
async def sync_route_with_rrhh(payload: dict, db: Session = Depends(get_db)):
    """
    Sincroniza ruta con sistema de RR.HH. (dinámico)
    Crea registro de asignación de turno dinámico basado en la ruta
    Payload: {
        "tracking_number": "RT-000001",
        "driver_id": 1,
        "driver_name": "Juan Pérez",
        "route_data": { origin, destination, distance_m, duration_s, estimated_start }
    }
    """
    try:
        from sqlalchemy import text
        from datetime import datetime, timedelta
        
        tracking_number = payload.get("tracking_number")
        driver_id = payload.get("driver_id")
        driver_name = payload.get("driver_name")
        route_data = payload.get("route_data", {})
        
        logging.info(f"🔄 Sincronizando ruta con RR.HH.: {tracking_number}, Driver: {driver_id}")
        
        if not tracking_number or not driver_id:
            raise HTTPException(status_code=400, detail="Faltan campos requeridos: tracking_number, driver_id")
        
        # Calcular duración estimada en minutos
        duration_minutes = route_data.get("duration_s", 0) // 60
        if duration_minutes == 0:
            duration_minutes = 30  # Mínimo 30 minutos
        
        logging.info(f"⏱️ Duración calculada: {duration_minutes} minutos")
        
        # Fecha y hora de inicio estimada
        estimated_start = route_data.get("estimated_start")
        if estimated_start:
            try:
                start_datetime = datetime.fromisoformat(estimated_start.replace('Z', '+00:00'))
            except Exception as e:
                logging.warning(f"⚠️ Error parseando fecha, usando ahora: {e}")
                start_datetime = datetime.now()
        else:
            start_datetime = datetime.now()
        
        logging.info(f"📅 Fecha/hora inicio: {start_datetime}")
        
        # Extraer route_id del tracking_number (formato: RT-000001 → id=1)
        route_id = None
        if tracking_number and tracking_number.startswith("RT-"):
            try:
                route_id = int(tracking_number.split("-")[1])
                logging.info(f"🔗 route_id extraído: {route_id}")
            except (IndexError, ValueError) as e:
                logging.warning(f"⚠️ No se pudo extraer route_id de {tracking_number}: {e}")
        
        # Crear turno dinámico en la tabla dynamic_shifts
        # FLUJO DIRECTO: Ruta creada desde Mapa ya está confirmada y lista para ejecutar
        insert_dynamic_shift = text("""
            INSERT INTO dynamic_shifts 
                (route_id, fecha_programada, hora_inicio, duracion_minutos, status)
            VALUES 
                (:route_id, :fecha, :hora, :duracion, :status)
            RETURNING id
        """)
        
        result = db.execute(insert_dynamic_shift, {
            "route_id": route_id,
            "fecha": start_datetime.date(),
            "hora": start_datetime.time(),
            "duracion": duration_minutes,
            "status": "asignado"  # ✅ OPTIMIZADO: Ruta lista para ejecutar inmediatamente
        })
        
        dynamic_shift_id = result.fetchone()[0]
        logging.info(f"✅ Turno dinámico creado: ID={dynamic_shift_id}")
        
        # Asignar conductor al turno dinámico
        insert_assignment = text("""
            INSERT INTO dynamic_shift_assignments 
                (dynamic_shift_id, employee_id, role_in_shift, status)
            VALUES 
                (:shift_id, :employee_id, :role, :status)
        """)
        
        db.execute(insert_assignment, {
            "shift_id": dynamic_shift_id,
            "employee_id": driver_id,
            "role": "Conductor Principal",
            "status": "asignado"
        })
        
        db.commit()
        
        logging.info(f"✅ Sincronizado con RR.HH.: Turno dinámico {dynamic_shift_id} para {driver_name}")
        
        return {
            "success": True,
            "dynamic_shift_id": dynamic_shift_id,
            "driver_id": driver_id,
            "driver_name": driver_name,
            "message": f"Turno dinámico creado para {driver_name}",
            "debug": {
                "fecha": str(start_datetime.date()),
                "hora": str(start_datetime.time()),
                "duracion_minutos": duration_minutes,
                "status": "asignado"
            }
        }
    
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al sincronizar con RR.HH.: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al sincronizar con RR.HH.: {str(e)}")



@app.get("/api/rrhh/dynamic-shifts/pending")
async def get_pending_dynamic_shifts(db: Session = Depends(get_db)):
    """
    Obtiene turnos dinámicos VERDADERAMENTE PENDIENTES
    CRITERIO: Turnos que el usuario AÚN NO ha visto/aceptado en el calendario
    
    Lógica: Como todos los turnos se crean con status='asignado' automáticamente
    desde MapView, consideramos "pendientes" aquellos que el usuario puede eliminar
    sin afectar el sistema. En este caso, devolvemos CERO turnos si todos ya fueron
    procesados por el sistema.
    
    ACTUALIZACIÓN: Retornar solo turnos con status='pendiente' explícitamente
    """
    try:
        from sqlalchemy import text
        
        # Cambio de estrategia: Solo mostrar turnos que explícitamente tienen status='pendiente'
        # Los turnos con status='asignado' YA están en el calendario y no deben aparecer aquí
        query = text("""
            SELECT 
                ds.id,
                ds.fecha_programada,
                ds.hora_inicio,
                ds.duracion_minutos,
                ds.conduccion_continua_minutos,
                ds.status,
                ds.route_id,
                ds.created_at,
                ds.assigned_at,
                ds.completed_at
            FROM dynamic_shifts ds
            WHERE ds.status = 'pendiente'
            AND ds.status NOT IN ('completado', 'cancelado')
            ORDER BY ds.fecha_programada DESC, ds.hora_inicio DESC
        """)
        
        result = db.execute(query)
        shifts = []
        
        for row in result:
            shifts.append({
                "id": row[0],
                "fecha_programada": row[1].isoformat() if row[1] else None,
                "hora_inicio": str(row[2]) if row[2] else None,
                "duracion_minutos": row[3],
                "conduccion_continua_minutos": row[4] or 300,
                "status": row[5],
                "route_id": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
                "assigned_at": row[8].isoformat() if row[8] else None,
                "completed_at": row[9].isoformat() if row[9] else None
            })
        
        return shifts
    
    except Exception as e:
        logging.error(f"❌ Error al obtener turnos dinámicos: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al obtener turnos dinámicos: {str(e)}")


@app.get("/api/rrhh/dynamic-shifts")
async def list_dynamic_shifts(db: Session = Depends(get_db)):
    """
    Lista todos los turnos dinámicos con detalles incluyendo asignaciones
    """
    try:
        from sqlalchemy import text
        
        # Query principal: obtener turnos dinámicos
        query = text("""
            SELECT 
                ds.id,
                ds.route_id,
                ds.fecha_programada,
                ds.hora_inicio,
                ds.duracion_minutos,
                ds.status
            FROM dynamic_shifts ds
            ORDER BY ds.fecha_programada DESC, ds.hora_inicio DESC
        """)
        
        result = db.execute(query)
        shifts = []
        
        # Query para obtener asignaciones
        assignments_query = text("""
            SELECT 
                dsa.dynamic_shift_id,
                dsa.employee_id,
                e.nombre,
                e.email,
                dsa.role_in_shift,
                dsa.status
            FROM dynamic_shift_assignments dsa
            JOIN employees e ON dsa.employee_id = e.id
            ORDER BY dsa.dynamic_shift_id, dsa.employee_id
        """)
        
        assignments_result = db.execute(assignments_query)
        
        # Agrupar asignaciones por shift_id
        assignments_by_shift = {}
        for asg_row in assignments_result:
            shift_id = asg_row[0]
            if shift_id not in assignments_by_shift:
                assignments_by_shift[shift_id] = []
            assignments_by_shift[shift_id].append({
                "employee_id": asg_row[1],
                "nombre": asg_row[2],
                "email": asg_row[3],
                "role_in_shift": asg_row[4],
                "status": asg_row[5]
            })
        
        # Construir respuesta con asignaciones
        for row in result:
            shift_id = row[0]
            shift_assignments = assignments_by_shift.get(shift_id, [])
            
            shifts.append({
                "id": shift_id,
                "route_id": row[1],
                "fecha_programada": row[2].isoformat() if row[2] else None,
                "hora_inicio": str(row[3]) if row[3] else None,
                "duracion_minutos": row[4],
                "status": row[5],
                "num_assignments": len(shift_assignments),
                "conductores": ", ".join([a["nombre"] for a in shift_assignments]) if shift_assignments else "Sin asignar",
                "assignments": shift_assignments  # ✅ Datos estructurados para frontend
            })
        
        return shifts
    
    except Exception as e:
        logging.error(f"❌ Error al listar turnos dinámicos: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al listar turnos dinámicos: {str(e)}")


@app.get("/api/rrhh/dynamic-shifts/available-drivers/{shift_id}")
async def get_available_drivers_for_shift(shift_id: int, db: Session = Depends(get_db)):
    """
    Obtiene conductores disponibles para un turno dinámico
    Retorna lista vacía para compatibilidad con frontend
    """
    try:
        from sqlalchemy import text
        
        # Por ahora retornamos lista vacía ya que no tenemos la lógica completa
        # El frontend puede manejar esto mostrando "Sin disponibles"
        return []
    
    except Exception as e:
        logging.error(f"❌ Error al obtener conductores disponibles: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al obtener conductores: {str(e)}")


@app.post("/api/rrhh/dynamic-shifts/{shift_id}/auto-assign")
async def auto_assign_driver_to_shift(shift_id: int, employee_id: int, db: Session = Depends(get_db)):
    """
    Asigna un conductor a un turno dinámico (confirmación desde RR.HH.)
    LOGICA MEJORADA: Cambia el status del turno de 'pendiente' a 'asignado'
    """
    try:
        from sqlalchemy import text
        
        # 1. Actualizar la asignación existente
        update_assignment = text("""
            UPDATE dynamic_shift_assignments
            SET employee_id = :employee_id, status = 'asignado', assigned_at = NOW()
            WHERE dynamic_shift_id = :shift_id
        """)
        
        db.execute(update_assignment, {"employee_id": employee_id, "shift_id": shift_id})
        
        # 2. Actualizar el dynamic_shift a 'asignado' (confirmado por RR.HH.)
        update_shift = text("""
            UPDATE dynamic_shifts
            SET status = 'asignado', assigned_at = NOW()
            WHERE id = :shift_id
        """)
        
        db.execute(update_shift, {"shift_id": shift_id})
        
        # 3. Actualizar el delivery_request también (sincronización completa)
        update_delivery = text("""
            UPDATE delivery_requests dr
            SET driver_id = :employee_id, status = 'assigned', updated_at = NOW()
            FROM dynamic_shifts ds
            WHERE ds.id = :shift_id AND ds.route_id = dr.id
        """)
        
        db.execute(update_delivery, {"employee_id": employee_id, "shift_id": shift_id})
        
        db.commit()
        
        logging.info(f"✓ Conductor {employee_id} asignado a turno {shift_id} - CONFIRMADO por RR.HH.")
        
        return {"success": True, "message": "Conductor asignado y turno confirmado"}
    
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al asignar conductor: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al asignar: {str(e)}")


@app.delete("/api/rrhh/dynamic-shifts/{shift_id}/unassign")
async def unassign_driver_from_shift(shift_id: int, db: Session = Depends(get_db)):
    """
    Desasigna un conductor de un turno dinámico - ELIMINACIÓN COMPLETA
    """
    try:
        from sqlalchemy import text
        
        # 1. Eliminar asignaciones (dynamic_shift_assignments)
        delete_assignments = text("""
            DELETE FROM dynamic_shift_assignments
            WHERE dynamic_shift_id = :shift_id
        """)
        
        db.execute(delete_assignments, {"shift_id": shift_id})
        
        # 2. Eliminar el dynamic_shift (esto activará el trigger que elimina shift_assignment)
        delete_shift = text("""
            DELETE FROM dynamic_shifts
            WHERE id = :shift_id
        """)
        
        db.execute(delete_shift, {"shift_id": shift_id})
        
        db.commit()
        
        logging.info(f"✅ Turno dinámico {shift_id} eliminado completamente (incluido calendario)")
        
        return {"success": True, "message": "Turno eliminado completamente"}
    
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al eliminar turno: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al eliminar: {str(e)}")


@app.get("/api/rrhh/employees")
async def get_employees(db: Session = Depends(get_db)):
    """
    Obtiene la lista de empleados activos
    Compatible con el frontend de RR.HH.
    """
    try:
        from sqlalchemy import text
        
        query = text("""
            SELECT 
                id,
                nombre,
                email,
                rut,
                activo,
                created_at
            FROM employees
            WHERE activo = true
            ORDER BY nombre
        """)
        
        result = db.execute(query)
        rows = result.fetchall()
        
        employees = []
        for row in rows:
            employees.append({
                "id": row[0],
                "nombre": row[1],
                "email": row[2],
                "rut": row[3],
                "activo": row[4],
                "created_at": row[5].isoformat() if row[5] else None
            })
        
        logging.info(f"📋 Listado de empleados: {len(employees)} encontrados")
        
        return employees
    
    except Exception as e:
        logging.error(f"❌ Error al obtener empleados: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al obtener empleados: {str(e)}")


@app.delete("/api/rrhh/dynamic-shifts/cleanup")
async def cleanup_old_pending_shifts(db: Session = Depends(get_db)):
    """
    Elimina turnos pendientes antiguos (más de 24 horas sin confirmar)
    MANTENIMIENTO: Ejecutar periódicamente para limpiar turnos no confirmados
    """
    try:
        from sqlalchemy import text
        
        # Eliminar turnos pendientes con más de 24 horas
        delete_query = text("""
            DELETE FROM dynamic_shifts
            WHERE status = 'pendiente'
            AND created_at < NOW() - INTERVAL '24 hours'
            RETURNING id
        """)
        
        result = db.execute(delete_query)
        deleted_ids = [row[0] for row in result.fetchall()]
        db.commit()
        
        logging.info(f"🗑️ Limpieza automática: {len(deleted_ids)} turnos pendientes eliminados")
        
        return {
            "success": True,
            "deleted_count": len(deleted_ids),
            "deleted_ids": deleted_ids,
            "message": f"{len(deleted_ids)} turnos pendientes antiguos eliminados"
        }
    
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al limpiar turnos: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al limpiar: {str(e)}")


# ============================================================================
# ENDPOINTS DE TURNOS REGULARES (Sistema tradicional de shifts/assignments)
# ============================================================================

@app.get("/api/rrhh/shifts")
async def get_shifts(db: Session = Depends(get_db)):
    """
    Obtiene todos los turnos regulares (plantillas de turno)
    Ejemplo: Mañana (08:00-16:00), Tarde (16:00-00:00), Noche (00:00-08:00)
    """
    try:
        from sqlalchemy import text
        
        query = text("""
            SELECT id, tipo, start_time, end_time, timezone, created_at
            FROM shifts
            ORDER BY start_time
        """)
        
        result = db.execute(query)
        shifts = []
        
        for row in result:
            shifts.append({
                "id": row[0],
                "tipo": row[1],
                "start_time": str(row[2]) if row[2] else None,
                "end_time": str(row[3]) if row[3] else None,
                "timezone": row[4] or "America/Santiago",
                "created_at": row[5].isoformat() if row[5] else None
            })
        
        logging.info(f"📋 Turnos regulares: {len(shifts)} encontrados")
        return shifts
    
    except Exception as e:
        logging.error(f"❌ Error al obtener turnos: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al obtener turnos: {str(e)}")


@app.post("/api/rrhh/shifts")
async def create_shift(shift_data: dict, db: Session = Depends(get_db)):
    """
    Crea un nuevo turno regular (plantilla)
    """
    try:
        from sqlalchemy import text
        
        insert_query = text("""
            INSERT INTO shifts (tipo, start_time, end_time, timezone)
            VALUES (:tipo, :start_time, :end_time, :timezone)
            RETURNING id, tipo, start_time, end_time, timezone, created_at
        """)
        
        result = db.execute(insert_query, {
            "tipo": shift_data.get("tipo"),
            "start_time": shift_data.get("start_time"),
            "end_time": shift_data.get("end_time"),
            "timezone": shift_data.get("timezone", "America/Santiago")
        })
        
        row = result.fetchone()
        db.commit()
        
        return {
            "id": row[0],
            "tipo": row[1],
            "start_time": str(row[2]),
            "end_time": str(row[3]),
            "timezone": row[4],
            "created_at": row[5].isoformat()
        }
    
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al crear turno: {e}")
        raise HTTPException(status_code=500, detail=f"Error al crear turno: {str(e)}")


@app.get("/api/rrhh/assignments")
async def list_assignments(
    employee_id: int = None,
    from_date: str = None,
    to_date: str = None,
    db: Session = Depends(get_db)
):
    """
    Lista asignaciones de turnos regulares
    Filtros opcionales: employee_id, from_date, to_date
    """
    try:
        from sqlalchemy import text
        
        # Construir query dinámicamente según filtros
        where_clauses = []
        params = {}
        
        if employee_id:
            where_clauses.append("sa.employee_id = :employee_id")
            params["employee_id"] = employee_id
        
        if from_date:
            where_clauses.append("sa.date >= :from_date")
            params["from_date"] = from_date
        
        if to_date:
            where_clauses.append("sa.date <= :to_date")
            params["to_date"] = to_date
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = text(f"""
            SELECT 
                sa.id,
                sa.employee_id,
                sa.shift_id,
                sa.date,
                e.nombre as employee_name,
                s.tipo as shift_type
            FROM shift_assignments sa
            LEFT JOIN employees e ON sa.employee_id = e.id
            LEFT JOIN shifts s ON sa.shift_id = s.id
            {where_sql}
            ORDER BY sa.date DESC, s.start_time
        """)
        
        result = db.execute(query, params)
        assignments = []
        
        for row in result:
            assignments.append({
                "id": row[0],
                "employee_id": row[1],
                "shift_id": row[2],
                "date": row[3].isoformat() if row[3] else None,
                "employee_name": row[4],
                "shift_type": row[5]
            })
        
        logging.info(f"📋 Asignaciones: {len(assignments)} encontradas")
        return assignments
    
    except Exception as e:
        logging.error(f"❌ Error al listar asignaciones: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al listar asignaciones: {str(e)}")


@app.post("/api/rrhh/assignments")
async def create_assignment(assignment_data: dict, db: Session = Depends(get_db)):
    """
    Crea una nueva asignación de turno regular
    """
    try:
        from sqlalchemy import text
        
        # Verificar si ya existe una asignación para ese empleado en esa fecha
        check_query = text("""
            SELECT id FROM shift_assignments
            WHERE employee_id = :employee_id AND date = :date
        """)
        
        existing = db.execute(check_query, {
            "employee_id": assignment_data.get("employee_id"),
            "date": assignment_data.get("date")
        }).fetchone()
        
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Este empleado ya tiene un turno asignado en esta fecha"
            )
        
        insert_query = text("""
            INSERT INTO shift_assignments (employee_id, shift_id, date)
            VALUES (:employee_id, :shift_id, :date)
            RETURNING id, employee_id, shift_id, date
        """)
        
        result = db.execute(insert_query, {
            "employee_id": assignment_data.get("employee_id"),
            "shift_id": assignment_data.get("shift_id"),
            "date": assignment_data.get("date")
        })
        
        row = result.fetchone()
        db.commit()
        
        return {
            "id": row[0],
            "employee_id": row[1],
            "shift_id": row[2],
            "date": row[3].isoformat()
        }
    
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al crear asignación: {e}")
        raise HTTPException(status_code=500, detail=f"Error al crear asignación: {str(e)}")


@app.delete("/api/rrhh/assignments/{assignment_id}")
async def delete_assignment(assignment_id: int, db: Session = Depends(get_db)):
    """
    Elimina una asignación de turno regular
    """
    try:
        from sqlalchemy import text
        
        delete_query = text("""
            DELETE FROM shift_assignments
            WHERE id = :id
            RETURNING id
        """)
        
        result = db.execute(delete_query, {"id": assignment_id})
        deleted = result.fetchone()
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Asignación no encontrada")
        
        db.commit()
        logging.info(f"✓ Asignación {assignment_id} eliminada")
        
        return {"success": True, "message": "Asignación eliminada correctamente"}
    
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al eliminar asignación: {e}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar: {str(e)}")


@app.get("/api/rrhh/assignments/suggestions/weekly")
async def get_weekly_suggestions(db: Session = Depends(get_db)):
    """
    Obtiene sugerencias semanales de asignación de turnos
    Retorna empleados sin asignar y turnos sin cubrir
    """
    try:
        from sqlalchemy import text
        from datetime import datetime, timedelta
        
        # Calcular inicio y fin de semana
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        # Empleados sin asignar esta semana
        unassigned_query = text("""
            SELECT 
                e.id,
                e.nombre,
                e.email,
                COUNT(sa.id) as assignments_this_week
            FROM employees e
            LEFT JOIN shift_assignments sa ON e.id = sa.employee_id
                AND sa.date BETWEEN :week_start AND :week_end
            WHERE e.activo = true
            GROUP BY e.id, e.nombre, e.email
            HAVING COUNT(sa.id) = 0
            ORDER BY e.nombre
        """)
        
        result = db.execute(unassigned_query, {
            "week_start": week_start,
            "week_end": week_end
        })
        
        unassigned_employees = []
        for row in result:
            unassigned_employees.append({
                "id": row[0],
                "nombre": row[1],
                "email": row[2],
                "assignments_this_week": row[3]
            })
        
        # Turnos sin cubrir (simplificado)
        uncovered_shifts = []
        
        # Estadísticas generales
        stats_query = text("""
            SELECT 
                COUNT(DISTINCT e.id) as total_employees,
                COUNT(DISTINCT s.id) as total_shifts,
                COUNT(sa.id) as total_assignments
            FROM employees e
            CROSS JOIN shifts s
            LEFT JOIN shift_assignments sa ON sa.date BETWEEN :week_start AND :week_end
            WHERE e.activo = true
        """)
        
        stats = db.execute(stats_query, {
            "week_start": week_start,
            "week_end": week_end
        }).fetchone()
        
        return {
            "unassigned_employees": unassigned_employees,
            "uncovered_shifts": uncovered_shifts,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "total_employees": stats[0] or 0,
            "total_shifts": stats[1] or 0,
            "total_assignments_this_week": stats[2] or 0
        }
    
    except Exception as e:
        logging.error(f"❌ Error al obtener sugerencias: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al obtener sugerencias: {str(e)}")


# ------------------------------------------------------
# CAPACITACIONES (TRAININGS)
# ------------------------------------------------------

@app.get("/api/rrhh/trainings")
async def list_trainings(db: Session = Depends(get_db)):
    """
    Lista todas las capacitaciones disponibles
    Trazabilidad: trainings → employee_trainings → employees
    """
    try:
        result = db.execute(text("""
            SELECT 
                t.id,
                t.title,
                t.topic,
                t.required,
                t.created_at,
                COUNT(DISTINCT et.employee_id) as enrolled_employees
            FROM trainings t
            LEFT JOIN employee_trainings et ON t.id = et.training_id
            GROUP BY t.id, t.title, t.topic, t.required, t.created_at
            ORDER BY t.created_at DESC
        """))
        
        trainings = []
        for row in result:
            trainings.append({
                "id": row[0],
                "title": row[1],
                "topic": row[2],
                "required": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
                "enrolled_employees": row[5]
            })
        
        return {"trainings": trainings, "total": len(trainings)}
    
    except Exception as e:
        logging.error(f"❌ Error al listar capacitaciones: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rrhh/trainings", status_code=201)
async def create_training(
    title: str,
    topic: str = "",
    required: bool = False,
    db: Session = Depends(get_db)
):
    """
    Crea una nueva capacitación
    """
    try:
        result = db.execute(text("""
            INSERT INTO trainings (title, topic, required, created_at)
            VALUES (:title, :topic, :required, NOW())
            RETURNING id, title, topic, required, created_at
        """), {
            "title": title,
            "topic": topic,
            "required": required
        })
        db.commit()
        
        training = result.fetchone()
        return {
            "id": training[0],
            "title": training[1],
            "topic": training[2],
            "required": training[3],
            "created_at": training[4].isoformat() if training[4] else None,
            "message": "Capacitación creada exitosamente"
        }
    
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al crear capacitación: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rrhh/trainings/{training_id}/enroll/{employee_id}")
async def enroll_employee(training_id: int, employee_id: int, db: Session = Depends(get_db)):
    """
    Inscribe un empleado en una capacitación
    Trazabilidad: employee → employee_trainings → training
    """
    try:
        # Verificar que el empleado y la capacitación existan
        employee = db.execute(text("SELECT id, nombre FROM employees WHERE id = :id"), {"id": employee_id}).fetchone()
        if not employee:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        
        training = db.execute(text("SELECT id, title FROM trainings WHERE id = :id"), {"id": training_id}).fetchone()
        if not training:
            raise HTTPException(status_code=404, detail="Capacitación no encontrada")
        
        # Verificar si ya está inscrito
        existing = db.execute(text("""
            SELECT id FROM employee_trainings 
            WHERE employee_id = :emp_id AND training_id = :train_id
        """), {"emp_id": employee_id, "train_id": training_id}).fetchone()
        
        if existing:
            raise HTTPException(status_code=400, detail="El empleado ya está inscrito en esta capacitación")
        
        # Inscribir
        result = db.execute(text("""
            INSERT INTO employee_trainings (employee_id, training_id, date, status, instructor)
            VALUES (:emp_id, :train_id, CURRENT_DATE, 'ENROLLED', 'Sistema')
            RETURNING id, date, status
        """), {"emp_id": employee_id, "train_id": training_id})
        db.commit()
        
        enrollment = result.fetchone()
        return {
            "id": enrollment[0],
            "employee_id": employee_id,
            "employee_name": employee[1],
            "training_id": training_id,
            "training_title": training[1],
            "date": enrollment[1].isoformat() if enrollment[1] else None,
            "status": enrollment[2],
            "message": f"Empleado {employee[1]} inscrito en {training[1]}"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al inscribir empleado: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rrhh/trainings/{training_id}/employees")
async def get_training_employees(training_id: int, db: Session = Depends(get_db)):
    """
    Obtiene los empleados inscritos en una capacitación
    Trazabilidad: training → employee_trainings → employees
    """
    try:
        result = db.execute(text("""
            SELECT 
                e.id,
                e.nombre,
                e.email,
                et.date,
                et.status,
                et.instructor,
                et.certificate_url
            FROM employee_trainings et
            INNER JOIN employees e ON et.employee_id = e.id
            WHERE et.training_id = :training_id
            ORDER BY et.date DESC
        """), {"training_id": training_id})
        
        employees = []
        for row in result:
            employees.append({
                "id": row[0],
                "nombre": row[1],
                "email": row[2],
                "date": row[3].isoformat() if row[3] else None,
                "status": row[4],
                "instructor": row[5],
                "certificate_url": row[6]
            })
        
        return {"training_id": training_id, "employees": employees, "total": len(employees)}
    
    except Exception as e:
        logging.error(f"❌ Error al obtener empleados de capacitación: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rrhh/employees/{employee_id}/trainings")
async def get_employee_trainings(employee_id: int, db: Session = Depends(get_db)):
    """
    Obtiene las capacitaciones de un empleado
    Trazabilidad: employee → employee_trainings → trainings
    """
    try:
        result = db.execute(text("""
            SELECT 
                t.id,
                t.title,
                t.topic,
                t.required,
                et.date,
                et.status,
                et.instructor,
                et.certificate_url
            FROM employee_trainings et
            INNER JOIN trainings t ON et.training_id = t.id
            WHERE et.employee_id = :employee_id
            ORDER BY et.date DESC
        """), {"employee_id": employee_id})
        
        trainings = []
        for row in result:
            trainings.append({
                "id": row[0],
                "title": row[1],
                "topic": row[2],
                "required": row[3],
                "date": row[4].isoformat() if row[4] else None,
                "status": row[5],
                "instructor": row[6],
                "certificate_url": row[7]
            })
        
        return {"employee_id": employee_id, "trainings": trainings, "total": len(trainings)}
    
    except Exception as e:
        logging.error(f"❌ Error al obtener capacitaciones del empleado: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------
# MÓDULO DE SEGURIDAD E INCIDENTES
# ------------------------------------------------------

@app.get("/api/incidents")
@app.get("/maps/incidents")
async def get_incidents(
    delivery_request_id: int = None,
    route_id: int = None,
    vehicle_id: int = None,
    driver_id: int = None,
    severity: str = None,
    type: str = None,
    limit: int = 100,
    offset: int = 0,
    order: str = "desc",
    db: Session = Depends(get_db)
):
    """
    Obtiene historial de incidentes con filtros opcionales
    """
    try:
        from sqlalchemy import text
        
        # Construir query dinámica según filtros
        conditions = []
        params = {"limit": limit, "offset": offset}
        
        if delivery_request_id:
            conditions.append("i.delivery_request_id = :delivery_request_id")
            params["delivery_request_id"] = delivery_request_id
        
        if route_id:
            conditions.append("i.route_id = :route_id")
            params["route_id"] = route_id
        
        if vehicle_id:
            conditions.append("i.vehicle_id = :vehicle_id")
            params["vehicle_id"] = vehicle_id
        
        if driver_id:
            conditions.append("i.driver_id = :driver_id")
            params["driver_id"] = driver_id
        
        if severity:
            conditions.append("i.severity = :severity")
            params["severity"] = severity
        
        if type:
            conditions.append("i.type = :type")
            params["type"] = type
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        order_clause = "DESC" if order == "desc" else "ASC"
        
        query = text(f"""
            SELECT 
                i.id,
                i.delivery_request_id,
                i.route_id,
                i.route_stop_id,
                i.vehicle_id,
                i.driver_id,
                i.severity,
                i.type,
                i.description,
                i.created_at,
                dr.origin_address,
                dr.destination_address,
                dr.status as delivery_status
            FROM incidents i
            LEFT JOIN delivery_requests dr ON i.delivery_request_id = dr.id
            {where_clause}
            ORDER BY i.created_at {order_clause}
            LIMIT :limit OFFSET :offset
        """)
        
        result = db.execute(query, params)
        incidents = []
        
        for row in result:
            incidents.append({
                "id": row[0],
                "delivery_request_id": row[1],
                "route_id": row[2],
                "route_stop_id": row[3],
                "vehicle_id": row[4],
                "driver_id": row[5],
                "severity": row[6],
                "type": row[7],
                "description": row[8],
                "created_at": row[9].isoformat() if row[9] else None,
                "origin_address": row[10],
                "destination_address": row[11],
                "delivery_status": row[12]
            })
        
        logging.info(f"📋 Incidentes encontrados: {len(incidents)}")
        return incidents
    
    except Exception as e:
        logging.error(f"❌ Error al obtener incidentes: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al obtener incidentes: {str(e)}")


@app.post("/api/incidents")
@app.post("/maps/incidents")
async def create_incident(payload: dict, db: Session = Depends(get_db)):
    """
    Registra un nuevo incidente de seguridad
    Payload: {
        "delivery_request_id": 1,
        "type": "theft|accident|assault|breakdown|smoke|lost_contact|delay",
        "description": "...",
        "vehicle_id": (opcional),
        "driver_id": (opcional)
    }
    """
    try:
        from sqlalchemy import text
        
        delivery_request_id = payload.get("delivery_request_id")
        incident_type = payload.get("type")
        description = payload.get("description")
        vehicle_id = payload.get("vehicle_id")
        driver_id = payload.get("driver_id")
        
        if not delivery_request_id or not incident_type or not description:
            raise HTTPException(
                status_code=400,
                detail="Campos requeridos: delivery_request_id, type, description"
            )
        
        # Derivar severidad automáticamente según tipo
        severity_map = {
            "theft": "high",
            "accident": "high",
            "assault": "high",
            "breakdown": "medium",
            "smoke": "medium",
            "lost_contact": "medium",
            "delay": "low"
        }
        severity = severity_map.get(incident_type, "medium")
        
        # Obtener vehicle_id y driver_id de delivery_request si no se proporcionan
        if not vehicle_id or not driver_id:
            dr_query = text("""
                SELECT vehicle_id, driver_id
                FROM delivery_requests
                WHERE id = :dr_id
            """)
            dr_result = db.execute(dr_query, {"dr_id": delivery_request_id}).fetchone()
            
            if dr_result:
                vehicle_id = vehicle_id or dr_result[0]
                driver_id = driver_id or dr_result[1]
        
        # Insertar incidente
        insert_query = text("""
            INSERT INTO incidents 
                (delivery_request_id, vehicle_id, driver_id, severity, type, description, created_at)
            VALUES 
                (:dr_id, :vehicle_id, :driver_id, :severity, :type, :description, NOW())
            RETURNING id, created_at
        """)
        
        result = db.execute(insert_query, {
            "dr_id": delivery_request_id,
            "vehicle_id": vehicle_id,
            "driver_id": driver_id,
            "severity": severity,
            "type": incident_type,
            "description": description
        })
        db.commit()
        
        row = result.fetchone()
        incident_id = row[0]
        created_at = row[1]
        
        logging.info(f"🚨 Incidente creado: ID={incident_id}, Tipo={incident_type}, Severidad={severity}")
        
        return {
            "id": incident_id,
            "delivery_request_id": delivery_request_id,
            "vehicle_id": vehicle_id,
            "driver_id": driver_id,
            "severity": severity,
            "type": incident_type,
            "description": description,
            "created_at": created_at.isoformat() if created_at else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.error(f"❌ Error al crear incidente: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al crear incidente: {str(e)}")


@app.get("/api/delivery-requests")
@app.get("/maps/delivery_requests")
async def get_delivery_requests(db: Session = Depends(get_db)):
    """
    Obtiene lista de solicitudes de entrega (cargamentos) para selección en formularios
    """
    try:
        from sqlalchemy import text
        
        query = text("""
            SELECT 
                id,
                origin_address,
                destination_address,
                driver_id,
                vehicle_id,
                status,
                distance_m,
                duration_s,
                created_at
            FROM delivery_requests
            ORDER BY created_at DESC
            LIMIT 100
        """)
        
        result = db.execute(query)
        requests = []
        
        for row in result:
            requests.append({
                "id": row[0],
                "origin": {"address": row[1]} if row[1] else None,
                "destination": {"address": row[2]} if row[2] else None,
                "driver_id": row[3],
                "vehicle_id": row[4],
                "status": row[5] or "pending",
                "eta": row[6],  # distance_m como aproximación de ETA
                "created_at": row[8].isoformat() if row[8] else None
            })
        
        logging.info(f"📦 Delivery requests encontrados: {len(requests)}")
        return requests
    
    except Exception as e:
        logging.error(f"❌ Error al obtener delivery requests: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error al obtener delivery requests: {str(e)}")


# ------------------------------------------------------
# IMPORTACIÓN DE RUTAS ADICIONALES (HU11, HU12, ETC.)
# ------------------------------------------------------

# Incluir router de entregas (Trazabilidad) - DEBE SER PRIMERO
logging.info("Incluyendo delivery_router...")
app.include_router(delivery_router)
logging.info("✅ Módulo de entregas (Trazabilidad/UTF-8) cargado correctamente.")

# Incluir router de cámaras (HU6)
logging.info("Incluyendo camaras_router...")
app.include_router(camaras_router, prefix="/api", tags=["camaras"])
logging.info("✅ Módulo de cámaras (HU6) cargado correctamente.")

try:
    from . import reportes  # HU11 y HU12
    app.include_router(reportes.router)
    logging.info("✅ Módulo de reportes (HU11/HU12) cargado correctamente.")
except ImportError as e:
    logging.warning(f"No se pudo importar el módulo de reportes: {e}")
