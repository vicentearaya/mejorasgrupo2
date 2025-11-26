from sqlalchemy import Column, Integer, String, Boolean, Date, TIMESTAMP, ForeignKey, Text, UniqueConstraint, Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

class Employee(Base):
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True, index=True)
    rut = Column(String(32), nullable=True)
    nombre = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True) # Hashed password
    activo = Column(Boolean, default=True)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=True)
    contract_type_id = Column(Integer, ForeignKey('contract_types.id'), nullable=True)
    shift_profile_id = Column(Integer, ForeignKey('shift_profiles.id'), nullable=True)
    vehicle_id = Column(Integer, nullable=True)
    paired_employee_id = Column(Integer, ForeignKey('employees.id'), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Shift(Base):
    __tablename__ = 'shifts'
    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(128), nullable=False)  # 'Mañana', 'Tarde', 'Noche'
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    timezone = Column(String(64), default='America/Santiago', nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class ShiftAssignment(Base):
    __tablename__ = 'shift_assignments'
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id', ondelete='CASCADE'), nullable=False)
    shift_id = Column(Integer, ForeignKey('shifts.id', ondelete='RESTRICT'), nullable=False)
    date = Column(Date, nullable=False)
    notes = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint('employee_id', 'shift_id', 'date', name='u_employee_shift_date'),)

class Training(Base):
    __tablename__ = 'trainings'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    topic = Column(String(255), nullable=True)
    required = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class EmployeeTraining(Base):
    __tablename__ = 'employee_trainings'
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id', ondelete='CASCADE'), nullable=False)
    training_id = Column(Integer, ForeignKey('trainings.id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)
    instructor = Column(String(255), nullable=True)
    status = Column(String(32), default='COMPLETED')
    certificate_url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

# ============================================
# ROLES AND CONTRACT TYPES
# ============================================
class Role(Base):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)
    descripcion = Column(Text, nullable=True)
    is_dynamic_shifts = Column(Boolean, default=False)
    requires_pairing = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class ContractType(Base):
    __tablename__ = 'contract_types'
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)
    descripcion = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class ShiftProfile(Base):
    __tablename__ = 'shift_profiles'
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=True)
    descripcion = Column(Text, nullable=True)
    is_flexible = Column(Boolean, default=False)
    auto_assign = Column(Boolean, default=True)
    min_coverage = Column(Integer, default=1)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

# ============================================
# DYNAMIC SHIFTS
# ============================================
class DynamicShift(Base):
    __tablename__ = 'dynamic_shifts'
    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, nullable=True)  # Referencia a routes en ms-logistica
    fecha_programada = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    duracion_minutos = Column(Integer, nullable=False)
    conduccion_continua_minutos = Column(Integer, default=300)  # 5 horas
    status = Column(String(50), default='pendiente')  # pendiente, asignado, en_curso, completado, cancelado
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    assigned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

class DynamicShiftAssignment(Base):
    __tablename__ = 'dynamic_shift_assignments'
    id = Column(Integer, primary_key=True, index=True)
    dynamic_shift_id = Column(Integer, ForeignKey('dynamic_shifts.id', ondelete='CASCADE'), nullable=False)
    employee_id = Column(Integer, ForeignKey('employees.id', ondelete='CASCADE'), nullable=False)
    role_in_shift = Column(String(50), nullable=False)  # 'conductor', 'asistente', 'custodia'
    assigned_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    status = Column(String(50), default='asignado')  # asignado, en_curso, completado, cancelado
    __table_args__ = (UniqueConstraint('dynamic_shift_id', 'employee_id', 'role_in_shift', name='u_dynamic_shift_emp_role'),)

class DrivingLog(Base):
    __tablename__ = 'driving_logs'
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey('employees.id', ondelete='CASCADE'), nullable=False)
    dynamic_shift_id = Column(Integer, ForeignKey('dynamic_shifts.id', ondelete='CASCADE'), nullable=False)
    fecha = Column(Date, nullable=False)
    minutos_conduccion = Column(Integer, nullable=False)
    minutos_descanso = Column(Integer, default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class DeliveryAlert(Base):
    __tablename__ = 'delivery_alerts'
    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(Integer, nullable=True)
    alert_type = Column(String(50), nullable=False)
    alert_level = Column(String(20), default='info')
    message = Column(Text, nullable=False)
    recipient_type = Column(String(50), nullable=False) # 'rrhh_manager', 'conductor'
    recipient_id = Column(Integer, nullable=True)
    is_sent = Column(Boolean, default=False)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    read_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
