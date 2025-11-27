-- 005_rrhh_schema.sql
-- -*- coding: utf-8 -*-
-- Esquema inicial para modulo RR.HH. (employees, shifts, shift_assignments, trainings)
-- Encoding: UTF8

SET client_encoding = 'UTF8';

BEGIN;

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    descripcion TEXT,
    is_dynamic_shifts BOOLEAN DEFAULT FALSE,
    requires_pairing BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contract_types (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    descripcion TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shift_profiles (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,
    role_id INTEGER REFERENCES roles(id),
    descripcion TEXT,
    is_flexible BOOLEAN DEFAULT FALSE,
    auto_assign BOOLEAN DEFAULT TRUE,
    min_coverage INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    rut VARCHAR(32),
    nombre VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    password VARCHAR(255),
    activo BOOLEAN DEFAULT TRUE,
    role_id INTEGER REFERENCES roles(id),
    contract_type_id INTEGER REFERENCES contract_types(id),
    shift_profile_id INTEGER REFERENCES shift_profiles(id),
    vehicle_id INTEGER,
    paired_employee_id INTEGER REFERENCES employees(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shifts (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(128) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    timezone VARCHAR(64) DEFAULT 'America/Santiago' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shift_assignments (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    shift_id INTEGER NOT NULL REFERENCES shifts(id) ON DELETE RESTRICT,
    date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE (employee_id, shift_id, date)
);

-- Optional trainings tables placeholder (used by HU10 later)
CREATE TABLE IF NOT EXISTS trainings (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    topic VARCHAR(255),
    required BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_trainings (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    training_id INTEGER NOT NULL REFERENCES trainings(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    instructor VARCHAR(255),
    status VARCHAR(32) DEFAULT 'COMPLETED',
    certificate_url TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Dynamic shifts tables
CREATE TABLE IF NOT EXISTS dynamic_shifts (
    id SERIAL PRIMARY KEY,
    route_id INTEGER,
    fecha_programada DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    duracion_minutos INTEGER NOT NULL,
    conduccion_continua_minutos INTEGER DEFAULT 300,
    status VARCHAR(50) DEFAULT 'pendiente',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    assigned_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS dynamic_shift_assignments (
    id SERIAL PRIMARY KEY,
    dynamic_shift_id INTEGER NOT NULL REFERENCES dynamic_shifts(id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    role_in_shift VARCHAR(50) NOT NULL,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'asignado',
    UNIQUE (dynamic_shift_id, employee_id, role_in_shift)
);

CREATE TABLE IF NOT EXISTS driving_logs (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    dynamic_shift_id INTEGER NOT NULL REFERENCES dynamic_shifts(id) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    minutos_conduccion INTEGER NOT NULL,
    minutos_descanso INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS ix_employees_role_id ON employees(role_id);
CREATE INDEX IF NOT EXISTS ix_employees_contract_type_id ON employees(contract_type_id);
CREATE INDEX IF NOT EXISTS ix_employees_activo ON employees(activo);
CREATE INDEX IF NOT EXISTS ix_shift_assignments_employee_id ON shift_assignments(employee_id);
CREATE INDEX IF NOT EXISTS ix_shift_assignments_shift_id ON shift_assignments(shift_id);
CREATE INDEX IF NOT EXISTS ix_shift_assignments_date ON shift_assignments(date);
CREATE INDEX IF NOT EXISTS ix_employee_trainings_employee_id ON employee_trainings(employee_id);
CREATE INDEX IF NOT EXISTS ix_employee_trainings_training_id ON employee_trainings(training_id);

COMMIT;
