-- 006_rrhh_seed.sql
-- -*- coding: utf-8 -*-
-- Seed data for RRHH module: predefined shifts for a logistics company
-- A logistics company works 24/7 with 3 standard shifts
-- Encoding: UTF8

SET client_encoding = 'UTF8';

BEGIN;

-- Insert predefined shifts (these are fixed and should not be user-created)
INSERT INTO shifts (tipo, start_time, end_time, timezone) VALUES
('Mañana', '06:00:00', '14:00:00', 'America/Santiago'),
('Tarde', '14:00:00', '22:00:00', 'America/Santiago'),
('Noche', '22:00:00', '06:00:00', 'America/Santiago')
ON CONFLICT DO NOTHING;

-- Optional: Create a test employee
INSERT INTO employees (rut, nombre, email, password, activo) VALUES
('12345678-9', 'Juan Pérez', 'juan.perez@logistica.cl', '$2b$12$TAkciKam6b86ACnjHi9JhOgse/HUmIIaRE4MGP2piU69PtG.9tLuS', TRUE),
('98765432-1', 'María García', 'maria.garcia@logistica.cl', '$2b$12$TAkciKam6b86ACnjHi9JhOgse/HUmIIaRE4MGP2piU69PtG.9tLuS', TRUE),
('55555555-5', 'Carlos López', 'carlos.lopez@logistica.cl', '$2b$12$TAkciKam6b86ACnjHi9JhOgse/HUmIIaRE4MGP2piU69PtG.9tLuS', TRUE)
ON CONFLICT DO NOTHING;

COMMIT;
