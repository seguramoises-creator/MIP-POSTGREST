import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Drawer, List, ListItemButton, ListItemIcon, ListItemText,
  Box, Divider, Tooltip, IconButton, Collapse, useMediaQuery, useTheme,
} from '@mui/material';
import {
  Dashboard, TrendingUp, TrackChanges, LocalHospital, EmojiEvents,
  CloudUpload, Settings, AdminPanelSettings, Assessment,
  SportsScore, Leaderboard, ScatterPlot, Quiz, AssignmentTurnedIn, Groups,
  MedicalServices, EditNote, EventNote, ReportProblem, Campaign, Paid,
  ChevronLeft, ChevronRight, Add, Remove,
} from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { Rol } from '../../types';
import logoImg from '../../assets/vista-logo.svg';

const DRAWER_WIDTH = 264;
const DRAWER_WIDTH_COLLAPSED = 72;
const LS_KEY = 'vista.sidebar.collapsed';

// Fondo del sidebar — azul menos intenso para que el texto se lea mejor.
const SIDEBAR_BG = 'linear-gradient(180deg, #2a3a8f 0%, #3d4db0 100%)';
const TXT_OFF = 'rgba(255,255,255,0.88)';   // texto inactivo (mayor contraste que antes)
const ICO_OFF = 'rgba(255,255,255,0.72)';   // icono inactivo
const TXT_ON = '#ffffff';
const ICO_ON = 'rgba(180,215,255,1)';
const DIV_COLOR = 'rgba(160,195,255,0.22)';

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  roles: Rol[];
}

interface NavSection {
  title: string | null;   // null = sin encabezado (el home)
  items: NavItem[];
}

