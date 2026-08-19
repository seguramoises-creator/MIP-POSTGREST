import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, CircularProgress, InputAdornment, IconButton, Link,
  Dialog, DialogTitle, DialogContent, DialogActions, Stack,
} from '@mui/material';
import { Visibility, VisibilityOff } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { authService } from '../../services/auth.service';
import { Rol } from '../../types';
import logoImg from '../../assets/mallen-logo.svg';

export default function Login() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // ── "Olvidó su contraseña" — flujo en 2 pasos (correo → código + nueva) ──
  const [fpOpen, setFpOpen] = useState(false);
  const [fpStep, setFpStep] = useState<1 | 2>(1);
  const [fpEmail, setFpEmail] = useState('');
  const [fpCodigo, setFpCodigo] = useState('');
  const [fpPass, setFpPass] = useState('');
  const [fpConfirm, setFpConfirm] = useState('');
  const [fpMsg, setFpMsg] = useState('');
  const [fpErr, setFpErr] = useState('');
  const [fpLoading, setFpLoading] = useState(false);
  const fpCoincide = fpPass.length > 0 && fpPass === fpConfirm;

  const abrirFp = () => {
    setFpOpen(true); setFpStep(1); setFpEmail(''); setFpCodigo(''); setFpPass(''); setFpConfirm('');
    setFpMsg(''); setFpErr('');
  };

  const fpEnviarCodigo = async () => {
    setFpErr(''); setFpMsg(''); setFpLoading(true);
    try {
      const msg = await authService.forgotPassword(fpEmail.trim());
      setFpMsg(msg);       // mensaje genérico del backend
      setFpStep(2);        // pasa a ingresar el código
    } catch (e: any) {
      setFpErr(e.response?.data?.detail || 'No se pudo procesar la solicitud.');
    } finally { setFpLoading(false); }
  };

  const fpRestablecer = async () => {
    setFpErr(''); setFpMsg(''); setFpLoading(true);
    try {
      const msg = await authService.resetPassword(fpEmail.trim(), fpCodigo.trim(), fpPass);
      setFpMsg(msg);
      setTimeout(() => setFpOpen(false), 2500);   // cierra tras confirmar
    } catch (e: any) {
      setFpErr(e.response?.data?.detail || 'No se pudo restablecer la contraseña.');
    } finally { setFpLoading(false); }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const tokens = await authService.login(username, password);
      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);

      const payload = authService.decodeToken(tokens.access_token);
      const rol = (payload?.rol || 'CONSULTA') as Rol;
      const nombreCompleto = payload?.nombre_completo || username;

      setAuth({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        username,
        rol,
        nombreCompleto,
        debeCambiarPassword: tokens.debe_cambiar_password ?? false,
        passwordExpiraEnDias: tokens.password_expira_en_dias ?? null,
        passwordMotivo: tokens.password_motivo ?? 'ok',
      });
      navigate(tokens.debe_cambiar_password ? '/cambiar-password' : '/dashboard');
    } catch (err: any) {
      // SIN respuesta del servidor no se puede afirmar nada sobre las credenciales: la
      // petición no llegó a salir. Antes se caía al «Credenciales incorrectas» por omisión
      // y la app acusaba a la contraseña justo en el único caso en que no lo sabe — con el
      // servidor apagado, sin red o con un túnel caído. Ese mensaje llegó a costar una tarde
      // de buscar claves y restablecer cuentas mientras el problema era la conexión.
      const msg = !err.response
        ? 'No se pudo contactar el servidor. Revisa tu conexión y vuelve a intentar.'
        : (err.response.data?.detail || err.response.data?.error || 'Credenciales incorrectas');
      setError(typeof msg === 'string' ? msg : 'Error al iniciar sesión');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        // Degradado del taupe Mallén. El rojo de marca NO entra aquí: como fondo a pantalla
        // completa competiría con el botón de acción, que es lo único que debe pedir el clic.
        background: 'linear-gradient(135deg, #2A2622 0%, #3A342F 40%, #584F46 75%, #686158 100%)',
      }}
    >
      <Card sx={{ width: 440, mx: 2, borderRadius: 3, boxShadow: 24, overflow: 'hidden' }}>
        {/* El logotipo a color de Mallén es vector SIN fondo propio, y sus contraformas
            (los huecos de la abeja y de las letras) están dibujadas en blanco. Necesita
            por tanto una superficie clara y aire alrededor: a sangre, como iba el logo
            anterior —que traía su propio fondo oscuro incrustado—, las contraformas se
            confundirían con el borde de la tarjeta. */}
        <Box sx={{ bgcolor: '#FFFFFF', px: 5, py: 4, lineHeight: 0 }}>
          <img
            src={logoImg}
            alt="Laboratorios Mallén"
            style={{ width: '100%', height: 'auto', display: 'block' }}
          />
        </Box>

        <CardContent sx={{ p: 4, pt: 3 }}>
          {/* Subtítulo */}
          <Box sx={{ textAlign: 'center', mb: 3 }}>
            <Typography variant="body2" color="text.secondary">
              Sistema Corporativo de Gestión Comercial
            </Typography>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 3 }}>
              {error}
            </Alert>
          )}

          <form onSubmit={handleLogin}>
            <TextField
              fullWidth
              label="Usuario"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              sx={{ mb: 2.5 }}
              autoFocus
              disabled={loading}
              // En móvil el teclado autocapitaliza y autocorrige un campo de texto: "mdavid"
              // llegaba como "Mdavid" y el login fallaba con "Credenciales incorrectas".
              inputProps={{ autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
                            autoComplete: 'username' }}
            />
            <TextField
              fullWidth
              label="Contraseña"
              type={showPwd ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              sx={{ mb: 3 }}
              disabled={loading}
              // Al pulsar el ojo el campo pasa a texto plano: sin esto, el móvil
              // autocapitalizaría lo que se escriba a partir de ese momento.
              inputProps={{ autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
                            autoComplete: 'current-password' }}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPwd(!showPwd)} edge="end">
                      {showPwd ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <Button
              fullWidth
              variant="contained"
              size="large"
              type="submit"
              disabled={loading || !username || !password}
              sx={{ py: 1.5, borderRadius: 2, fontWeight: 700 }}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : 'Iniciar Sesión'}
            </Button>
          </form>

          <Box textAlign="center" mt={2}>
            <Link component="button" type="button" underline="hover" onClick={abrirFp}
                  sx={{ fontSize: 14, fontWeight: 600 }}>
              ¿Olvidó su contraseña?
            </Link>
          </Box>

          <Typography variant="caption" color="text.disabled" display="block" textAlign="center" mt={3}>
            v1.0.0 — Confidencial
          </Typography>
        </CardContent>
      </Card>

      {/* Diálogo de recuperación por correo + código */}
      <Dialog open={fpOpen} onClose={() => setFpOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Recuperar contraseña</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {fpErr && <Alert severity="error" onClose={() => setFpErr('')}>{fpErr}</Alert>}
            {fpMsg && <Alert severity="success">{fpMsg}</Alert>}

            {fpStep === 1 ? (
              <>
                <Typography variant="body2" color="text.secondary">
                  Ingresa el correo asociado a tu cuenta. Si está registrado, recibirás un
                  código de recuperación.
                </Typography>
                <TextField
                  fullWidth size="small" label="Correo electrónico" type="email"
                  value={fpEmail} onChange={(e) => setFpEmail(e.target.value)} autoFocus
                />
              </>
            ) : (
              <>
                <Typography variant="body2" color="text.secondary">
                  Escribe el código de 6 dígitos que enviamos a <strong>{fpEmail}</strong> y tu
                  nueva contraseña. El código vence en 15 minutos.
                </Typography>
                <TextField
                  fullWidth size="small" label="Código de recuperación"
                  value={fpCodigo} onChange={(e) => setFpCodigo(e.target.value.trim())}
                  inputProps={{ inputMode: 'numeric', maxLength: 6, autoCapitalize: 'none',
                                autoCorrect: 'off', spellCheck: false }}
                />
                <TextField
                  fullWidth size="small" label="Nueva contraseña" type="password"
                  value={fpPass} onChange={(e) => setFpPass(e.target.value)}
                  inputProps={{ autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
                                autoComplete: 'new-password' }}
                  helperText="Mayúscula, minúscula, número y un carácter especial (!@#$¿'…)"
                />
                <TextField
                  fullWidth size="small" label="Confirmar nueva contraseña" type="password"
                  value={fpConfirm} onChange={(e) => setFpConfirm(e.target.value)}
                  inputProps={{ autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
                                autoComplete: 'new-password' }}
                  error={fpConfirm.length > 0 && !fpCoincide}
                  helperText={fpConfirm.length > 0 && !fpCoincide ? 'No coinciden' : ' '}
                />
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFpOpen(false)}>Cerrar</Button>
          {fpStep === 1 ? (
            <Button variant="contained" disabled={fpLoading || !fpEmail.trim()} onClick={fpEnviarCodigo}>
              {fpLoading ? <CircularProgress size={18} /> : 'Enviar código'}
            </Button>
          ) : (
            <Button variant="contained"
                    disabled={fpLoading || fpCodigo.trim().length < 6 || fpPass.trim().length < 8 || !fpCoincide}
                    onClick={fpRestablecer}>
              {fpLoading ? <CircularProgress size={18} /> : 'Cambiar contraseña'}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
}
