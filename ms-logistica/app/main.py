from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from .routes import router as maps_router
from .routes import router as routes_router
from .delivery_service import router as delivery_router
import structlog  # type: ignore[reportMissingImports]
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST  # type: ignore[reportMissingImports]
from fastapi.responses import Response
from .logging_config import configure_logging
from .db import engine
from .models import Base

configure_logging()

log = structlog.get_logger()

app = FastAPI(title="ms-logistica")
app.include_router(maps_router, prefix="/maps", tags=["maps"])
app.include_router(routes_router, prefix="/routes", tags=["routes"])
app.include_router(delivery_router, tags=["deliveries"])

# For dev/MVP, ensure tables exist
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logging.error(f"Error creating tables: {e}")
    # best-effort; log will be handled by global exception handler if needed
    pass

# CORS for local development (all localhost ports)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Middleware para garantizar UTF-8 en todas las respuestas
class UTF8Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Asegurar que todas las respuestas JSON tengan charset=utf-8
        if response.headers.get('content-type', '').startswith('application/json'):
            response.headers['content-type'] = 'application/json; charset=utf-8'
        return response

app.add_middleware(UTF8Middleware)


# Global exception handler for dev visibility
from fastapi.responses import JSONResponse
import traceback, os, logging


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    tb = traceback.format_exc()
    logging.error("Unhandled exception in ms-logistica: %s", str(exc))
    logging.error(tb)
    show_trace = os.environ.get("DEV", "1") == "1"
    return JSONResponse(status_code=500, content={"detail": "internal_server_error", "error": str(exc), "trace": tb if show_trace else None})

# Prometheus metrics
REQUESTS = Counter("ms_logistica_requests_total", "Total HTTP requests")


@app.get("/health")
async def health():
    REQUESTS.inc()
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    """Root endpoint - useful for browsers hitting the service."""
    return {
        "service": "ms-logistica",
        "version": "2.0.0-integration",
        "status": "running",
        "features": [
            "Google Places Autocomplete Optimizado",
            "Geocoding Multi-estrategia",
            "Gestión de Vehículos",
            "Asignación de Rutas",
            "Integración RRHH",
            "Sistema de Incidentes",
            "Trazabilidad de Entregas (UTF-8)"
        ],
        "endpoints": [
            "/health",
            "/metrics",
            "/maps/geocode",
            "/maps/place-details",
            "/maps/nearby_search",
            "/maps/search_combined",
            "/maps/directions",
            "/maps/delivery_requests",
            "/maps/incidents",
            "/maps/vehicles",
            "/maps/route_assignments",
            "/api/deliveries (GET/POST - CRUD entregas)",
            "/api/deliveries/{id} (GET - detalles)",
            "/api/deliveries/{id}/tracking (GET - GPS en tiempo real)",
            "/api/deliveries/{id}/events (GET - historial de eventos)",
            "/api/deliveries/{id}/audit (GET - auditoría legal)",
            "/api/deliveries/{id}/alerts (GET - alertas)",
            "/api/deliveries/{id}/assign (PUT - asignar conductor)",
            "/api/deliveries/{id}/status (PUT - cambiar estado)"
        ]
    }


@app.get("/favicon.ico")
async def favicon():
    # Return empty 204 to avoid noisy 404s from browsers
    return Response(status_code=204)
