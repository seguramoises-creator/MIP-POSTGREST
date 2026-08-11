/**
 * MedicosTopConfigTab.tsx — Parámetros del cron de avisos de Médicos TOP (§7.3).
 *
 * Gobierna a quién le llega un correo real (representantes y sus Gerentes de
 * Distrito): cuántos días de gracia se dan antes del recordatorio y a qué % del
 * ciclo se escala al GD, más el interruptor de emergencia del cron completo.
 * Mismo mecanismo de configuración en BD que ya usa el Servidor de Correo (SMTP)
 * y la Política de contraseñas — sin migración, sin redesplegar.
 */
import { useEffect, useState } from 'react';
import {
  Box, Typography, TextField, FormControlLabel, Switch, Button, Alert, Stack, Grid,
} from '@mui/material';
import { api } from '../../services/api';

interface TopConfig {
  dias_recordatorio: number;
  pct_ciclo_escalamiento: number;
  avisos_activos: boolean;
  dias_recordatorio_default: number;
  pct_ciclo_escalamiento_default: number;
  avisos_activos_default: boolean;
}

export default function MedicosTopConfigTab() {
  const [cfg, setCfg] = useState<TopConfig | null>(null);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const cargar = () => {
    api.get<TopConfig>('/admin/config/medicos-top')
      .then((r) => setCfg(r.data))
      .catch(() => setMsg({ tipo: 'error', texto: 'No se pudo cargar la configuración.' }));
  };
  useEffect(cargar, []);

  const guardar = async () => {
    if (!cfg) return;
    setSaving(true); setMsg(null);
    try {
      const { data } = await api.put<TopConfig>('/admin/config/medicos-top', {
        dias_recordatorio: cfg.dias_recordatorio,
        pct_ciclo_escalamiento: cfg.pct_ciclo_escalamiento,
        avisos_activos: cfg.avisos_activos,
      });
      setCfg(data);
      setMsg({ tipo: 'success', texto: 'Configuración guardada. El próximo corte del cron ya la usa.' });
    } catch (e: any) {
      setMsg({ tipo: 'error', texto: e.response?.data?.detail || 'No se pudo guardar.' });
    } finally { setSaving(false); }
  };

  if (!cfg) return <Typography color="text.secondary">Cargando…</Typography>;

  return (
    <Box sx={{ maxWidth: 640 }}>
      <Typography variant="h6" fontWeight={700} mb={0.5}>Avisos de Médicos TOP</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Controla el cron diario que recuerda al representante las visitas vencidas a
        médicos TOP y escala al Gerente de Distrito si el ciclo avanza sin cubrirlas.
        Los cambios aplican de inmediato, sin redesplegar.
      </Typography>

      <Alert severity="warning" sx={{ mb: 2 }}>
        Los valores por defecto ({cfg.dias_recordatorio_default} días / {cfg.pct_ciclo_escalamiento_default}%)
        son una posición razonable, <strong>no una decisión cerrada</strong>: siguen pendientes de
        confirmar con el laboratorio (Mallén). Quien los ajuste debe saber que puede cambiar.
        Dejar un campo vacío equivale a usar el valor por defecto.
      </Alert>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      <Stack spacing={2.5}>
        <FormControlLabel
          control={
            <Switch
              checked={cfg.avisos_activos}
              onChange={(e) => setCfg({ ...cfg, avisos_activos: e.target.checked })}
            />
          }
          label={`Avisos de médicos TOP ${cfg.avisos_activos ? 'ACTIVADOS' : 'DESACTIVADOS'}`}
        />
        <Typography variant="caption" color="text.secondary" sx={{ mt: -1.5 }}>
          Interruptor de emergencia: lo apaga por completo (recordatorio + escalamiento) sin
          tocar código ni redesplegar, por si el cron se comporta mal en producción.
        </Typography>

        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              type="number"
              label="Días de gracia para el recordatorio"
              helperText="Días hábiles tras la fecha planeada antes de avisar al representante."
              value={cfg.dias_recordatorio}
              disabled={!cfg.avisos_activos}
              onChange={(e) => setCfg({ ...cfg, dias_recordatorio: Number(e.target.value) })}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              type="number"
              label="% del ciclo para escalar al GD"
              helperText="% de días hábiles del ciclo transcurridos antes de escalar al Gerente de Distrito."
              value={cfg.pct_ciclo_escalamiento}
              disabled={!cfg.avisos_activos}
              onChange={(e) => setCfg({ ...cfg, pct_ciclo_escalamiento: Number(e.target.value) })}
            />
          </Grid>
        </Grid>

        <Box>
          <Button variant="contained" onClick={guardar} disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar cambios'}
          </Button>
        </Box>
      </Stack>
    </Box>
  );
}
