/**
 * Onboarding.tsx — Onboarding y Biblioteca (§4 y §5).
 * Shell de tabs: cada rol ve los que le corresponden, con los mismos gates que
 * el router backend (`formacion.py`).
 */
import { useMemo, useState } from 'react';
import { Box, Tabs, Tab, Typography, Alert } from '@mui/material';
import { useAuthStore } from '../../store/auth.store';
import MiRuta from './onboarding/MiRuta';
import Biblioteca from './onboarding/Biblioteca';
import RutasAdmin from './onboarding/RutasAdmin';

// "Mi ruta" es del representante (el backend exige enlace a rm_id).
const ROLES_MI_RUTA = ['REPRESENTANTE_MEDICO'];
// Gestión de rutas: RequireContenido del backend (crear plantillas). GERENTE_MEDICO
// sí puede operar este tab; solo «Asignar» le está vedado (RequireCapacitacion),
// y ese botón se oculta para él dentro del tab.
const ROLES_RUTAS = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'GERENTE_MEDICO'];
// Biblioteca: listar es RequireAnyAuth; las acciones se gatean dentro del tab.
const ROLES_BIBLIOTECA = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION',
  'GERENTE_MEDICO', 'PRESIDENCIA', 'GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'];

export default function Onboarding() {
  const rol = useAuthStore((s) => s.rol);
  const [tab, setTab] = useState(0);

  const tabs = useMemo(() => {
    const t: { label: string; nodo: JSX.Element }[] = [];
    if (rol && ROLES_MI_RUTA.includes(rol)) t.push({ label: 'Mi ruta', nodo: <MiRuta /> });
    if (rol && ROLES_BIBLIOTECA.includes(rol)) t.push({ label: 'Biblioteca', nodo: <Biblioteca /> });
    if (rol && ROLES_RUTAS.includes(rol)) t.push({ label: 'Rutas y plantillas', nodo: <RutasAdmin /> });
    return t;
  }, [rol]);

  const activo = Math.min(tab, Math.max(0, tabs.length - 1));

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={800} mb={2}>Formación inicial</Typography>
      {tabs.length === 0 ? (
        <Alert severity="info">Tu usuario no tiene acceso a ninguna vista de Formación inicial.</Alert>
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
