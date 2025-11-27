# LuxChile ERP — Gestión de Inventario (MVP)

Sistema modular orientado a microservicios para la gestión de inventario, logística y visualización web. Stack principal (MVP):

- Backend: FastAPI (Python), SQLAlchemy, Alembic (migraciones), patrones BFF/Gateway.
- Frontend: React + Vite + TypeScript (Google Maps SDK / Autocomplete / Rutas).
- Infraestructura: Docker Compose (Postgres).
- Observabilidad: /health y (en progreso) /metrics, futura trazabilidad.
  

> Este README se centra en levantar y entender el estado actual. Para una visión conceptual adicional revisar `ARCHITECTURE.md`.

---
## ⚡ Deploy & Verification (IS1-105)

**✅ Status**: Ready for Production  
**Branch**: `IS1-105-Fix-HU4-Visualizar-ruta-asignada`

Sistema de Trazabilidad de Entregas **fully operational** con UTF-8, PL/pgSQL functions, y endpoints end-to-end.

**Quick validation** (5 min):
```powershell
cd C:\Users\david\Desktop\Ingenieria-Software-1
docker-compose -f infra/docker-compose.yaml up -d --build
Start-Sleep -Seconds 5
curl http://localhost:8000/deliveries  # Should return 200 + UTF-8 names
```

**Full guide**: See [`DEPLOY.md`](DEPLOY.md)  
**Changes & Acceptance Criteria**: See [`JIRA_CHANGELOG.md`](JIRA_CHANGELOG.md)

---
## 🚀 Quick Start (Desarrollo)

1. Clonar y situarse en la raíz del repositorio.
2. Crear variables de entorno base:
	```powershell
	Copy-Item .env.sample .env
	Copy-Item web/.env.example web/.env
	# Completa claves: VITE_GOOGLE_MAPS_API_KEY, credenciales opcionales
	```
3. Levantar infraestructura esencial (desde la carpeta `infra`):
	```powershell
	cd infra
	docker compose up -d postgres
	```
4. Construir y levantar servicios de aplicación:
	```powershell
	docker compose up -d --build gateway ms-inventario ms-logistica web
	```
5. Verificar endpoints:
	- Frontend: http://localhost:5173
	- Gateway: http://localhost:8000/health
	- Inventario: http://localhost:8002/health
	- Logística: http://localhost:8001/health
    

Para reconstruir después de cambios en código backend/frontend: `docker compose up -d --build <servicio>`.

Notas BD:
- Los scripts de `infra/sql` se ejecutan automáticamente la primera vez que se crea el volumen de Postgres (montados en `/docker-entrypoint-initdb.d`).
- Si necesitas reinicializar la base desde cero para re-ejecutar los `.sql`: `docker compose down -v` y luego `docker compose up -d postgres`.

---
## 🧱 Microservicios Principales

| Servicio | Puerto | Descripción | Estado |
|----------|--------|-------------|--------|
| gateway | 8000 | BFF/API Gateway (Auth, agregación) | Skeleton funcional |
| ms-inventario | 8002 (interno 8000) | Catálogo productos, stock, alertas | MVP estable |
| ms-logistica | 8001 (interno 8000) | Optimización rutas / geocoding | MVP inicial |
| web | 5173 (Docker 80→5173) | UI React (Inventario + Map) | MVP |
| postgres | 5432 | Base de datos principal | En uso |


Servicios placeholder listados en `docker-compose` (ms-seguridad, ms-activos, ms-rrhh, ms-reportes) aún no tienen código integrado. Para el MVP no se incluyen servicios de mensajería ni stack de observabilidad avanzada (Kafka, RabbitMQ, Prometheus, Grafana, Loki) ni reverse proxy (Traefik).

---
## 📦 Estructura de carpetas relevante

```
infra/                # Docker compose + SQL init
gateway/              # API Gateway / BFF (FastAPI + Alembic)
ms-inventario/        # Servicio inventario completo (routers, modelos, CRUD)
ms-logistica/         # Servicio logística (optimizador, rutas)
web/                  # Frontend React + Vite
scripts/              # Scripts utilitarios (smoke tests, payloads)
ARCHITECTURE.md       # Documento arquitectónico alto nivel
requirements.txt      # Requerimientos raíz (si aplica consolidación)
```

---
## 🔌 Endpoints (Inventario)

Base URL (local): `http://localhost:8002`

