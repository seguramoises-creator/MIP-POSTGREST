import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Card, CardContent, TextField, Button, Typography, Alert, Stack,
  List, ListItem, ListItemIcon, ListItemText,
} from '@mui/material';
import { CheckCircle, RadioButtonUnchecked, LockReset, Logout } from '@mui/icons-material';
import { api } from '../../services/api';
import { useAuthStore } from '../../store/auth.store';
import { authService } from '../../services/auth.service';
import { marcaViva } from '../../theme/marcaViva';

// Carácter especial = cualquiera que no sea letra, número ni espacio. Debe coincidir con
// `password_policy_service.es_especial` del backend. La lista fija anterior dejaba fuera
// símbolos muy a mano en teclados móviles en español (¿ ¡ ' " `) y el botón no se
// habilitaba nunca. \p{L}/\p{N} respetan acentos y ñ como LETRAS, no como especiales.
const ESPECIAL = /[^\p{L}\p{N}\s]/u;

export default function CambiarPassword() {
  const navigate = useNavigate();
  const rol = useAuthStore((s) => s.rol);
  const debeCambiar = useAuthStore((s) => s.debeCambiarPassword);
  const setPasswordEstado = useAuthStore((s) => s.setPasswordEstado);
  const accessToken = useAuthStore((s) => s.accessToken);
  const logout = useAuthStore((s) => s.logout);

  // La longitud mínima es CONFIGURABLE en BD y varía por rol: se consulta al backend en
  // vez de fijarla aquí. Con el valor fijo, si el ADMIN subía el mínimo desde Política de
  // contraseñas, la lista mostraba un número equivocado y el botón no se habilitaba nunca.
  const [minLen, setMinLen] = useState(rol === 'ADMIN' ? 12 : 8);
  useEffect(() => {
    api.get<{ min_longitud: number }>('/auth/password-policy')
      .then((r) => { if (r.data?.min_longitud) setMinLen(r.data.min_longitud); })
      .catch(() => { /* sin conexión: queda el valor por defecto */ });
  }, []);
  const [actual, setActual] = useState('');
  const [nueva, setNueva] = useState('');
  const [confirmar, setConfirmar] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Auto-verificación: el estado persistido en el navegador puede quedar viejo
  // (p. ej. tras una corrección en la BD). Se consulta /auth/me: si el servidor
  // dice que NO hay que cambiar la contraseña, se sale solo de esta pantalla.
  useEffect(() => {
    api.get('/auth/me')
      .then(({ data }) => {
        if (!data.debe_cambiar_password) {
          setPasswordEstado({
            debeCambiarPassword: false,
            passwordExpiraEnDias: data.password_expira_en_dias ?? null,
            passwordMotivo: 'ok',
          });
          navigate('/dashboard', { replace: true });
        }
      })
      .catch(() => { /* sin red o token vencido: se queda en la pantalla */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLogout = async () => {
    await authService.logout(accessToken || '');
    logout();
    navigate('/login', { replace: true });
  };

  // Requisitos evaluados en vivo (guía visual; el backend es la validación real).
  const reglas = [
    { ok: nueva.length >= minLen, txt: `Al menos ${minLen} caracteres` },
    { ok: /[A-Z]/.test(nueva), txt: 'Una mayúscula' },
    { ok: /[a-z]/.test(nueva), txt: 'Una minúscula' },
    { ok: /[0-9]/.test(nueva), txt: 'Un número' },
    { ok: ESPECIAL.test(nueva), txt: 'Un carácter especial (!@#$%…)' },
  ];
  const todasOk = reglas.every((r) => r.ok);
  const coincide = nueva.length > 0 && nueva === confirmar;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!coincide) { setError('Las contraseñas no coinciden'); return; }
    setSaving(true);
    try {
      await api.post('/auth/change-password', { password_actual: actual, password_nuevo: nueva });
      setPasswordEstado({ debeCambiarPassword: false, passwordExpiraEnDias: null, passwordMotivo: 'ok' });
      navigate('/dashboard');
    } catch (err: any) {
      const detalle = err.response?.data?.detail;
      setError(typeof detalle === 'string' ? detalle : 'No se pudo cambiar la contraseña.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: marcaViva.degradadoEntrada,
    }}>
      <Card sx={{ width: 460, mx: 2, borderRadius: 3, boxShadow: 24 }}>
        <CardContent sx={{ p: 4 }}>
          <Box sx={{ textAlign: 'center', mb: 2 }}>
            <LockReset color="primary" sx={{ fontSize: 40 }} />
            <Typography variant="h6" fontWeight={700} mt={1}>Cambia tu contraseña</Typography>
            <Typography variant="body2" color="text.secondary">
              {debeCambiar
                ? 'Por seguridad debes definir una nueva contraseña para continuar.'
                : 'Actualiza tu contraseña.'}
            </Typography>
          </Box>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <form onSubmit={handleSubmit}>
            <Stack spacing={2}>
              <TextField label="Contraseña actual" type="password" value={actual}
                         onChange={(e) => setActual(e.target.value)} fullWidth autoFocus
                         autoComplete="current-password" />
              <TextField label="Nueva contraseña" type="password" value={nueva}
                         onChange={(e) => setNueva(e.target.value)} fullWidth
                         autoComplete="new-password" />
              <TextField label="Confirmar nueva contraseña" type="password" value={confirmar}
                         onChange={(e) => setConfirmar(e.target.value)} fullWidth
                         autoComplete="new-password"
                         error={confirmar.length > 0 && !coincide}
                         helperText={confirmar.length > 0 && !coincide ? 'No coinciden' : ' '} />

              <List dense sx={{ bgcolor: 'action.hover', borderRadius: 1, py: 0.5 }}>
                {reglas.map((r) => (
                  <ListItem key={r.txt} sx={{ py: 0 }}>
                    <ListItemIcon sx={{ minWidth: 32 }}>
                      {r.ok ? <CheckCircle color="success" fontSize="small" />
                            : <RadioButtonUnchecked color="disabled" fontSize="small" />}
                    </ListItemIcon>
                    <ListItemText primary={r.txt}
                      primaryTypographyProps={{ variant: 'body2', color: r.ok ? 'text.primary' : 'text.secondary' }} />
                  </ListItem>
                ))}
              </List>

              {/* Decir QUÉ falta: en móvil la lista de requisitos suele quedar fuera de
                  pantalla y el botón gris se lee como "no funciona". */}
              {!saving && (!actual || !todasOk || !coincide) && (
                <Alert severity="info" sx={{ mb: 1.5 }}>
                  {!actual
                    ? 'Falta escribir tu contraseña actual (la temporal que te dieron).'
                    : !todasOk
                      ? `Falta: ${reglas.filter((r) => !r.ok).map((r) => r.txt.toLowerCase()).join(', ')}.`
                      : 'Las dos contraseñas nuevas no coinciden.'}
                </Alert>
              )}

              <Button type="submit" variant="contained" size="large" fullWidth
                      disabled={saving || !actual || !todasOk || !coincide}
                      sx={{ py: 1.3, borderRadius: 2, fontWeight: 700 }}>
                {saving ? 'Guardando…' : 'Cambiar contraseña'}
              </Button>
              <Button startIcon={<Logout />} color="inherit" size="small" onClick={handleLogout}
                      sx={{ alignSelf: 'center', color: 'text.secondary', textTransform: 'none' }}>
                Cerrar sesión
              </Button>
            </Stack>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}
