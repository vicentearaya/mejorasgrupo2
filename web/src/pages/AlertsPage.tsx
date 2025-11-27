import { useEffect, useState } from 'react';
import { getAlerts, ackAlert } from '../api/inventario';
import styles from './AlertsPage.module.css';

export interface AlertItem {
  id: number;
  producto_id: number;
  bodega_id: number;
  tipo: string;
  mensaje: string;
  leida: boolean;
  created_at?: string;
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [soloNoLeidas, setSoloNoLeidas] = useState(true);
  const [filtroTipo, setFiltroTipo] = useState<string>('');

  // Email Modal State
  const [selectedAlert, setSelectedAlert] = useState<AlertItem | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const raw = await getAlerts();
      const list: AlertItem[] = (raw && (raw.value ?? raw)) || [];
      setAlerts(list);
    } catch (e: any) {
      setError(e.message ?? 'Error cargando alertas');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);

  const filtered = alerts.filter(a => {
    if (soloNoLeidas && a.leida) return false;
    if (filtroTipo && a.tipo !== filtroTipo) return false;
    return true;
  });

  const tipos = Array.from(new Set(alerts.map(a => a.tipo))).sort();

  const ackOne = async (id: number) => {
    await ackAlert(id); await load();
  };

  const handleEmailClick = (alert: AlertItem) => {
    setSelectedAlert(alert);
    setIsModalOpen(true);
  };

  const handleSendEmail = () => {
    // Simulación de envío
    alert(`✅ Correo enviado exitosamente a admin@luxlogistics.cl\n\nAsunto: Alerta ${selectedAlert?.tipo}\nID: ${selectedAlert?.id}`);
    setIsModalOpen(false);
    setSelectedAlert(null);
  };

  const getBadgeClass = (tipo: string) => {
    if (tipo === 'CRITICO') return styles.badgeCrit;
    if (tipo === 'BAJO_STOCK' || tipo === 'LOW_STOCK') return styles.badgeWarn;
    return styles.badgeInfo;
  };

  return (
    <div className={styles.root}>
      <div className={styles.headerContainer}>
        <h2 className={styles.title}>Panel de Alertas</h2>
        <button className={styles.refreshBtn} onClick={load} disabled={loading}>
          {loading ? 'Actualizando...' : 'Refrescar Datos'}
        </button>
      </div>

      <div className={styles.filters}>
        <label className={styles.filterLabel}>
          <input
            type="checkbox"
            checked={soloNoLeidas}
            onChange={e => setSoloNoLeidas(e.target.checked)}
            style={{ width: '16px', height: '16px' }}
          />
          Ocultar leídas
        </label>

        <div className={styles.filterLabel}>
          <span>Filtrar por tipo:</span>
          <select
            className={styles.select}
            value={filtroTipo}
            onChange={e => setFiltroTipo(e.target.value)}
          >
            <option value="">Todos</option>
            {tipos.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.listContainer}>
        <table className={styles.table}>
          <thead className={styles.thead}>
            <tr>
              <th className={styles.th}>ID</th>
              <th className={styles.th}>Estado</th>
              <th className={styles.th}>Tipo</th>
              <th className={styles.th}>Mensaje</th>
              <th className={styles.th}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(a => (
              <tr key={a.id} className={styles.row}>
                <td className={styles.td}>#{a.id}</td>
                <td className={styles.td}>
                  {a.leida ? (
                    <span className={styles.statusRead}>Leída</span>
                  ) : (
                    <span className={styles.statusUnread}>Activa</span>
                  )}
                </td>
                <td className={styles.td}>
                  <span className={`${styles.badge} ${getBadgeClass(a.tipo)}`}>
                    {a.tipo}
                  </span>
                </td>
                <td className={styles.td}>{a.mensaje}</td>
                <td className={styles.td}>
                  <div className={styles.actions}>
                    {!a.leida && (
                      <button
                        className={`${styles.actionBtn} ${styles.ackBtn}`}
                        onClick={() => ackOne(a.id)}
                        title="Marcar como leída"
                      >
                        ✓ ACK
                      </button>
                    )}
                    <button
                      className={`${styles.actionBtn} ${styles.emailBtn}`}
                      onClick={() => handleEmailClick(a)}
                      title="Enviar por correo"
                    >
                      ✉ Enviar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && !loading && (
              <tr>
                <td colSpan={5} className={styles.empty}>
                  No hay alertas que coincidan con los filtros
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Email Modal */}
      {isModalOpen && selectedAlert && (
        <div className={styles.modalOverlay} onClick={() => setIsModalOpen(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3 className={styles.modalTitle}>Enviar Reporte por Correo</h3>
            </div>
            <div className={styles.modalBody}>
              <div className={styles.emailPreview}>
                <span className={styles.emailField}>
                  <span className={styles.emailLabel}>Para:</span>
                  admin@luxlogistics.cl
                </span>
                <span className={styles.emailField}>
                  <span className={styles.emailLabel}>Asunto:</span>
                  [ALERTA] {selectedAlert.tipo} - ID #{selectedAlert.id}
                </span>
                <hr style={{ margin: '12px 0', borderColor: '#e2e8f0', opacity: 0.5 }} />
                <p style={{ margin: 0, lineHeight: '1.5' }}>
                  Estimado Administrador,
                  <br /><br />
                  Se ha detectado la siguiente incidencia en el inventario:
                  <br />
                  <strong>{selectedAlert.mensaje}</strong>
                  <br /><br />
                  Por favor tomar las acciones correctivas necesarias.
                  <br /><br />
                  Saludos,<br />
                  Sistema ERP LuxChile
                </p>
              </div>
              <p style={{ fontSize: '0.875rem', color: '#64748b', fontStyle: 'italic' }}>
                ℹ️ Este es un entorno de desarrollo. Al enviar, se simulará el despacho del correo.
              </p>
            </div>
            <div className={styles.modalFooter}>
              <button className={styles.cancelBtn} onClick={() => setIsModalOpen(false)}>
                Cancelar
              </button>
              <button className={styles.sendBtn} onClick={handleSendEmail}>
                <span>✈️</span> Enviar Correo
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
