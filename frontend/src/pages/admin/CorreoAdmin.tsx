/**
 * CorreoAdmin.tsx — Configuración del servidor de correo (SMTP) desde el sistema.
 * Tab de Admin.tsx (solo ADMIN). Los datos se guardan en BD (config_service, claves
 * MAIL_*) y los usa TODO el envío de correo del sistema (recuperación de contraseña,
 * notificaciones de ranking/reconocimiento/exámenes, etc.), con fallback al .env.
 */
import { useEffect, useState } from 'react';
import {
  Box, Card, CardContent, Typography, TextField, Button, Grid, Alert, Stack,
  FormControlLabel, Switch, CircularProgress, Divider, Chip,
} from '@mui/material';
import { Save, Send, MarkEmailRead } from '@mui/icons-material';
import { api } from '../../services/api';

type Cfg = {
  server: string; port: number; username: string; from_email: string;
  from_name: string; tls: boolean; ssl: boolean; password_set: boolean; habilitado: boolean;
};

export default function CorreoAdmin() {
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [password, setPassword] = useState('');   // vacío = no cambiar
  const [testEmail, setTestEmail] = useState('');
  const [msg, setMsg] = useState<{ t: 'success' | 'error' | 'info'; m: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const cargar = () => {
    setLoading(true);
    api.get<Cfg>('/admin/config/correo')
      .then((r) => { setCfg(r.data); setTestEmail(r.data.from_email || ''); })
      .catch((e) => setMsg({ t: 'error', m: e.response?.data?.detail || e.message }))
      .finally(() => setLoading(false));
  };
  useEffect(cargar, []);

  const guardar = async () => {
    if (!cfg) return;
    setSaving(true); setMsg(null);
    try {
      await api.put('/admin/config/correo', {
        server: cfg.server, port: Number(cfg.port) || 587, username: cfg.username,
        password: password || null, from_email: cfg.from_email, from_name: cfg.from_name,
        tls: cfg.tls, ssl: cfg.ssl,
      });
      setPassword('');
      setMsg({ t: 'success', m: 'Configuración de correo guardada.' });
      cargar();
    } catch (e: any) {
      setMsg({ t: 'error', m: e.response?.data?.detail || e.message });
    } finally { setSaving(false); }
  };

  const probar = async () => {
    setTesting(true); setMsg(null);
    try {
      const r = await api.post('/admin/config/correo/probar', { email: testEmail.trim() });
      setMsg({ t: 'success', m: r.data?.message || 'Correo de prueba enviado.' });
    } catch (e: any) {
      setMsg({ t: 'error', m: e.response?.data?.detail || e.message });
    } finally { setTesting(false); }
  };

  if (loading || !cfg) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  const set = (k: keyof Cfg, v: any) => setCfg({ ...cfg, [k]: v });

  return (
    <Card elevation={2} sx={{ borderRadius: 3 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} mb={1}>
          <MarkEmailRead color="primary" />
          <Typography variant="h6" fontWeight={600}>Servidor de Correo (SMTP)</Typography>
          <Chip size="small" color={cfg.habilitado ? 'success' : 'default'}
                label={cfg.habilitado ? 'Activo' : 'Sin configurar'} sx={{ fontWeight: 700 }} />
        </Stack>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Este servidor envía TODOS los correos del sistema (recuperación de contraseña y
          notificaciones). Para Gmail usa <strong>smtp.gmail.com</strong>, puerto <strong>587</strong>,
          TLS activo y una <strong>App Password</strong> de 16 caracteres (no la clave normal).
        </Typography>

        {msg && <Alert severity={msg.t} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.m}</Alert>}

        <Grid container spacing={2}>
          <Grid item xs={12} sm={8}>
            <TextField fullWidth size="small" label="Servidor SMTP" placeholder="smtp.gmail.com"
                       value={cfg.server} onChange={(e) => set('server', e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={4}>
            <TextField fullWidth size="small" label="Puerto" type="number"
                       value={cfg.port} onChange={(e) => set('port', e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField fullWidth size="small" label="Usuario (correo)" value={cfg.username}
                       onChange={(e) => set('username', e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField fullWidth size="small" label="Contraseña / App Password" type="password"
                       value={password} onChange={(e) => setPassword(e.target.value)}
                       placeholder={cfg.password_set ? '•••••••• (guardada — deja vacío para no cambiar)' : ''}
                       helperText={cfg.password_set ? 'Ya hay una guardada; escribe solo si la vas a cambiar.' : 'Requerida para autenticar.'} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField fullWidth size="small" label="Remitente (From)" value={cfg.from_email}
                       onChange={(e) => set('from_email', e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField fullWidth size="small" label="Nombre del remitente" value={cfg.from_name}
                       onChange={(e) => set('from_name', e.target.value)} />
          </Grid>
          <Grid item xs={12}>
            {/* TLS y SSL son mutuamente excluyentes: 587 → TLS (STARTTLS); 465 → SSL. */}
            <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
              <FormControlLabel
                control={<Switch checked={cfg.tls}
                  onChange={(e) => setCfg({ ...cfg, tls: e.target.checked, ssl: e.target.checked ? false : cfg.ssl })} />}
                label="TLS (STARTTLS) — puerto 587" />
              <FormControlLabel
                control={<Switch checked={cfg.ssl}
                  onChange={(e) => setCfg({ ...cfg, ssl: e.target.checked, tls: e.target.checked ? false : cfg.tls })} />}
                label="SSL — puerto 465" />
              <Typography variant="caption" color="text.secondary">
                Gmail: usa TLS con puerto 587 (SSL apagado).
              </Typography>
            </Stack>
          </Grid>
        </Grid>

        <Box mt={2}>
          <Button variant="contained" startIcon={<Save />} disabled={saving} onClick={guardar}>
            {saving ? <CircularProgress size={18} /> : 'Guardar configuración'}
          </Button>
        </Box>

        <Divider sx={{ my: 3 }} />

        <Typography variant="subtitle2" fontWeight={700} mb={1}>Probar envío</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <TextField size="small" label="Enviar prueba a" type="email" sx={{ minWidth: 280 }}
                     value={testEmail} onChange={(e) => setTestEmail(e.target.value)} />
          <Button variant="outlined" startIcon={<Send />} disabled={testing || !testEmail.trim()} onClick={probar}>
            {testing ? <CircularProgress size={18} /> : 'Enviar correo de prueba'}
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block" mt={1}>
          Guarda primero la configuración; la prueba usa lo guardado. Si falla, revisa el servidor,
          puerto, usuario/contraseña (App Password en Gmail) y TLS/SSL.
        </Typography>
      </CardContent>
    </Card>
  );
}