// ── Menú agrupado por flujo de trabajo (Dashboard como home; sin Proyección Visita) ──
export const NAV_SECTIONS: NavSection[] = [
  {
    title: null,
    items: [
      { label: 'Dashboard Ejecutivo', path: '/dashboard', icon: <Dashboard />, roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD'] },
    ],
  },
  {
    title: 'Operación diaria',
    items: [
      { label: 'Registrar Visita',    path: '/visita/registrar', icon: <EditNote />,      roles: ['ADMIN', 'REPRESENTANTE_MEDICO'] },
      { label: 'Cobertura Visita',    path: '/visita/cobertura', icon: <TrackChanges />,  roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
      { label: 'Ruptura / Cierre',    path: '/visita/ruptura',   icon: <ReportProblem />, roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
      { label: 'Parrilla & Muestras', path: '/visita/parrilla',  icon: <Campaign />,      roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
    ],
  },
  {
    title: 'Maestros y planeación',
    items: [
      { label: 'Panel Médico',          path: '/visita/panel-medico', icon: <MedicalServices />, roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
      { label: 'Categorización Médica', path: '/categorizacion',      icon: <LocalHospital />,   roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'CONSULTA'] },
      { label: 'Planeación Ciclo',      path: '/visita/planeacion',   icon: <EventNote />,       roles: ['ADMIN', 'REPRESENTANTE_MEDICO'] },
    ],
  },
  {
    title: 'Desempeño y análisis',
    items: [
      { label: 'Indicadores Desempeño', path: '/coaching',             icon: <Leaderboard />,  roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO'] },
      { label: 'Productividad',         path: '/productividad',        icon: <TrendingUp />,   roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'REPRESENTANTE_MEDICO'] },
      { label: 'Ranking',               path: '/ranking',              icon: <SportsScore />,  roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'REPRESENTANTE_MEDICO', 'CONSULTA'] },
      { label: 'Reconocimiento',        path: '/reconocimiento',       icon: <EmojiEvents />,  roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'CONSULTA'] },
      { label: 'Matriz LSII',           path: '/lsii',                 icon: <ScatterPlot />,  roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'CONSULTA'] },
      { label: 'Cobertura Predictiva',  path: '/cobertura-predictiva', icon: <TrackChanges />, roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA'] },
      { label: 'Costo & ROI',           path: '/visita/costo-roi',     icon: <Paid />,         roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
    ],
  },
  {
    title: 'Formación',
    items: [
      { label: 'Exámenes',          path: '/examenes',        icon: <Quiz />,               roles: ['ADMIN', 'CAPACITACION', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO'] },
      { label: 'Mis Exámenes',      path: '/mis-examenes',    icon: <AssignmentTurnedIn />, roles: ['GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'] },
      { label: 'Exámenes — Equipo', path: '/examenes-equipo', icon: <Groups />,             roles: ['GERENTE_DISTRITO'] },
    ],
  },
  {
    title: 'Datos',
    items: [
      { label: 'Carga Excel (ETL)', path: '/etl',      icon: <CloudUpload />, roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD'] },
      { label: 'Reportes',          path: '/reportes', icon: <Assessment />,  roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'CONSULTA'] },
    ],
  },
  {
    title: 'Sistema',
    items: [
      { label: 'Configuración',   path: '/admin',    icon: <Settings />,           roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD'] },
      { label: 'Administración',  path: '/usuarios', icon: <AdminPanelSettings />, roles: ['ADMIN'] },
    ],
  },
];

// Lista plana (en el orden agrupado) — la usa App.tsx para resolver la ruta inicial por rol.
export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { rol }  = useAuthStore();
  const theme = useTheme();
  const isNarrow = useMediaQuery(theme.breakpoints.down('md'));

  // Sidebar completo colapsado (solo iconos) — preferencia persistida.
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored !== null) return stored === '1';
    return isNarrow;
  });
  useEffect(() => { localStorage.setItem(LS_KEY, collapsed ? '1' : '0'); }, [collapsed]);
  useEffect(() => {
    if (localStorage.getItem(LS_KEY) === null && isNarrow) setCollapsed(true);
  }, [isNarrow]);

  const puedeVer = (item: NavItem) => !!rol && item.roles.includes(rol);

  // Acordeón: qué secciones (con título) están expandidas. Ocultas por defecto;
  // se abre automáticamente la sección de la ruta activa.
  const seccionActiva = NAV_SECTIONS.findIndex(
    (s) => s.title !== null && s.items.some((it) => location.pathname.startsWith(it.path)));
  const [openSections, setOpenSections] = useState<Record<number, boolean>>(
    () => (seccionActiva >= 0 ? { [seccionActiva]: true } : {}));
  useEffect(() => {
    if (seccionActiva >= 0) setOpenSections((p) => ({ ...p, [seccionActiva]: true }));
  }, [seccionActiva]);
  const toggleSection = (i: number) => setOpenSections((p) => ({ ...p, [i]: !p[i] }));

  const width = collapsed ? DRAWER_WIDTH_COLLAPSED : DRAWER_WIDTH;

  // Fila de navegación (item real que navega).
  const renderItem = (item: NavItem, indent = false) => {
    const active =
      location.pathname.startsWith(item.path) &&
      (item.path !== '/dashboard' || location.pathname === '/dashboard');
    const button = (
      <ListItemButton
        onClick={() => navigate(item.path)}
        selected={active}
        sx={{
          borderRadius: 2,
          mb: 0.4,
          minHeight: 42,
          justifyContent: collapsed ? 'center' : 'flex-start',
          pl: collapsed ? 1 : (indent ? 2.2 : 1.5),
          pr: collapsed ? 1 : 1.5,
          color: active ? TXT_ON : TXT_OFF,
          bgcolor: active ? 'rgba(255,255,255,0.18) !important' : 'transparent',
          borderLeft: active ? '3px solid rgba(150,200,255,0.95)' : '3px solid transparent',
          '&:hover': { bgcolor: 'rgba(255,255,255,0.11)' },
          transition: 'all 0.15s ease',
        }}
      >
        <ListItemIcon sx={{
          color: active ? ICO_ON : ICO_OFF,
          minWidth: 0,
          mr: collapsed ? 0 : 1.5,
          justifyContent: 'center',
        }}>
          {item.icon}
        </ListItemIcon>
        {!collapsed && (
          <ListItemText
            primary={item.label}
            primaryTypographyProps={{ fontSize: '0.83rem', fontWeight: active ? 700 : 400 }}
          />
        )}
      </ListItemButton>
    );
    return collapsed
      ? <Tooltip key={item.path} title={item.label} placement="right" arrow>{button}</Tooltip>
      : <Box key={item.path}>{button}</Box>;
  };

  // Encabezado de sección — mismo estilo/tamaño que "Dashboard Ejecutivo", con +/−.
  const renderHeader = (title: string, si: number) => {
    const open = !!openSections[si];
    return (
      <ListItemButton
        onClick={() => toggleSection(si)}
        sx={{
          borderRadius: 2,
          mb: 0.4,
          mt: 0.4,
          minHeight: 42,
          pl: 1.5, pr: 1.5,
          color: TXT_OFF,
          '&:hover': { bgcolor: 'rgba(255,255,255,0.11)' },
          transition: 'all 0.15s ease',
        }}
      >
        <ListItemIcon sx={{ color: ICO_OFF, minWidth: 0, mr: 1.5, justifyContent: 'center' }}>
          {open ? <Remove /> : <Add />}
        </ListItemIcon>
        <ListItemText
          primary={title}
          primaryTypographyProps={{ fontSize: '0.83rem', fontWeight: 600 }}
        />
      </ListItemButton>
    );
  };

  return (
    <Drawer
      variant="permanent"
      sx={{
        width,
        flexShrink: 0,
        whiteSpace: 'nowrap',
        transition: 'width 0.2s ease',
        '& .MuiDrawer-paper': {
          width,
          boxSizing: 'border-box',
          background: SIDEBAR_BG,
          color: 'white',
          overflow: 'hidden auto',
          transition: 'width 0.2s ease',
          borderRight: 'none',
        },
      }}
    >
      {/* ── Área del logo ── */}
      <Box sx={{
        width: '100%',
        overflow: 'hidden',
        borderRadius: '0 0 16px 16px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.30)',
        lineHeight: 0,
        flexShrink: 0,
      }}>
        <img
          src={logoImg}
          alt="VISTA — Inteligencia Comercial"
          style={{ width: '100%', height: 'auto', display: 'block', objectFit: 'cover' }}
        />
      </Box>

      {/* ── Botón de colapso del sidebar completo ── */}
      <Box sx={{ display: 'flex', justifyContent: collapsed ? 'center' : 'flex-end', px: 1, py: 0.5 }}>
        <Tooltip title={collapsed ? 'Expandir menú' : 'Colapsar menú'} placement="right" arrow>
          <IconButton size="small" onClick={() => setCollapsed((c) => !c)}
                      aria-label={collapsed ? 'Expandir menú' : 'Colapsar menú'}
                      sx={{ color: 'rgba(255,255,255,0.8)' }}>
            {collapsed ? <ChevronRight /> : <ChevronLeft />}
          </IconButton>
        </Tooltip>
      </Box>

      <Divider sx={{ borderColor: DIV_COLOR, mx: 1.5, mb: 0.5 }} />

      {/* ── Navegación: secciones en acordeón (o iconos planos si está colapsado) ── */}
      <List dense component="div" sx={{ px: 1, pt: 0.5 }}>
        {NAV_SECTIONS.map((section, si) => {
          const items = section.items.filter(puedeVer);
          if (items.length === 0) return null;

          // Home (sin título): siempre visible, sin acordeón.
          if (section.title === null) {
            return <Box key={si}>{items.map((it) => renderItem(it))}</Box>;
          }

          // Colapsado (solo iconos): sin acordeón — divisor + iconos con tooltip.
          if (collapsed) {
            return (
              <Box key={si}>
                <Divider sx={{ borderColor: DIV_COLOR, my: 0.9, mx: 1 }} />
                {items.map((it) => renderItem(it))}
              </Box>
            );
          }

          // Expandido: encabezado (+/−) + items ocultos dentro de un Collapse.
          const open = !!openSections[si];
          return (
            <Box key={si}>
              {renderHeader(section.title, si)}
              <Collapse in={open} timeout="auto" unmountOnExit>
                <Box>{items.map((it) => renderItem(it, true))}</Box>
              </Collapse>
            </Box>
          );
        })}
      </List>
    </Drawer>
  );
}

export { DRAWER_WIDTH, DRAWER_WIDTH_COLLAPSED };
