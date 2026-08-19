import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Box, Card, CardContent, TextField, Button, Typography, Alert, Stack,
  List, ListItem, ListItemIcon, ListItemText, CircularProgress, Link,
} from '@mui/material';
import { CheckCircle, RadioButtonUnchecked, HowToReg } from '@mui/icons-material';
import { authService } from '../../services/auth.service';
import logoImg from '../../assets/mallen-logo.svg';

// Mismo criterio que `password_policy_service.es_especial` del backend: especial es
// cualquier carácter que no sea letra, número ni espacio. \p{L}/\p{N} tratan los acentos
// y la ñ como LETRAS, así que no sirven para cumplir el requisito.
const ESPECIAL = /[^\p{L}\p{N}\s]/u;

export default function ActivarCuenta() {
  const navigate = useNavigate();
  const { token = '' } = useParams();

  const [cargando, setCargando] = useState(true);
  const [info, setInfo] = useState<{ nombre: string; username: string; min_longitud: number } | null>(null);
  const [tokenError, setTokenError] = useState('');
  // Un fallo de RED no es un enlace vencido. Confundirlos manda al usuario a pedir un
  // enlace nuevo (que tampoco le llegará) en vez de decirle que reintente la conexión.
  const [esFalloRed, setEsFalloRed] = useState(false);

  const [pass, setPass] = useState('');
  const [confirmar, setConfirmar] = useState('');
  const [error, setError] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [listo, setListo] = useState(false);

  // Reenvío cuando el enlace venció.
  const [email, setEmail] = useState('');
  const [reenviando, setReenviando] = useState(false);
  const [reenvioMsg, setReenvioMsg] = useState('');

  // Se valida el enlace ANTES de mostrar el formulario: así el usuario sabe de entrada si
  // venció, en vez de escribir una contraseña y que se la rechacen al final.
  useEffect(() => {
    authService.validarActivacion(token)
      .then(setInfo)
      .catch((e: any) => {
        // Sin `e.response` no hubo respuesta del servidor: es red caída, no un enlace malo.
        const sinRespuesta = !e.response;
        setEsFalloRed(sinRespuesta);
        setTokenError(sinRespuesta
          ? 'No pudimos conectar con el servidor. Revisa tu conexión y vuelve a abrir el enlace.'
          : (e.response?.data?.detail || 'El enlace no es válido o ya venció.'));
      })
      .finally(() => setCargando(false));
  }, [token]);

  const minLen = info?.min_longitud ?? 8;
  const reglas = [
    { ok: pass.length >= minLen, txt: `Al menos ${minLen} caracteres` },
    { ok: /[A-Z]/.test(pass), txt: 'Una mayúscula' },
    { ok: /[a-z]/.test(pass), txt: 'Una minúscula' },
    { ok: /[0-9]/.test(pass), txt: 'Un número' },
    { ok: ESPECIAL.test(pass), txt: 'Un carácter especial (!@#$%…)' },
  ];
  const todasOk = reglas.every((r) => r.ok);
  const coincide = pass.length > 0 && pass === confirmar;

  const activar = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setGuardando(true);
    try {
      await authService.activarCuenta(token, pass);
      setListo(true);
      setTimeout(() => navigate('/login', { replace: true }), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'No se pudo activar la cuenta.');
    } finally {
      setGuardando(false);
    }
  };

  const reenviar = async () => {
    setReenviando(true);
    try {
      setReenvioMsg(await authService.reenviarActivacion(email.trim()));
    } catch {
      setReenvioMsg('Si la cuenta existe y está pendiente de activación, recibirás un enlace nuevo.');
    } finally {
      setReenviando(false);
    }
  };

  return (
    <Box sx={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #2A2622 0%, #686158 40%, #584F46 75%, #686158 100%)',
      py: 4,
    }}>
      <Card sx={{ width: 460, mx: 2, borderRadius: 3, boxShadow: 24, overflow: 'hidden' }}>
        <Box sx={{ lineHeight: 0, width: '100%' }}>
          <img src={logoImg} alt="Laboratorios Mallén" style={{ width: '100%', height: 'auto', display: 'block' }} />
        </Box>

        <CardContent sx={{ p: 4, pt: 3 }}>
          {cargando && (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <CircularProgress />
              <Typography variant="body2" color="text.secondary" mt={2}>
                Verificando tu enlace…
              </Typography>
            </Box>
          )}

          {/* Enlace vencido / usado / inválido → se ofrece pedir uno nuevo. */}
          {!cargando && tokenError && (
            <Stack spacing={2}>
              <Alert severity={esFalloRed ? 'warning' : 'error'}>{tokenError}</Alert>
              {/* Si fue la red, pedir otro enlace no arregla nada: el enlace actual puede
                  seguir siendo válido. Se ofrece reintentar. */}
              {esFalloRed ? (
                <Button variant="contained" onClick={() => window.location.reload()}>
                  Reintentar
                </Button>
              ) : (
                <>
                  <Typography variant="body2" color="text.secondary">
                    Escribe tu correo y te enviamos un enlace nuevo.
                  </Typography>
                  <TextField
                    fullWidth size="small" label="Correo electrónico" type="email"
                    value={email} onChange={(e) => setEmail(e.target.value.trim())}
                    inputProps={{ autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
                                  autoComplete: 'email' }}
                  />
                  {reenvioMsg && <Alert severity="success">{reenvioMsg}</Alert>}
                  <Button variant="contained" onClick={reenviar}
                          disabled={reenviando || !email.trim()}>
                    {reenviando ? <CircularProgress size={20} /> : 'Enviarme un enlace nuevo'}
                  </Button>
                </>
              )}
              <Link component="button" type="button" underline="hover"
                    onClick={() => navigate('/login')} sx={{ fontSize: 14 }}>
                Volver al inicio de sesión
              </Link>
            </Stack>
          )}

          {!cargando && listo && (
            <Stack spacing={2} sx={{ textAlign: 'center' }}>
              <CheckCircle color="success" sx={{ fontSize: 48, alignSelf: 'center' }} />
              <Typography variant="h6" fontWeight={700}>¡Cuenta activada!</Typography>
              <Typography variant="body2" color="text.secondary">
                Ya puedes iniciar sesión con tu nueva contraseña. Te llevamos a la pantalla
                de acceso…
              </Typography>
              <Button variant="contained" onClick={() => navigate('/login', { replace: true })}>
                Iniciar sesión
              </Button>
            </Stack>
          )}

          {!cargando && info && !listo && (
            <>
              <Box sx={{ textAlign: 'center', mb: 2 }}>
                <HowToReg color="primary" sx={{ fontSize: 40 }} />
                <Typography variant="h6" fontWeight={700} mt={1}>
                  Hola, {info.nombre}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Crea tu contraseña para activar el acceso de <strong>{info.username}</strong>.
                </Typography>
              </Box>

              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

              <form onSubmit={activar}>
                <Stack spacing={2}>
                  {/* autoCapitalize/autoCorrect apagados: en móvil el teclado capitaliza la
                      primera letra de un campo de texto y eso ya provocó contraseñas
                      distintas a las que el usuario creía haber escrito. */}
                  <TextField
                    label="Nueva contraseña" type="password" fullWidth autoFocus
                    value={pass} onChange={(e) => setPass(e.target.value)}
                    inputProps={{ autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
                                  autoComplete: 'new-password' }}
                  />
                  <TextField
                    label="Confirmar contraseña" type="password" fullWidth
                    value={confirmar} onChange={(e) => setConfirmar(e.target.value)}
                    inputProps={{ autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
                                  autoComplete: 'new-password' }}
                    error={confirmar.length > 0 && !coincide}
                    helperText={confirmar.length > 0 && !coincide ? 'No coinciden' : ' '}
                  />

                  <List dense sx={{ bgcolor: 'action.hover', borderRadius: 1, py: 0.5 }}>
                    {reglas.map((r) => (
                      <ListItem key={r.txt} sx={{ py: 0 }}>
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          {r.ok ? <CheckCircle color="success" fontSize="small" />
                                : <RadioButtonUnchecked color="disabled" fontSize="small" />}
                        </ListItemIcon>
                        <ListItemText primary={r.txt}
                          primaryTypographyProps={{ variant: 'body2',
                            color: r.ok ? 'text.primary' : 'text.secondary' }} />
                      </ListItem>
                    ))}
                  </List>

                  {/* Decir QUÉ falta: en móvil la lista de requisitos queda fuera de pantalla
                      y un botón gris se lee como "no funciona". */}
                  {!guardando && (!todasOk || !coincide) && (
                    <Alert severity="info">
                      {!todasOk
                        ? `Falta: ${reglas.filter((r) => !r.ok).map((r) => r.txt.toLowerCase()).join(', ')}.`
                        : 'Las dos contraseñas no coinciden.'}
                    </Alert>
                  )}

                  <Button type="submit" variant="contained" size="large" fullWidth
                          disabled={guardando || !todasOk || !coincide}
                          sx={{ py: 1.3, borderRadius: 2, fontWeight: 700 }}>
                    {guardando ? <CircularProgress size={24} color="inherit" /> : 'Activar mi cuenta'}
                  </Button>
                </Stack>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
