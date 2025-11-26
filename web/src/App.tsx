import React from 'react';
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import MapView from './MapView';
import ErrorBoundary from './ErrorBoundary';
import InventoryPage from './pages/InventoryPage';
import AlertsPage from './pages/AlertsPage';
import SecurityPage from './pages/SecurityPage';
import IncidentsPage from './pages/IncidentsPage';
import MaintenancePage from './pages/MaintenancePage';
import CalendarViewPage from './pages/RRHHModule/CalendarViewPage';
import ConductorsSchedulePage from './pages/RRHHModule/ConductorsSchedulePage';
import TrainingsPage from './pages/RRHHModule/TrainingsPage';
import EmployeesPage from './pages/RRHHModule/EmployeesPage';
import CamarasPage from './pages/CamarasPage';
import LoginPage from './pages/LoginPage';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider, useAuth } from './context/AuthContext';
import './app.css';

function AppContent() {
  const { isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h2>LuxChile</h2>
        <nav>
          <ul>
            <li><NavLink to="/" end>Rutas</NavLink></li>
            <li><NavLink to="/inventario">Inventario</NavLink></li>
            <li><NavLink to="/camaras">Cámaras</NavLink></li>
            <li><NavLink to="/alertas">Alertas</NavLink></li>
            <li><NavLink to="/seguridad">Seguridad</NavLink></li>
            <li><NavLink to="/incidentes">Incidentes</NavLink></li>
            <li><NavLink to="/mantencion">Mantención</NavLink></li>
            <li><strong>RR.HH.</strong>
              <ul style={{ paddingLeft: '1rem', marginTop: '0.5rem' }}>
                <li><NavLink to="/empleados">Empleados</NavLink></li>
                <li><NavLink to="/conductores">Turnos Conductores</NavLink></li>
                <li><NavLink to="/calendario">Calendario de Turnos</NavLink></li>
                <li><NavLink to="/capacitaciones">Capacitaciones</NavLink></li>
              </ul>
            </li>
          </ul>
        </nav>
        <div style={{ marginTop: 'auto', padding: '1rem' }}>
          <button
            onClick={handleLogout}
            style={{
              width: '100%',
              padding: '0.5rem',
              backgroundColor: '#dc2626',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            Cerrar Sesión
          </button>
        </div>
        <p className="small">Demo: ruteo + inventario + alertas + RR.HH.</p>
      </aside>
      <main className="main">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<ProtectedRoute><MapView /></ProtectedRoute>} />
            <Route path="/inventario" element={<ProtectedRoute><InventoryPage /></ProtectedRoute>} />
            <Route path="/camaras" element={<ProtectedRoute><CamarasPage /></ProtectedRoute>} />
            <Route path="/alertas" element={<ProtectedRoute><AlertsPage /></ProtectedRoute>} />
            <Route path="/seguridad" element={<ProtectedRoute><SecurityPage /></ProtectedRoute>} />
            <Route path="/incidentes" element={<ProtectedRoute><IncidentsPage /></ProtectedRoute>} />
            <Route path="/mantencion" element={<ProtectedRoute><MaintenancePage /></ProtectedRoute>} />
            <Route path="/calendario" element={<ProtectedRoute><CalendarViewPage /></ProtectedRoute>} />
            <Route path="/conductores" element={<ProtectedRoute><ConductorsSchedulePage /></ProtectedRoute>} />
            <Route path="/capacitaciones" element={<ProtectedRoute><TrainingsPage /></ProtectedRoute>} />
            <Route path="/empleados" element={<ProtectedRoute><EmployeesPage /></ProtectedRoute>} />
            <Route path="*" element={<ProtectedRoute><MapView /></ProtectedRoute>} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