| Método | Path | Descripción |
|--------|------|-------------|
| GET | /health | Healthcheck |
| GET | /productos | Lista productos (SKU, nombre) |
| GET | /inventory/{bodega_id} | Stock de una bodega (enriquecido si hay join) |
| GET | /alerts | Alertas de stock no leídas |
| PATCH | /alerts/{id}/ack | Marcar alerta como atendida |

La agregación futura vía `gateway` permitirá ofrecer subset público: `/api/inventario/*`.

---
## 🗄️ Base de Datos

- Imagen Postgres 15.
- Usuario/DB por defecto definidos en `docker-compose.yaml` (`lux / luxpass / erp`).
- Scripts iniciales en `infra/sql/` (por ejemplo `001_init_schema.sql`).
- Migraciones: Gateway y ms-logistica incluyen estructura Alembic; ms-inventario puede incorporar migraciones en iteraciones siguientes.

Para inspeccionar DB: opcionalmente levantar `pgadmin` (puerto 5050) y conectar con credenciales.

---
## 🌐 Frontend

- Vite + React + TypeScript.
- Variables `.env` (en `web/.env`):
  - `VITE_API_URL` (Gateway)
	- `VITE_API_LOGISTICA` (Logística directo)
  - `VITE_API_INVENTARIO` (Inventario directo)
  - `VITE_GOOGLE_MAPS_API_KEY`
- Componentes clave: `MapView`, `InventoryPage`, `AlertsPage`, `PlaceAutocomplete`.

Build (opcional fuera de Docker):
```powershell
cd web
npm install
npm run dev
```

---
## 🔐 Seguridad (Roadmap)

- OAuth2 + JWT (access/refresh) – skeleton en Gateway.
- TOTP (2FA) con `pyotp` planificado.
- RBAC / Roles y permisos (pendiente implementación persistente).

---
## 📊 Observabilidad (Roadmap)

Se puede añadir instrumentación `/metrics` en iteraciones siguientes si se requiere.

---
## 🧪 Testing

### Pruebas Unitarias (Backend)

Para ejecutar las pruebas unitarias de los microservicios, utiliza los siguientes comandos (asegúrate de que los contenedores estén corriendo):

**1. Login (ms-rrhh)**
```powershell
docker exec infra-ms-rrhh-1 python -m unittest tests/test_login_unittest.py
```

**2. Ajustes de Stock (ms-inventario)**
```powershell
docker exec infra-ms-inventario-1 python -m unittest tests/test_stock_adjustments.py
```

**3. Alertas (ms-inventario)**
```powershell
docker exec infra-ms-inventario-1 python -m unittest tests/test_alerts.py
```

---
## 🧪 Smoke Test rápido

```powershell
python scripts/smoke_test.py
```
Configura previamente variables necesarias (.env y servicios arriba).

---
## 🛠 Troubleshooting

| Problema | Causa probable | Solución |
|----------|----------------|----------|
| Gateway 502 / Bad Gateway | Servicio backend aún construyendo | `docker compose logs -f gateway` y reintentar |
| Frontend no carga mapas | Falta `VITE_GOOGLE_MAPS_API_KEY` | Añadir clave válida en `web/.env` |
| DB connection refused | Postgres no listo | `docker compose logs -f postgres` esperar/ reiniciar |
|  |  |  |

Logs de un servicio específico:
```powershell
docker compose logs -f ms-inventario
```

---
## 🗺 Roadmap sugerido

1. Migraciones unificadas (Alembic) para inventario.
2. Instrumentación `/metrics` (opcional) y observabilidad básica.
3. Autenticación completa + RBAC + refresh tokens.
4. Eventos de stock y colas (mensajería) si el alcance lo requiere.
5. Optimización avanzada rutas (matriz distancias + heurísticas).
6. Integración CI (lint, tests, build) y CD.
7. Hardening seguridad (headers, rate limiting, audit log).

---
## 📄 Licencia / Créditos

Proyecto interno educativo / PoC. Ajustar licencia según necesidad antes de hacer público.

---
## ✅ Estado resumen

| Área | Estado |
|------|--------|
| Inventario básico | OK |
| Alertas stock | OK (ack manual) |
| Logística rutas | MVP inicial |
| Gateway Auth | Skeleton |
| Frontend UI | MVP |
| Observabilidad | Parcial |
| Seguridad avanzada | Pendiente |
| Mensajería | No incluida en MVP |

---
Si necesitas una versión reducida para una demo rápida, puedes eliminar servicios placeholder y reconstruir el compose antes de subir a producción.
