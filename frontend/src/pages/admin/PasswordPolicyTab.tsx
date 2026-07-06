import { useEffect, useState } from 'react';
import {
  Box, Typography, TextField, FormControlLabel, Switch, Button, Alert, Stack, Grid,
} from '@mui/material';
import { api } from '../../services/api';

interface Policy {
  expiracion_activa: boolean;
  expiracion_dias: number;
  aviso_dias: number;
  historial_n: number;
  min_longitud: number;
  min_longitud_admin: number;
}

const CAMPOS_NUM: { key: keyof Policy; label: string; help: string }[] = [
  { key: 'expiracion_dias', label: 'Días para vencer', help: 'Cada cuántos días expira la contraseña.' },
  { key: 'aviso_dias', label: 'Días de aviso previo', help: 'Con cuántos días de anticipación se avisa.' },
  { key: 'historial_n', label: 'Historial (no reutilizar)', help: 'Cuántas contraseñas anteriores no se pueden repetir.' },
  { key: 'min_longitud', label: 'Longitud mínima', help: 'Mínimo de caracteres (usuarios no admin).' },
  { key: 'min_longitud_admin', label: 'Longitud mínima ADMIN', help: 'Mínimo de caracteres para administradores.' },
];

export default function PasswordPolicyTab() {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [saving, setSaving] = useState(false);

  const cargar = () => {
    api.get<Policy>('/admin/config/password-policy')
      .then((r) => setPolicy(r.data))
      .catch(() => setMsg({ tipo: 'error', texto: 'No se pudo cargar la política.' }));
  };
  useEffect(cargar, []);

  const guardar = async () => {
    if (!policy) return;
    setSaving(true); setMsg(null);
    try {
      const { data } = await api.put<Policy>('/admin/config/password-policy', policy);
      setPolicy(data);
      setMsg({ tipo: 'success', texto: 'Política actualizada.' });
    } catch (e: any) {
      setMsg({ tipo: 'error', texto: e.response?.data?.detail || 'No se pudo guardar.' });
    } finally { setSaving(false); }
  };

  if (!policy) return <Typography color="text.secondary">Cargando…</Typography>;

  return (
    <Box sx={{ maxWidth: 640 }}>
      <Typography variant="h6" fontWeight={700} mb={0.5}>Política de contraseñas</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Reglas de seguridad para las contraseñas de los usuarios. Los cambios aplican de inmediato.
      </Typography>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }}>{msg.texto}</Alert>}

      <Stack spacing={2.5}>
        <FormControlLabel
          control={
            <Switch
              checked={policy.expiracion_activa}
              onChange={(e) => setPolicy({ ...policy, expiracion_activa: e.target.checked })}
            />
          }
          label={`Expiración de contraseñas ${policy.expiracion_activa ? 'ACTIVADA' : 'DESACTIVADA'}`}
        />

        <Grid container spacing={2}>
          {CAMPOS_NUM.map((c) => (
            <Grid item xs={12} sm={6} key={c.key}>
              <TextField
                fullWidth
                type="number"
                label={c.label}
                helperText={c.help}
                value={policy[c.key] as number}
                disabled={!policy.expiracion_activa && (c.key === 'expiracion_dias' || c.key === 'aviso_dias')}
                onChange={(e) => setPolicy({ ...policy, [c.key]: Number(e.target.value) })}
              />
            </Grid>
          ))}
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
