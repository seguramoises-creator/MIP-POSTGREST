import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, CircularProgress, InputAdornment, IconButton,
} from '@mui/material';
import { Visibility, VisibilityOff } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { authService } from '../../services/auth.service';
import { Rol } from '../../types';
import logoImg from '../../assets/vista-logo.svg';

export default function Login() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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
      const msg = err.response?.data?.detail || err.response?.data?.error || 'Credenciales incorrectas';
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
        background: 'linear-gradient(135deg, #0a1a4e 0%, #1a237e 40%, #0d47a1 75%, #01579b 100%)',
      }}
    >
      <Card sx={{ width: 440, mx: 2, borderRadius: 3, boxShadow: 24, overflow: 'hidden' }}>
        {/* Logo — ocupa el ancho completo del card, sin márgenes */}
        <Box sx={{ lineHeight: 0, width: '100%' }}>
          <img
            src={logoImg}
            alt="VISTA — Inteligencia Comercial"
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
            />
            <TextField
              fullWidth
              label="Contraseña"
              type={showPwd ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              sx={{ mb: 3 }}
              disabled={loading}
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

          <Typography variant="caption" color="text.disabled" display="block" textAlign="center" mt={3}>
            v1.0.0 — Confidencial
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
