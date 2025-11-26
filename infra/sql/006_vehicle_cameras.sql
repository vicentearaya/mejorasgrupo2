-- ======================================================
-- SISTEMA DE ASIGNACIÓN DE CÁMARAS A VEHÍCULOS
-- HU6 - Subtarea IS1-86: Modificar base de datos para agregar el camión
-- ======================================================

BEGIN;

-- Tabla de relación vehículo-cámara
CREATE TABLE IF NOT EXISTS vehicle_cameras (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    camera_id VARCHAR(50) NOT NULL,
    camera_name VARCHAR(100),
    position VARCHAR(50) CHECK (position IN ('frontal', 'trasera', 'interior', 'lateral_izquierda', 'lateral_derecha')),
    stream_url TEXT,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(vehicle_id, camera_id)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_vehicle_cameras_vehicle ON vehicle_cameras(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_cameras_camera ON vehicle_cameras(camera_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_cameras_active ON vehicle_cameras(active);

-- Trigger para updated_at
CREATE OR REPLACE FUNCTION update_vehicle_cameras_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_vehicle_cameras_updated_at ON vehicle_cameras;

CREATE TRIGGER trigger_vehicle_cameras_updated_at
    BEFORE UPDATE ON vehicle_cameras
    FOR EACH ROW
    EXECUTE FUNCTION update_vehicle_cameras_timestamp();

-- ======================================================
-- DATOS DE EJEMPLO PARA DEMOSTRACIÓN
-- En producción, las cámaras se asignan dinámicamente
-- usando el endpoint POST /api/camaras/vehicle/{id}/camera
-- ======================================================

-- Asegurar que existen los vehículos para la demo
INSERT INTO vehicles (id, code, capacity_kg, status, active)
VALUES 
    (1, 'VAN-001', 800, 'active', true),
    (2, 'VAN-002', 800, 'active', true)
ON CONFLICT (id) DO NOTHING;

-- Asignar cam1 y cam2 a VAN-001 (vehículo ID 1)
INSERT INTO vehicle_cameras (vehicle_id, camera_id, camera_name, position, stream_url, active)
VALUES 
    (1, 'cam1', 'Cámara Frontal VAN-001', 'frontal', 'http://localhost:8888/cam1/index.m3u8', true),
    (1, 'cam2', 'Cámara Trasera VAN-001', 'trasera', 'http://localhost:8888/cam2/index.m3u8', true)
ON CONFLICT (vehicle_id, camera_id) DO NOTHING;

-- Asignar cam1 a VAN-002 (vehículo ID 2)
INSERT INTO vehicle_cameras (vehicle_id, camera_id, camera_name, position, stream_url, active)
VALUES 
    (2, 'cam1', 'Cámara Frontal VAN-002', 'frontal', 'http://localhost:8888/cam1/index.m3u8', true)
ON CONFLICT (vehicle_id, camera_id) DO NOTHING;

COMMIT;
