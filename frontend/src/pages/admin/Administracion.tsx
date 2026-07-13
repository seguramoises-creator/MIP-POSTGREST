/**
 * Administracion.tsx — Ítem de menú "Administración" (solo ADMIN).
 * Agrupa en 3 pestañas (naranjas): Usuarios · Política de contraseñas · Servidor de
 * Correo (SMTP). Las dos últimas se movieron aquí desde "Configuración" (Admin.tsx).
 */
import { useState } from 'react';
import { Box, Card, Tabs, Tab } from '@mui/material';
import { People, Lock, MarkEmailRead } from '@mui/icons-material';
import Usuarios from './Usuarios';
import PasswordPolicyTab from './PasswordPolicyTab';
import CorreoAdmin from './CorreoAdmin';

const NARANJA = '#ed6c02';

export default function Administracion() {
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Card elevation={0} sx={{ borderRadius: 3, border: '1px solid #eef1f6' }}>
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
            <Tab icon={<Lock fontSize="small" />} iconPosition="start" label="Política de contraseñas" />
            <Tab icon={<MarkEmailRead fontSize="small" />} iconPosition="start" label="Servidor de Correo (SMTP)" />
          </Tabs>
        </Box>

        <Box sx={{ p: { xs: 1, sm: 2 } }}>
          {tab === 0 ? <Usuarios /> : tab === 1 ? <PasswordPolicyTab /> : <CorreoAdmin />}
        </Box>
      </Card>
    </Box>
  );
}
