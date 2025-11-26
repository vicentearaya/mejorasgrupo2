from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .routers import employees, shifts, assignments, trainings, employee_trainings, dynamic_shifts, auth
from .alert_service import router as alert_router

app = FastAPI(title='ms-rrhh')

# CORS configuration - allow all for development
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

# Include routers
app.include_router(auth.router)
app.include_router(employees.router, prefix='/employees', tags=['employees'])
app.include_router(shifts.router, prefix='/shifts', tags=['shifts'])
app.include_router(assignments.router, prefix='/assignments', tags=['assignments'])
app.include_router(dynamic_shifts.router, prefix='/dynamic-shifts', tags=['dynamic-shifts'])
app.include_router(trainings.router, prefix='/trainings', tags=['trainings'])
app.include_router(employee_trainings.router, tags=['employee-trainings'])
app.include_router(alert_router, tags=['delivery-alerts'])


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/')
def root():
    return {
        'service': 'ms-rrhh',
        'status': 'ok',
        'features': [
            'Gestión de Empleados (UTF-8)',
            'Turnos y Asignaciones',
            'Capacitaciones',
            'Alertas de Entregas en Tiempo Real',
            'Notificaciones a Conductores'
        ],
        'endpoints': [
            '/health',
            '/employees',
            '/shifts',
            '/assignments',
            '/dynamic-shifts',
            '/trainings',
            '/api/alerts (alertas de entregas)',
            '/api/alerts/conductor/{id} (alertas del conductor)',
            '/api/alerts/{id}/read (marcar como leída)',
            '/api/alerts/send (recibir evento)',
            '/api/alerts/stats (estadísticas)'
        ]
    }
