/**
 * Medicos.tsx — Sección Médicos con dos subpestañas:
 *   1) Categorización (motor A/B/C/D por criterios)
 *   2) Maestro de Médicos (dato general central)
 * El Panel Médico del representante vive aparte, en /visita/panel-medico.
 */
import { useState } from 'react';
import { Box, Tabs, Tab, Typography } from '@mui/material';
import Categorizacion from '../categorizacion/Categorizacion';
import MaestroMedicos from './MaestroMedicos';

export default function Medicos() {
  const [tab, setTab] = useState(0);
  return (
    <Box>
      <Typography variant="h5" fontWeight={700} mb={0.5}>Médicos</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Categorización y maestro central de médicos
      </Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}>
        <Tab label="Categorización" />
        <Tab label="Maestro de Médicos" />
      </Tabs>
      {tab === 0 && <Categorizacion />}
      {tab === 1 && <MaestroMedicos />}
    </Box>
  );
}
