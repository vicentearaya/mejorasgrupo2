import { useEffect, useMemo, useState, ChangeEvent } from 'react';
import { getInventarioPorBodega, getAlerts, postMovement, StockItem } from '../api/inventario';
import styles from './InventoryPage.module.css';

const BODEGAS = [
  { id: 1, nombre: 'Bodega Central' },
  { id: 2, nombre: 'Bodega Norte' },
];

export default function InventoryPage() {
  const [bodegaId, setBodegaId] = useState<number>(1);
  const [items, setItems] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [alertCount, setAlertCount] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const loadData = async (id: number) => {
    setLoading(true); setError(null);
    try {
      const [inv, alerts] = await Promise.all([
        getInventarioPorBodega(id),
        getAlerts()
      ]);
      setItems(inv ?? []);
      const list = (alerts && (alerts.value ?? alerts)) || [];
      setAlertCount(list.length);
    } catch (e: any) {
      setError(e.message ?? 'Error cargando datos');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(bodegaId);
    const t = setInterval(() => loadData(bodegaId), 15000);
    return () => clearInterval(t);
  }, [bodegaId]);

  const totalSKUs = useMemo(() => items.length, [items]);

  const onChangeBodega = (e: ChangeEvent<HTMLSelectElement>) => {
    setBodegaId(Number(e.target.value));
  };

  const handleIncrement = async (productoId: number) => {
    await postMovement(productoId, bodegaId, -1); // Negative for IN
    await loadData(bodegaId);
  };

  const handleDecrement = async (productoId: number) => {
    await postMovement(productoId, bodegaId, 1); // Positive for OUT
    await loadData(bodegaId);
  };

  const getQuantityClass = (cantidad: number) => {
    if (cantidad === 0) return styles.quantityZero;
    if (cantidad <= 5) return styles.quantityLow;
    return styles.quantityNormal;
  };

  return (
    <div className={styles.root}>
      <div className={styles.pageHeader}>
        <h1 className={styles.title}>📦 Gestión de Inventario</h1>
        <p className={styles.subtitle}>Control de stock por bodega en tiempo real</p>
      </div>

      <div className={styles.controlCard}>
        <div className={styles.controlGroup}>
          <label htmlFor="bodegaSel" className={styles.label}>
            <span className={styles.labelIcon}>🏢</span>
            Bodega:
          </label>
          <select id="bodegaSel" value={bodegaId} onChange={onChangeBodega} className={styles.select}>
            {BODEGAS.map(b => <option key={b.id} value={b.id}>{b.nombre}</option>)}
          </select>
        </div>

        <button onClick={() => loadData(bodegaId)} disabled={loading} className={styles.refreshButton}>
          <span className={styles.buttonIcon}>🔄</span>
          {loading ? 'Actualizando...' : 'Actualizar'}
        </button>

        <div className={styles.statsGroup}>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>Total SKUs</span>
            <span className={styles.statValue}>{totalSKUs}</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>Alertas</span>
            <span className={`${styles.statValue} ${styles.badge} ${alertCount > 0 ? styles.badgeAlert : styles.badgeSuccess}`}>
              {alertCount}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div className={styles.errorCard}>
          <span className={styles.errorIcon}>⚠️</span>
          {error}
        </div>
      )}

      <div className={styles.tableCard}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>SKU</th>
              <th>Producto</th>
              <th>Cantidad</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, index) => (
              <tr key={it.producto_id} className={index % 2 === 0 ? styles.rowEven : styles.rowOdd}>
                <td>
                  <span className={styles.skuBadge}>{it.sku ?? '—'}</span>
                </td>
                <td className={styles.productName}>{it.nombre ?? '—'}</td>
                <td>
                  <span className={`${styles.quantityBadge} ${getQuantityClass(it.cantidad)}`}>
                    {it.cantidad}
                  </span>
                </td>
                <td className={styles.actions}>
                  <button
                    onClick={() => handleIncrement(it.producto_id)}
                    disabled={loading}
                    className={styles.incrementButton}
                    title="Agregar 1 unidad"
                  >
                    <span className={styles.buttonIcon}>➕</span>
                    +1
                  </button>
                  <button
                    onClick={() => handleDecrement(it.producto_id)}
                    disabled={loading}
                    className={styles.decrementButton}
                    title="Quitar 1 unidad"
                  >
                    <span className={styles.buttonIcon}>➖</span>
                    -1
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={4} className={styles.empty}>
                  <div className={styles.emptyState}>
                    <span className={styles.emptyIcon}>📭</span>
                    <p>No hay productos en esta bodega</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
