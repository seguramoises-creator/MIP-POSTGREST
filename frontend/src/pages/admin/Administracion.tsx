/**
 * Administracion.tsx — Ítem de menú "Administración" (solo ADMIN).
 * Agrupa pestañas (naranjas): Usuarios · Roles y Permisos · Política de contraseñas ·
 * Servidor de Correo (SMTP) · Avisos de Médicos TOP · Matriz de Errores.
 */
import { useState } from 'react';
import { Box, Card, Tabs, Tab } from '@mui/material';
import { People, Security, Lock, MarkEmailRead, ReportProblem, NotificationsActive } from '@mui/icons-material';
import Usuarios from './Usuarios';
import MatrizRoles from './MatrizRoles';
import PasswordPolicyTab from './PasswordPolicyTab';
import CorreoAdmin from './CorreoAdmin';
import MedicosTopConfigTab from './MedicosTopConfigTab';
import CatalogoErrores from './CatalogoErrores';

const NARANJA = '#ed6c02';

export default function Administracion() {
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Card elevation={0} sx={{ borderRadius: 3, border: '1px solid #EFEBE6' }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            TabIndicatorProps={{ sx: { backgroundColor: NARANJA, height: 3 } }}
            sx={{
              '& .MuiTab-root': { fontWeight: 700, textTransform: 'none', color: 'text.secondary' },
              '& .MuiTab-root.Mui-selected': { color: NARANJA },
            }}
          >
            <Tab icon={<People fontSize="small" />} iconPosition="start" label="Usuarios" />
            <Tab icon={<Security fontSize="small" />} iconPosition="start" label="Roles y Permisos" />
            <Tab icon={<Lock fontSize="small" />} iconPosition="start" label="Política de contraseñas" />
            <Tab icon={<MarkEmailRead fontSize="small" />} iconPosition="start" label="Servidor de Correo (SMTP)" />
            <Tab icon={<NotificationsActive fontSize="small" />} iconPosition="start" label="Avisos Médicos TOP" />
            <Tab icon={<ReportProblem fontSize="small" />} iconPosition="start" label="Matriz de Errores" />
          </Tabs>
        </Box>

        <Box sx={{ p: { xs: 1, sm: 2 } }}>
          {tab === 0 ? <Usuarios />
            : tab === 1 ? <MatrizRoles />
            : tab === 2 ? <PasswordPolicyTab />
            : tab === 3 ? <CorreoAdmin />
            : tab === 4 ? <MedicosTopConfigTab />
            : <CatalogoErrores />}
        </Box>
      </Card>
    </Box>
  );
}
