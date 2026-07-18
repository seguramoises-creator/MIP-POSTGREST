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
  ChevronLeft, ChevronRight, Add, Remove, RateReview,
} from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { usePermisosStore } from '../../store/permisos.store';
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
  roles: Rol[];          // fallback mientras cargan los permisos (y para módulos fuera de la matriz)
  recurso?: string;      // recurso de la matriz RBAC; si existe, la visibilidad la decide /authz/me/permisos
  accion?: string;       // acción a evaluar sobre el recurso (default 'read')
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
      { label: 'Dashboard Ejecutivo', path: '/dashboard', icon: <Dashboard />, recurso: 'dashboard.ejecutivo', roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD'] },
    ],
  },
  {
    title: 'Operación diaria',
    items: [
      { label: 'Registrar Visita',    path: '/visita/registrar', icon: <EditNote />,      recurso: 'visita.registrar', roles: ['ADMIN', 'REPRESENTANTE_MEDICO'] },
      { label: 'Cobertura Visita',    path: '/visita/cobertura', icon: <TrackChanges />,  recurso: 'cobertura.diaria', roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
      { label: 'Ruptura / Cierre',    path: '/visita/ruptura',   icon: <ReportProblem />, recurso: 'cobertura.diaria', roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
      { label: 'Parrilla & Muestras', path: '/visita/parrilla',  icon: <Campaign />,      recurso: 'parrilla.consulta', roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
      { label: 'Coaching (MORE)',     path: '/coaching-more',    icon: <RateReview />,    recurso: 'coaching.hoja', roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
    ],
  },
  {
    title: 'Maestros y planeación',
    items: [
      { label: 'Panel Médico',          path: '/visita/panel-medico', icon: <MedicalServices />, recurso: 'medico.panel', roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
      { label: 'Médicos',               path: '/medicos',             icon: <LocalHospital />,   recurso: 'medico.panel', roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_MARCA', 'GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO', 'CONSULTA'] },
      { label: 'Planeación Ciclo',      path: '/visita/planeacion',   icon: <EventNote />,       recurso: 'planeacion.ciclo', roles: ['ADMIN', 'REPRESENTANTE_MEDICO'] },
    ],
  },
  {
    title: 'Desempeño y análisis',
    items: [
      { label: 'Indicadores Desempeño', path: '/coaching',             icon: <Leaderboard />,  recurso: 'coaching.kpi', roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO'] },
      { label: 'Productividad',         path: '/productividad',        icon: <TrendingUp />,   recurso: 'productividad.comercial', roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'REPRESENTANTE_MEDICO'] },
      { label: 'Ranking',               path: '/ranking',              icon: <SportsScore />,  recurso: 'ranking.rkt', roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'REPRESENTANTE_MEDICO', 'CONSULTA'] },
      { label: 'Reconocimiento',        path: '/reconocimiento',       icon: <EmojiEvents />,  roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'CONSULTA'] },
      { label: 'Matriz LSII',           path: '/lsii',                 icon: <ScatterPlot />,  roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'CONSULTA'] },
      { label: 'Cobertura Predictiva',  path: '/cobertura-predictiva', icon: <TrackChanges />, recurso: 'cobertura.predictiva', roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA'] },
      { label: 'Costo & ROI',           path: '/visita/costo-roi',     icon: <Paid />,         recurso: 'costoroi.ver', roles: ['ADMIN', 'GERENTE_DISTRITO', 'GERENTE_PRODUCTIVIDAD', 'REPRESENTANTE_MEDICO'] },
    ],
  },
  {
    title: 'Formación',
    items: [
      { label: 'Exámenes',          path: '/examenes',        icon: <Quiz />,               recurso: 'examen.configurar', accion: 'configure', roles: ['ADMIN', 'CAPACITACION'] },
      { label: 'Mis Exámenes',      path: '/mis-examenes',    icon: <AssignmentTurnedIn />, roles: ['GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'] },
      { label: 'Exámenes — Equipo', path: '/examenes-equipo', icon: <Groups />,             roles: ['GERENTE_DISTRITO'] },
    ],
  },
  {
    title: 'Datos',
    items: [
      { label: 'Carga Excel (ETL)', path: '/etl',      icon: <CloudUpload />, roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD'] },
      { label: 'Reportes',          path: '/reportes', icon: <Assessment />,  recurso: 'exportacion', accion: 'export', roles: ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD', 'CONSULTA'] },
    ],
  },
  {
    title: 'Sistema',
    items: [
      { label: 'Configuración',   path: '/admin',    icon: <Settings />,           roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD'] },
      { label: 'Administración',  path: '/usuarios', icon: <AdminPanelSettings />, recurso: 'config.usuarios', roles: ['ADMIN'] },
    ],
  },
];

// Lista plana (en el orden agrupado) — la usa App.tsx para resolver la ruta inicial por rol.
export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);

export default function Sidebar({ mobileOpen = false, onMobileClose }:
  { mobileOpen?: boolean; onMobileClose?: () => void } = {}) {
  const navigate = useNavigate();
  const location = useLocation();
  const { rol }  = useAuthStore();
  const puedePerm = usePermisosStore((s) => s.puede);
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

  // Visibilidad: si el ítem tiene `recurso`, la decide la matriz (/authz/me/permisos).
  // Mientras los permisos no cargan (puedePerm devuelve null) o si el ítem no está en la
  // matriz, se cae al gate por rol.
  const puedeVer = (item: NavItem) => {
    if (item.recurso) {
      const p = puedePerm(item.recurso, item.accion ?? 'read');
      if (p !== null) return p;
    }
    return !!rol && item.roles.includes(rol);
  };

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

  // Fila de navegación (item real que navega). `colap` = versión solo-iconos.
  const renderItem = (item: NavItem, colap: boolean, indent = false) => {
    const active =
      location.pathname.startsWith(item.path) &&
      (item.path !== '/dashboard' || location.pathname === '/dashboard');
    const button = (
      <ListItemButton
        onClick={() => { navigate(item.path); onMobileClose?.(); }}
        selected={active}
        sx={{
          borderRadius: 2,
          mb: 0.4,
          minHeight: 42,
          justifyContent: colap ? 'center' : 'flex-start',
          pl: colap ? 1 : (indent ? 2.2 : 1.5),
          pr: colap ? 1 : 1.5,
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
          mr: colap ? 0 : 1.5,
          justifyContent: 'center',
        }}>
          {item.icon}
        </ListItemIcon>
        {!colap && (
          <ListItemText
            primary={item.label}
            primaryTypographyProps={{ fontSize: '0.83rem', fontWeight: active ? 700 : 400 }}
          />
        )}
      </ListItemButton>
    );
    return colap
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

  // Cuerpo del menú, reutilizado por ambos drawers.
  //  `colap`       = versión solo-iconos (escritorio colapsado).
  //  `showCollapse`= muestra el botón de colapsar (solo en el drawer de escritorio).
  const body = (colap: boolean, showCollapse: boolean) => (
    <>
      {/* ── Área del logo ── */}
      <Box sx={{
        width: '100%', overflow: 'hidden', borderRadius: '0 0 16px 16px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.30)', lineHeight: 0, flexShrink: 0,
      }}>
        <img src={logoImg} alt="VISTA — Inteligencia Comercial"
             style={{ width: '100%', height: 'auto', display: 'block', objectFit: 'cover' }} />
      </Box>

      {/* ── Botón de colapso (solo escritorio) ── */}
      {showCollapse && (
        <Box sx={{ display: 'flex', justifyContent: colap ? 'center' : 'flex-end', px: 1, py: 0.5 }}>
          <Tooltip title={colap ? 'Expandir menú' : 'Colapsar menú'} placement="right" arrow>
            <IconButton size="small" onClick={() => setCollapsed((c) => !c)}
                        aria-label={colap ? 'Expandir menú' : 'Colapsar menú'}
                        sx={{ color: 'rgba(255,255,255,0.8)' }}>
              {colap ? <ChevronRight /> : <ChevronLeft />}
            </IconButton>
          </Tooltip>
        </Box>
      )}

      <Divider sx={{ borderColor: DIV_COLOR, mx: 1.5, mb: 0.5 }} />

      {/* ── Navegación ── */}
      <List dense component="div" sx={{ px: 1, pt: 0.5 }}>
        {NAV_SECTIONS.map((section, si) => {
          const items = section.items.filter(puedeVer);
          if (items.length === 0) return null;
          if (section.title === null) {
            return <Box key={si}>{items.map((it) => renderItem(it, colap))}</Box>;
          }
          if (colap) {
            return (
              <Box key={si}>
                <Divider sx={{ borderColor: DIV_COLOR, my: 0.9, mx: 1 }} />
                {items.map((it) => renderItem(it, colap))}
              </Box>
            );
          }
          const open = !!openSections[si];
          return (
            <Box key={si}>
              {renderHeader(section.title, si)}
              <Collapse in={open} timeout="auto" unmountOnExit>
                <Box>{items.map((it) => renderItem(it, colap, true))}</Box>
              </Collapse>
            </Box>
          );
        })}
      </List>
    </>
  );

  const paperSx = {
    boxSizing: 'border-box', background: SIDEBAR_BG, color: 'white',
    overflow: 'hidden auto', borderRight: 'none',
  } as const;

  return (
    <>
      {/* ESCRITORIO (md+): drawer permanente y colapsable. */}
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', md: 'block' },
          width, flexShrink: 0, whiteSpace: 'nowrap', transition: 'width 0.2s ease',
          '& .MuiDrawer-paper': { ...paperSx, width, transition: 'width 0.2s ease' },
        }}
      >
        {body(collapsed, true)}
      </Drawer>

      {/* MÓVIL/TABLET (< md): drawer temporal en overlay — como app nativa.
          Oculto por defecto; se abre con el botón ☰ del AppBar y se cierra al navegar. */}
      {/* Montaje CONDICIONAL: el Drawer temporal solo existe en el árbol cuando el menú
          está abierto. Al cerrar (mobileOpen=false), React DESMONTA el Drawer y su portal
          (backdrop incluido) directamente — sin depender de la transición de salida de
          MUI, que en Safari iOS no disparaba `onExited` y dejaba el backdrop atascado
          visible tapando la pantalla (el velo gris = congelamiento). `mobileOpen` solo se
          pone true desde el botón ☰, que únicamente existe en móvil, así que esto nunca
          se monta en escritorio. */}
      {mobileOpen && (
        <Drawer
          variant="temporary"
          open
          onClose={onMobileClose}
          sx={{ '& .MuiDrawer-paper': { ...paperSx, width: DRAWER_WIDTH } }}
        >
          {body(false, false)}
        </Drawer>
      )}
    </>
  );
}

export { DRAWER_WIDTH, DRAWER_WIDTH_COLLAPSED };
