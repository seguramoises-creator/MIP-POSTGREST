import { useNavigate, useLocation } from 'react-router-dom';
import {
  Drawer, List, ListItemButton, ListItemIcon, ListItemText,
  Box, Chip, Divider,
} from '@mui/material';
import {
  Dashboard, TrendingUp, TrackChanges, LocalHospital, EmojiEvents,
  CloudUpload, Settings, AdminPanelSettings, Assessment,
  SportsScore, Leaderboard, ScatterPlot, Quiz, AssignmentTurnedIn, Groups, MedicalServices,
} from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { Rol } from '../../types';
import logoImg from '../../assets/vista-logo.svg';

const DRAWER_WIDTH = 264;

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  roles: Rol[];
}

export const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard Ejecutivo',   path: '/dashboard',     icon: <Dashboard />,         roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD'] },
  { label: 'Ranking',               path: '/ranking',       icon: <SportsScore />,        roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'REPRESENTANTE_MEDICO', 'CONSULTA'] },
  { label: 'Productividad',         path: '/productividad', icon: <TrendingUp />,         roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'REPRESENTANTE_MEDICO'] },
  { label: 'Indicadores Desempeño', path: '/coaching',      icon: <Leaderboard />,        roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO'] },
  { label: 'Matriz LSII',           path: '/lsii',          icon: <ScatterPlot />,        roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'CONSULTA'] },
  { label: 'Exámenes',              path: '/examenes',      icon: <Quiz />,               roles: ['ADMIN', 'CAPACITACION', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO'] },
  { label: 'Mis Exámenes',          path: '/mis-examenes',  icon: <AssignmentTurnedIn />, roles: ['GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'] },
  { label: 'Exámenes — Equipo',     path: '/examenes-equipo', icon: <Groups />,           roles: ['GERENTE_DISTRITO'] },
  { label: 'Panel Médico',          path: '/visita/panel-medico', icon: <MedicalServices />, roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
  { label: 'Cobertura Visita',      path: '/visita/cobertura', icon: <TrackChanges />,       roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
  { label: 'Cobertura Predictiva',  path: '/cobertura-predictiva', icon: <TrackChanges />, roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA'] },
  { label: 'Categorización Médica', path: '/categorizacion',icon: <LocalHospital />,      roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'CONSULTA'] },
  { label: 'Reconocimiento',        path: '/reconocimiento',icon: <EmojiEvents />,        roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'CONSULTA'] },
  { label: 'Carga Excel (ETL)',      path: '/etl',           icon: <CloudUpload />,        roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD'] },
  { label: 'Reportes',              path: '/reportes',      icon: <Assessment />,         roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'CONSULTA'] },
  { label: 'Configuración',         path: '/admin',         icon: <Settings />,           roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD'] },
  { label: 'Administración',        path: '/usuarios',      icon: <AdminPanelSettings />, roles: ['ADMIN'] },
];

const ROL_LABELS: Record<Rol, string> = {
  ADMIN:                 'Administrador',
  PRESIDENCIA:           'Presidencia',
  DIR_COMERCIAL:         'Dir. Comercial',
  GERENTE_PRODUCTIVIDAD: 'Ger. Productividad',
  GERENTE_DISTRITO:      'Ger. Distrito',
  GERENTE_MARCA:         'Ger. Marca',
  REPRESENTANTE_MEDICO:  'Rep. Médico',
  CAPACITACION:          'Capacitación',
  CONSULTA:              'Consulta',
};

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { rol }  = useAuthStore();

  const visibleItems = NAV_ITEMS.filter(item => rol && item.roles.includes(rol));

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: DRAWER_WIDTH,
          boxSizing: 'border-box',
          background: 'linear-gradient(180deg, #1a237e 0%, #283593 100%)',
          color: 'white',
          overflow: 'hidden auto',
        },
      }}
    >
      {/* ── Área del logo — sin box extra, el SVG ya trae su propio fondo ── */}
      <Box sx={{
        width: '100%',
        overflow: 'hidden',
        borderRadius: '0 0 16px 16px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.35)',
        lineHeight: 0,
        flexShrink: 0,
      }}>
        <img
          src={logoImg}
          alt="VISTA — Inteligencia Comercial"
          style={{
            width: '100%',
            height: 'auto',
            display: 'block',
            objectFit: 'cover',
          }}
        />
      </Box>

      {/* Divisor sutil */}
      <Divider sx={{ borderColor: 'rgba(100,150,255,0.18)', mx: 1.5, mb: 0.5, mt: 0.5 }} />

      {/* ── Navegación ─────────────────────────────────────── */}
      <List dense sx={{ px: 1, pt: 1 }}>
        {visibleItems.map((item) => {
          const active =
            location.pathname.startsWith(item.path) &&
            (item.path !== '/dashboard' || location.pathname === '/dashboard');
          return (
            <ListItemButton
              key={item.path}
              onClick={() => navigate(item.path)}
              selected={active}
              sx={{
                borderRadius: 2,
                mb: 0.4,
                color: active ? 'white' : 'rgba(255,255,255,0.72)',
                bgcolor: active ? 'rgba(255,255,255,0.16) !important' : 'transparent',
                borderLeft: active ? '3px solid rgba(140,190,255,0.9)' : '3px solid transparent',
                '&:hover': { bgcolor: 'rgba(255,255,255,0.09)' },
                transition: 'all 0.15s ease',
              }}
            >
              <ListItemIcon sx={{
                color: active ? 'rgba(160,205,255,1)' : 'rgba(255,255,255,0.55)',
                minWidth: 36,
              }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText
                primary={item.label}
                primaryTypographyProps={{
                  fontSize: '0.83rem',
                  fontWeight: active ? 700 : 400,
                }}
              />
            </ListItemButton>
          );
        })}
      </List>
    </Drawer>
  );
}

export { DRAWER_WIDTH };
