import { Outlet, useNavigate, useLocation, Navigate } from 'react-router-dom';
import {
  Box, AppBar, Toolbar, Typography, IconButton,
  Tooltip, Avatar, Menu, MenuItem, Divider, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, Button, Alert, Stack,
} from '@mui/material';
import { Logout, AccountCircle, LockReset, SupervisorAccount, Menu as MenuIcon } from '@mui/icons-material';
import { useState, useEffect } from 'react';
import Sidebar, { DRAWER_WIDTH } from './Sidebar';
import { useAuthStore } from '../../store/auth.store';
import { authService } from '../../services/auth.service';
import { api } from '../../services/api';
import { miGerente, type MiGerente } from '../../services/visita.service';
import CicloPaisBadge from '../CicloPaisBadge';
import CicloPaisHeader from '../CicloPaisHeader';

export default function MainLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // Franja global País+Ciclo: se oculta donde es redundante — en /visita/registrar
  // (el registro siempre va al ciclo abierto) y en las páginas que ya traen sus
  // propios selectores de País/Ciclo o no dependen del ciclo (dashboard, LSII, los
  // módulos de análisis, ETL/Reportes con filtros propios, y Admin/Usuarios).
  const HEADER_OCULTO = [
    '/visita/registrar', '/dashboard', '/lsii',
    '/coaching', '/productividad', '/ranking', '/reconocimiento', '/cobertura-predictiva',
    '/etl', '/reportes', '/usuarios', '/admin',
  ];
  const headerEnLayout = !HEADER_OCULTO.includes(pathname);
  const { nombreCompleto, accessToken, rol, logout } = useAuthStore();
  const debeCambiarPassword = useAuthStore((s) => s.debeCambiarPassword);
  const passwordMotivo = useAuthStore((s) => s.passwordMotivo);
  const passwordExpiraEnDias = useAuthStore((s) => s.passwordExpiraEnDias);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [gd, setGd] = useState<MiGerente | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);   // menú lateral en móvil (overlay)

  // El representante ve su Gerente de Distrito de la línea arriba a la derecha.
  useEffect(() => {
    if (rol === 'REPRESENTANTE_MEDICO') miGerente().then(setGd).catch(() => setGd(null));
    else setGd(null);
  }, [rol]);

  const [pwOpen, setPwOpen] = useState(false);
  const [pwActual, setPwActual] = useState('');
  const [pwNueva, setPwNueva] = useState('');
  const [pwMsg, setPwMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [pwSaving, setPwSaving] = useState(false);

  const handleLogout = async () => {
    await authService.logout(accessToken || '');
    logout();
    navigate('/login');
  };

  const abrirCambioPassword = () => { setAnchorEl(null); setPwMsg(null); setPwActual(''); setPwNueva(''); setPwOpen(true); };

  const handleCambiarPassword = async () => {
    setPwSaving(true); setPwMsg(null);
    try {
      await api.post('/auth/change-password', { password_actual: pwActual, password_nuevo: pwNueva });
      setPwMsg({ tipo: 'success', texto: 'Contraseña actualizada correctamente.' });
      setPwActual(''); setPwNueva('');
    } catch (e: unknown) {
      const detalle = (e as { response?: { data?: { detail?: string | { msg?: string }[] } } })?.response?.data?.detail;
      const texto = Array.isArray(detalle) ? (detalle[0]?.msg || 'Datos inválidos') : (detalle || 'No se pudo cambiar la contraseña.');
      setPwMsg({ tipo: 'error', texto: String(texto) });
    } finally { setPwSaving(false); }
  };

  // Cambio forzoso: si la política exige cambiar la contraseña, no se puede
  // usar el sistema hasta hacerlo (se manda a la pantalla dedicada).
  if (debeCambiarPassword) return <Navigate to="/cambiar-password" replace />;

  const avisoVencimiento = passwordMotivo === 'por_expirar' && passwordExpiraEnDias != null;

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />
      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <AppBar
          position="sticky"
          elevation={0}
          sx={{
            bgcolor: 'white',
            borderBottom: '1px solid',
            borderColor: 'divider',
            color: 'text.primary',
          }}
        >
          <Toolbar sx={{ justifyContent: 'space-between', gap: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
              {/* Botón ☰ — solo en móvil/tablet; abre el menú lateral en overlay. */}
              <IconButton edge="start" onClick={() => setMobileOpen(true)}
                          aria-label="Abrir menú" sx={{ display: { xs: 'inline-flex', md: 'none' } }}>
                <MenuIcon />
              </IconButton>
              {/* Título largo: oculto en teléfono (app-like); visible desde tablet. */}
              <Typography variant="subtitle1" fontWeight={600} color="text.secondary" noWrap
                          sx={{ fontSize: { sm: '0.9rem', md: '1rem' }, display: { xs: 'none', sm: 'block' } }}>
                Sistema Corporativo de Gestión Comercial
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.75, sm: 1.5 } }}>
              <CicloPaisBadge />
              {gd?.gerente && (
                <Tooltip title={`Gerente de Distrito${gd.linea ? ` · Línea ${gd.linea}` : ''}`}>
                  <Chip
                    size="small"
                    color="primary"
                    variant="outlined"
                    icon={<SupervisorAccount />}
                    label={`Gerente de Distrito: ${gd.gerente}`}
                    sx={{ fontWeight: 600, display: { xs: 'none', md: 'inline-flex' } }}
                  />
                </Tooltip>
              )}
              {nombreCompleto && (
                <Typography
                  variant="body2"
                  fontWeight={600}
                  noWrap
                  sx={{ color: 'text.primary', letterSpacing: '0.2px', display: { xs: 'none', md: 'block' } }}
                >
                  {nombreCompleto}
                </Typography>
              )}
              <Tooltip title="Opciones de cuenta">
                <IconButton onClick={(e) => setAnchorEl(e.currentTarget)} size="small">
                  <Avatar sx={{ width: 34, height: 34, bgcolor: 'primary.main', fontSize: '0.9rem' }}>
                    {nombreCompleto?.[0]?.toUpperCase() || 'U'}
                  </Avatar>
                </IconButton>
              </Tooltip>
            </Box>
          </Toolbar>
        </AppBar>

        <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
          <MenuItem disabled>
            <AccountCircle sx={{ mr: 1 }} /> {nombreCompleto}
          </MenuItem>
          <Divider />
          <MenuItem onClick={abrirCambioPassword}>
            <LockReset sx={{ mr: 1 }} /> Cambiar contraseña
          </MenuItem>
          <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
            <Logout sx={{ mr: 1 }} /> Cerrar sesión
          </MenuItem>
        </Menu>

        <Dialog open={pwOpen} onClose={() => setPwOpen(false)} maxWidth="xs" fullWidth>
          <DialogTitle>Cambiar contraseña</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              {pwMsg && <Alert severity={pwMsg.tipo}>{pwMsg.texto}</Alert>}
              <TextField label="Contraseña actual" type="password" value={pwActual}
                         onChange={(e) => setPwActual(e.target.value)} fullWidth autoComplete="current-password" />
              <TextField label="Contraseña nueva" type="password" value={pwNueva}
                         onChange={(e) => setPwNueva(e.target.value)} fullWidth autoComplete="new-password"
                         helperText="Mín. 12 caracteres, con mayúscula, minúscula y número." />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setPwOpen(false)}>Cerrar</Button>
            <Button variant="contained" onClick={handleCambiarPassword}
                    disabled={pwSaving || !pwActual || !pwNueva}>
              {pwSaving ? 'Guardando…' : 'Cambiar'}
            </Button>
          </DialogActions>
        </Dialog>

        <Box sx={{ flexGrow: 1, p: { xs: 1.5, sm: 3 }, bgcolor: '#f5f6fa', minWidth: 0, overflowX: 'hidden' }}>
          {avisoVencimiento && (
            <Alert
              severity="warning"
              sx={{ mb: 2 }}
              action={
                <Button color="inherit" size="small" onClick={() => navigate('/cambiar-password')}>
                  Cambiar ahora
                </Button>
              }
            >
              Tu contraseña vence en {passwordExpiraEnDias} día(s). Te recomendamos cambiarla.
            </Alert>
          )}
          {headerEnLayout && <CicloPaisHeader />}
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
