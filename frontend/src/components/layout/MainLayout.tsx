import { Outlet, useNavigate } from 'react-router-dom';
import {
  Box, AppBar, Toolbar, Typography, IconButton,
  Tooltip, Avatar, Menu, MenuItem, Divider,
} from '@mui/material';
import { Logout, AccountCircle } from '@mui/icons-material';
import { useState } from 'react';
import Sidebar, { DRAWER_WIDTH } from './Sidebar';
import { useAuthStore } from '../../store/auth.store';
import { authService } from '../../services/auth.service';

export default function MainLayout() {
  const navigate = useNavigate();
  const { nombreCompleto, accessToken, logout } = useAuthStore();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const handleLogout = async () => {
    await authService.logout(accessToken || '');
    logout();
    navigate('/login');
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar />
      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
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
          <Toolbar sx={{ justifyContent: 'space-between' }}>
            <Typography variant="subtitle1" fontWeight={600} color="text.secondary">
              Sistema Corporativo de Gestión Comercial
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              {nombreCompleto && (
                <Typography
                  variant="body2"
                  fontWeight={600}
                  sx={{ color: 'text.primary', letterSpacing: '0.2px' }}
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
          <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
            <Logout sx={{ mr: 1 }} /> Cerrar sesión
          </MenuItem>
        </Menu>

        <Box sx={{ flexGrow: 1, p: 3, bgcolor: '#f5f6fa' }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
