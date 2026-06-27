import { useState } from 'react';
import {
  Box, Card, CardContent, TextField, Button, Typography,
  Alert, CircularProgress, InputAdornment, IconButton, Stepper, Step, StepLabel,
} from '@mui/material';
import { Visibility, VisibilityOff } from '@mui/icons-material';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const API = import.meta.env.VITE_API_URL || '/api/v1';

export default function Setup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    nombre_completo: '',
    username: '',
    email: '',
    password: '',
    confirmar: '',
  });
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handle = (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [e.target.name]: e.target.value });

  const validar = () => {
    if (!form.nombre_completo.trim()) return 'El nombre completo es requerido';
    if (!form.username.trim()) return 'El nombre de usuario es requerido';
    if (!form.email.includes('@')) return 'Correo electrónico inválido';
    if (form.password.length < 12) return 'La contraseña debe tener al menos 12 caracteres';
    if (!/[A-Z]/.test(form.password)) return 'La contraseña debe tener al menos una mayúscula';
    if (!/[a-z]/.test(form.password)) return 'La contraseña debe tener al menos una minúscula';
    if (!/\d/.test(form.password)) return 'La contraseña debe tener al menos un número';
    if (form.password !== form.confirmar) return 'Las contraseñas no coinciden';
    return '';
  };

  const submit = async () => {
    const err = validar();
    if (err) { setError(err); return; }
    setError('');
    setLoading(true);
    try {
      await axios.post(`${API}/setup/inicializar`, {
        nombre_completo: form.nombre_completo,
        username: form.username,
        email: form.email,
        password: form.password,
      });
      setSuccess(true);
      setTimeout(() => navigate('/login'), 2500);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Error al crear el administrador');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #1a237e 0%, #0d47a1 100%)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2,
    }}>
      <Card sx={{ maxWidth: 480, width: '100%', borderRadius: 3, boxShadow: 8 }}>
        <CardContent sx={{ p: 4 }}>
          {/* Logo / título */}
          <Box sx={{ textAlign: 'center', mb: 3 }}>
            <Typography variant="h5" fontWeight={700} color="primary">
              MSM — Sistema MIP
            </Typography>
            <Typography variant="body2" color="text.secondary" mt={0.5}>
              Configuración inicial del sistema
            </Typography>
          </Box>

          <Stepper activeStep={success ? 1 : 0} sx={{ mb: 3 }}>
            <Step><StepLabel>Crear administrador</StepLabel></Step>
            <Step><StepLabel>Iniciar sesión</StepLabel></Step>
          </Stepper>

          {success ? (
            <Alert severity="success" sx={{ mt: 1 }}>
              ¡Administrador creado! Redirigiendo al inicio de sesión…
            </Alert>
          ) : (
            <>
              <Typography variant="body2" color="text.secondary" mb={2}>
                No existen usuarios en el sistema. Crea el primer administrador para comenzar.
              </Typography>

              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

              <TextField fullWidth label="Nombre completo" name="nombre_completo"
                value={form.nombre_completo} onChange={handle} sx={{ mb: 2 }} />
              <TextField fullWidth label="Usuario" name="username"
                value={form.username} onChange={handle} sx={{ mb: 2 }} />
              <TextField fullWidth label="Correo electrónico" name="email" type="email"
                value={form.email} onChange={handle} sx={{ mb: 2 }} />
              <TextField fullWidth label="Contraseña" name="password"
                type={showPwd ? 'text' : 'password'}
                value={form.password} onChange={handle} sx={{ mb: 1 }}
                helperText="Mínimo 12 caracteres, una mayúscula, una minúscula y un número"
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton onClick={() => setShowPwd(!showPwd)} edge="end">
                        {showPwd ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }} />
              <TextField fullWidth label="Confirmar contraseña" name="confirmar"
                type="password" value={form.confirmar} onChange={handle} sx={{ mb: 3 }} />

              <Button fullWidth variant="contained" size="large"
                onClick={submit} disabled={loading}
                sx={{ py: 1.5, fontWeight: 700 }}>
                {loading ? <CircularProgress size={24} color="inherit" /> : 'Crear administrador e iniciar'}
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
