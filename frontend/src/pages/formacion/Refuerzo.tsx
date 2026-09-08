/**
 * Refuerzo.tsx — Refuerzo de Memoria y su KPI (§10 y §11).
 * Shell de tabs: cada rol ve solo los que le corresponden, con los mismos
 * gates que el router backend (`formacion_refuerzo.py`).
 */
import { useMemo, useState } from 'react';
import { Box, Tabs, Tab, Typography, Alert } from '@mui/material';
import { useAuthStore } from '../../store/auth.store';
import MisCapsulas from './refuerzo/MisCapsulas';
import CampanasRefuerzo from './refuerzo/CampanasRefuerzo';
import KpiRefuerzo from './refuerzo/KpiRefuerzo';

// Mismos gates que el router: RequireCapacitacion y el _VEN_TODO del §11.5.
// "Mis cápsulas" va por rol y no por `rm_id` porque el store de auth solo
// guarda el rol; el backend exige el enlace a representante y responde 403 si
// falta, que es la única fuente de verdad de ese dato.
const ROLES_CAPSULAS = ['REPRESENTANTE_MEDICO'];
// GERENTE_MEDICO NO va aquí: en el backend (formacion_refuerzo.py) solo
// POST /rondas/{id}/capsulas lo admite (RequireContenido) — listar_campanas,
// calendario, programar y publicar exigen RequireCapacitacion. Si entrara al
// tab, la lista le daría 403 antes de llegar a lo único que sí puede hacer.
// Hoy GERENTE_MEDICO no tiene camino propio en la UI para aportar cápsulas
// (follow-up pendiente).
const ROLES_CAMPANAS = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION'];
const ROLES_KPI = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'PRESIDENCIA',
  'GERENTE_MEDICO', 'GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'];

export default function Refuerzo() {
  const rol = useAuthStore((s) => s.rol);
  const [tab, setTab] = useState(0);

  const tabs = useMemo(() => {
    const t: { label: string; nodo: JSX.Element }[] = [];
    if (rol && ROLES_CAPSULAS.includes(rol)) t.push({ label: 'Mis cápsulas', nodo: <MisCapsulas /> });
    if (rol && ROLES_CAMPANAS.includes(rol)) t.push({ label: 'Campañas', nodo: <CampanasRefuerzo /> });
    if (rol && ROLES_KPI.includes(rol)) t.push({ label: 'KPI', nodo: <KpiRefuerzo /> });
    return t;
  }, [rol]);

  const activo = Math.min(tab, Math.max(0, tabs.length - 1));

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={800} mb={2}>Refuerzo de Memoria</Typography>
      {tabs.length === 0 ? (
        <Alert severity="info">Tu usuario no tiene acceso a ninguna vista de Refuerzo.</Alert>
      ) : (
        <>
          <Tabs value={activo} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
            {tabs.map((t) => <Tab key={t.label} label={t.label} />)}
          </Tabs>
          {tabs[activo]?.nodo}
        </>
      )}
    </Box>
  );
}
