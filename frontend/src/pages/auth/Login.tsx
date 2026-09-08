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
import { marcaViva, tinteSobre } from '../../theme/marcaViva';

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

  // El enlace es el único texto pequeño a color sobre la tarjeta, así que es el que
  // fija el listón: se ACLARA el azul de acción hasta pasar 4.5:1 contra el fondo de
  // la tarjeta en vez de escribir un tono a mano, que solo serviría para esta marca.
  const azulEnlace = tinteSobre(marcaViva.rojo, marcaViva.taupeProfundo, 4.5);

  // Etiqueta ENCIMA del campo, no flotante: sobre una caja blanca la etiqueta de MUI
  // se apoya en el borde y hay que teñirla contra dos fondos a la vez. Arriba se lee
  // igual con el campo vacío y con el campo lleno.
  const Etiqueta = ({ children }: { children: React.ReactNode }) => (
    <Typography component="label" sx={{ display: 'block', mb: 0.75, fontSize: 14,
                                        fontWeight: 700, color: '#FFFFFF' }}>
      {children}
    </Typography>
  );

  // Campo blanco sobre tarjeta oscura. Va aquí y no repetido en cada TextField para
  // que el próximo campo que se añada nazca con el mismo aspecto.
  const campoBlanco = {
    '& .MuiOutlinedInput-root': {
      bgcolor: '#FFFFFF', borderRadius: 2.5,
      '& input': { color: '#11151F', padding: '14px 16px' },
      '& fieldset': { borderColor: 'transparent' },
      '&:hover fieldset': { borderColor: 'rgba(0,0,0,0.18)' },
      '&.Mui-focused fieldset': { borderColor: marcaViva.rojoTenue, borderWidth: 2 },
    },
    '& .MuiIconButton-root': { color: 'rgba(17,21,31,0.55)' },
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        // Un RESPLANDOR, no una banda: el degradado lineal de antes pintaba una diagonal
        // que cruzaba la tarjeta y la partía en dos tonos. Centrado algo por encima del
        // formulario, el fondo se aclara justo detrás de la tarjeta y se apaga hacia los
        // bordes, así que la tarjeta queda siempre MÁS OSCURA que lo que la rodea y se
        // sostiene sola sin depender del borde.
        background: `radial-gradient(ellipse 95% 75% at 42% 28%, ${marcaViva.rojoOscuro} 0%,`
                  + ` ${marcaViva.taupeProfundo} 48%, ${marcaViva.taupeNegro} 100%)`,
      }}
    >
      <Card sx={{ width: 460, mx: 2, borderRadius: 4, overflow: 'hidden',
                  bgcolor: marcaViva.taupeProfundo,
                  border: '1px solid rgba(255,255,255,0.10)',
                  boxShadow: '0 24px 64px rgba(0,0,0,0.45)',
                  color: '#FFFFFF' }}>
        <CardContent sx={{ p: { xs: 3, sm: 4.5 } }}>
          {/* ESQUINAS REDONDEADAS, y no es decoración. El logotipo de VISTA es un JPEG
              incrustado en el `.svg`: un rectángulo con su propio fondo. Medido sobre el
              archivo, ese fondo NO es plano —va de `#001834` en las esquinas a `#042A64`
              en el centro—, así que ningún color de tarjeta lo hace desaparecer; probé
              igualarlo y se sigue viendo el recuadro. Redondeado y con un filo tenue
              alrededor, la placa se lee como una pieza puesta a propósito en vez de como
              un recorte mal pegado. Desaparecería del todo con un logotipo con
              transparencia; mientras el archivo sea un JPEG, esto es lo honesto.

              Acotado en ancho: a sangre se llevaba casi el 40 % de la tarjeta en un móvil
              y empujaba el botón de entrar contra el borde inferior. */}
          <Box sx={{ display: 'flex', justifyContent: 'center', lineHeight: 0, mb: 2 }}>
            <Box component="img" src={marcaViva.logo.logoColor} alt={marcaViva.logo.nombre}
                 sx={{ width: '100%', maxWidth: { xs: 220, sm: 300 }, height: 'auto',
                       display: 'block', borderRadius: 2,
                       boxShadow: '0 0 0 1px rgba(255,255,255,0.07)' }} />
          </Box>

          <Box sx={{ textAlign: 'center', mb: 3.5 }}>
            {/* El nombre sale de la identidad, no escrito a mano: en la instalación de
                otro cliente esta línea tiene que decir el suyo. */}
            <Typography sx={{ fontSize: 27, fontWeight: 800, letterSpacing: '-0.01em' }}>
              Bienvenido a {marcaViva.logo.nombre}
            </Typography>
            <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.72)', mt: 0.5 }}>
              Ingresa a tu espacio de gestión comercial
            </Typography>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 3 }}>
              {error}
            </Alert>
          )}

          <form onSubmit={handleLogin}>
            <Box sx={{ mb: 2.5 }}>
              <Etiqueta>Usuario</Etiqueta>
              <TextField
                fullWidth
                placeholder="Ingresa tu usuario"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                sx={campoBlanco}
                autoFocus
                disabled={loading}
                // En móvil el teclado autocapitaliza y autocorrige un campo de texto: "mdavid"
                // llegaba como "Mdavid" y el login fallaba con "Credenciales incorrectas".
                inputProps={{ autoCapitalize: 'none', autoCorrect: 'off', spellCheck: false,
                              autoComplete: 'username' }}
              />
            </Box>
            <Box sx={{ mb: 3.5 }}>
              <Etiqueta>Contraseña</Etiqueta>
              <TextField
                fullWidth
                placeholder="Ingresa tu contraseña"
                type={showPwd ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                sx={campoBlanco}
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
            </Box>
            <Button
              fullWidth
              variant="contained"
              size="large"
              type="submit"
              disabled={loading || !username || !password}
              // El azul ACLARADO de la identidad: el de marca sobre esta tarjeta da
              // 2.24:1, por debajo del 3:1 que WCAG 1.4.11 exige a un elemento gráfico,
              // y el botón se difuminaría. Este da 3.42:1 contra la tarjeta.
              sx={{ py: 1.6, borderRadius: 2.5, fontWeight: 700, fontSize: 16,
                    textTransform: 'none', boxShadow: 'none',
                    bgcolor: marcaViva.rojoTenue, color: '#FFFFFF',
                    '&:hover': { bgcolor: marcaViva.rojo, boxShadow: 'none' },
                    '&.Mui-disabled': { bgcolor: 'rgba(255,255,255,0.14)', color: 'rgba(255,255,255,0.45)' } }}
            >
              {loading ? <CircularProgress size={24} color="inherit" /> : 'Iniciar sesión'}
            </Button>
          </form>

          <Box textAlign="center" mt={2.5}>
            <Link component="button" type="button" underline="hover" onClick={abrirFp}
                  sx={{ fontSize: 14, fontWeight: 700, color: azulEnlace }}>
              ¿Olvidaste tu contraseña?
            </Link>
          </Box>

          <Typography variant="caption" display="block" textAlign="center" mt={3}
                      sx={{ color: 'rgba(255,255,255,0.55)' }}>
            v1.0.0 • Confidencial
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
