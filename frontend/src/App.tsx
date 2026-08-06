import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useEffect, useState, Suspense } from 'react';
import axios from 'axios';
import { lazyWithReload, ErrorBoundary } from './components/common/resilience';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme, CssBaseline, Box, Typography } from '@mui/material';
import { useAuthStore } from './store/auth.store';
import ProtectedRoute from './components/common/ProtectedRoute';
import MainLayout from './components/layout/MainLayout';
import Login from './pages/auth/Login';
import CambiarPassword from './pages/auth/CambiarPassword';
import ActivarCuenta from './pages/auth/ActivarCuenta';
import Setup from './pages/setup/Setup';
const DashboardEjecutivo = lazyWithReload(() => import('./pages/dashboard/DashboardEjecutivo'));
import { NAV_ITEMS } from './components/layout/Sidebar';
import { Rol } from './types';

// Página de inicio según el rol = primer ítem del menú al que tiene acceso.
// Evita aterrizar a roles sin dashboard (Asesor de Capacitación, RM, etc.) en el
// Dashboard Ejecutivo, que les daría error de "sin datos / sin acceso".
function rutaInicial(rol: Rol | null): string {
  if (!rol) return '/login';
  const item = NAV_ITEMS.find((i) => i.roles.includes(rol));
  return item ? item.path : '/sin-acceso';
}
// Páginas cargadas bajo demanda (code-splitting): cada ruta baja su propio chunk
// al abrirla, aligerando la carga inicial de la app.
const Productividad = lazyWithReload(() => import('./pages/productividad/Productividad'));
const CoberturaPredictiva = lazyWithReload(() => import('./pages/cobertura-predictiva/CoberturaPredictiva'));
const Coaching = lazyWithReload(() => import('./pages/coaching/Coaching'));
const CoachingMore = lazyWithReload(() => import('./pages/coaching-more/CoachingMore'));
const Categorizacion = lazyWithReload(() => import('./pages/categorizacion/Categorizacion'));
const Medicos = lazyWithReload(() => import('./pages/medicos/Medicos'));
const Ranking = lazyWithReload(() => import('./pages/ranking/Ranking'));
const Reconocimiento = lazyWithReload(() => import('./pages/reconocimiento/Reconocimiento'));
const ETL = lazyWithReload(() => import('./pages/etl/ETL'));
const Admin = lazyWithReload(() => import('./pages/admin/Admin'));
const Administracion = lazyWithReload(() => import('./pages/admin/Administracion'));
const Reportes = lazyWithReload(() => import('./pages/reportes/Reportes'));
const Lsii = lazyWithReload(() => import('./pages/lsii/Lsii'));
const Examenes = lazyWithReload(() => import('./pages/examenes/Examenes'));
const MisExamenes = lazyWithReload(() => import('./pages/examenes/MisExamenes'));
const EquipoExamenes = lazyWithReload(() => import('./pages/examenes/EquipoExamenes'));
const PanelMedico = lazyWithReload(() => import('./pages/visita/PanelMedico'));
const PanelFarmacia = lazyWithReload(() => import('./pages/visita/PanelFarmacia'));
const MaestroFarmacias = lazyWithReload(() => import('./pages/admin/MaestroFarmacias'));
const CoberturaDashboard = lazyWithReload(() => import('./pages/visita/CoberturaDashboard'));
const RegistrarVisita = lazyWithReload(() => import('./pages/visita/RegistrarVisita'));
const PlaneacionVisita = lazyWithReload(() => import('./pages/visita/PlaneacionVisita'));
const RupturaVisita = lazyWithReload(() => import('./pages/visita/RupturaVisita'));
const ParrillaVisita = lazyWithReload(() => import('./pages/visita/ParrillaVisita'));
const CostoRoiVisita = lazyWithReload(() => import('./pages/visita/CostoRoiVisita'));
const PlanBrechas = lazyWithReload(() => import('./pages/formacion/PlanBrechas'));
const CalendarioCoaching = lazyWithReload(() => import('./pages/formacion/CalendarioCoaching'));
const Simulacro = lazyWithReload(() => import('./pages/formacion/Simulacro'));

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 120000, retry: 1 } } });

const theme = createTheme({
  palette: { primary: { main: '#1a237e' }, secondary: { main: '#0d47a1' }, background: { default: '#f5f6fa' } },
  typography: { fontFamily: '"Inter","Roboto","Helvetica","Arial",sans-serif' },
  shape: { borderRadius: 8 },
  components: {
    // Congelamiento en móvil (Safari iOS / Android): el scroll-lock de los overlays
    // de MUI pone el <body> en position:fixed + backdrop y en Safari iOS a veces NO
    // se revierte al cerrar; tras abrir varios Select/menús (los filtros) el body
    // queda bloqueado con el velo gris encima = pantalla congelada. `disableScrollLock`
    // evita esa manipulación del body en TODOS los overlays. Tradeoff: el fondo puede
    // desplazarse con un menú abierto — aceptable frente al congelamiento.
    MuiModal: { defaultProps: { disableScrollLock: true } },
    MuiPopover: { defaultProps: { disableScrollLock: true } },
    MuiMenu: { defaultProps: { disableScrollLock: true } },
    MuiDialog: { defaultProps: { disableScrollLock: true } },
    MuiDrawer: { defaultProps: { disableScrollLock: true } },
    // Elegancia: las tarjetas "outlined" llevan un borde azul oscuro y una
    // sombra sutil del mismo tono, consistente en toda la app.
    MuiCard: {
      styleOverrides: {
        root: ({ ownerState }: { ownerState: { variant?: string } }) =>
          ownerState.variant === 'outlined'
            ? {
                borderColor: 'rgba(26,35,126,0.45)',
                borderWidth: 1.5,
                boxShadow: '0 2px 10px rgba(26,35,126,0.06)',
                transition: 'box-shadow .2s ease, border-color .2s ease',
                '&:hover': { borderColor: '#1a237e', boxShadow: '0 4px 16px rgba(26,35,126,0.12)' },
              }
            : {},
      },
    },
  },
});

function SinAcceso() {
  return (
    <Box sx={{ textAlign: 'center', mt: 10 }}>
      <Typography variant="h4" color="error">Acceso Denegado</Typography>
      <Typography color="text.secondary" mt={1}>No tienes permisos para ver esta sección.</Typography>
    </Box>
  );
}

function AppRoutes() {
  const { isAuthenticated, rol } = useAuthStore();
  const inicio = rutaInicial(rol);
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const API = (import.meta as any).env?.VITE_API_URL || '/api/v1';
    axios.get(`${API}/setup/status`)
      .then(r => { if (r.data.setup_required) navigate('/setup', { replace: true }); })
      .catch(() => {/* ignorar si el endpoint no responde */})
      .finally(() => setChecking(false));
  }, []);

  if (checking) return null;

  return (
    <ErrorBoundary>
    <Suspense fallback={<Box sx={{ p: 6, textAlign: 'center' }}><Typography color="text.secondary">Cargando…</Typography></Box>}>
    <Routes>
      <Route path="/setup" element={<Setup />} />
      <Route path="/login" element={isAuthenticated ? <Navigate to={inicio} /> : <Login />} />
      <Route path="/cambiar-password" element={isAuthenticated ? <CambiarPassword /> : <Navigate to="/login" />} />
      {/* Activación de cuenta: ruta PÚBLICA y sin condicionar a isAuthenticated — quien
          llega desde el correo aún no tiene contraseña, así que jamás está autenticado.
          Va antes del catch-all para que el enlace no rebote al dashboard. */}
      <Route path="/activar/:token" element={<ActivarCuenta />} />
      <Route path="/sin-acceso" element={<SinAcceso />} />
      <Route path="/" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
        <Route index element={<Navigate to={inicio} />} />
        {/* RBAC Fase 2: las rutas mapeadas gatean por la matriz (recurso=...), con fallback por rol.
            Solo /admin (megapantalla de catálogos = administración de sistema) queda por rol. */}
        <Route path="dashboard" element={<ProtectedRoute recurso="dashboard.ejecutivo" allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD']}><DashboardEjecutivo /></ProtectedRoute>} />
        <Route path="productividad" element={<ProtectedRoute recurso="productividad.comercial"><Productividad /></ProtectedRoute>} />
        <Route path="cobertura-predictiva" element={<ProtectedRoute recurso="cobertura.predictiva"><CoberturaPredictiva /></ProtectedRoute>} />
        <Route path="coaching" element={<ProtectedRoute recurso="coaching.kpi" allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO']}><Coaching /></ProtectedRoute>} />
        <Route path="coaching-more" element={<ProtectedRoute recurso="coaching.hoja" allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO','REPRESENTANTE_MEDICO']}><CoachingMore /></ProtectedRoute>} />
        {/* jul-2026: estas 2 rutas usan el MISMO recurso que gobierna su API (`categorizacion.py`
            y `maestro_medicos.py`, ahora en la matriz). Antes miraban `categorizacion.basica` /
            `medico.panel` —filas del spec que consumen otros módulos—, así que la pantalla podía
            negarse a un rol al que la API sí respondía: GERENTE_PRODUCTIVIDAD importaba y daba de
            alta médicos sin poder abrir el maestro. Alineado, lo que el cliente edite en Roles y
            Permisos se refleja también en la navegación. OJO: `/visita/panel-medico` es otra
            pantalla y sigue con `medico.panel`, que es su recurso correcto. */}
        <Route path="categorizacion" element={<ProtectedRoute recurso="categorizacion.operacion" allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD','GERENTE_MARCA','GERENTE_DISTRITO','REPRESENTANTE_MEDICO','CONSULTA']}><Categorizacion /></ProtectedRoute>} />
        <Route path="medicos" element={<ProtectedRoute recurso="medico.maestro" allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD','GERENTE_MARCA','GERENTE_DISTRITO','REPRESENTANTE_MEDICO','CONSULTA']}><Medicos /></ProtectedRoute>} />
        <Route path="ranking" element={<ProtectedRoute recurso="ranking.rkt"><Ranking /></ProtectedRoute>} />
        <Route path="reconocimiento" element={<ProtectedRoute recurso="reconocimiento"><Reconocimiento /></ProtectedRoute>} />
        <Route path="lsii" element={<ProtectedRoute recurso="lsii.evaluar" allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO','GERENTE_MARCA','CONSULTA']}><Lsii /></ProtectedRoute>} />
        <Route path="mis-examenes" element={<ProtectedRoute allowedRoles={['GERENTE_DISTRITO','REPRESENTANTE_MEDICO']}><MisExamenes /></ProtectedRoute>} />
        {/* Gestión de exámenes (crear/asignar/consolidar): SOLO ADMIN y el coordinador de
            Capacitación. Coincide con el backend (RequireCapacitacion = ADMIN + CAPACITACION);
            un GD/Gerente de Productividad recibía 403 y solo veía errores. */}
        <Route path="examenes" element={<ProtectedRoute recurso="examen.configurar" accion="configure" allowedRoles={['ADMIN','CAPACITACION']}><Examenes /></ProtectedRoute>} />
        <Route path="examenes-equipo" element={<ProtectedRoute allowedRoles={['GERENTE_DISTRITO']}><EquipoExamenes /></ProtectedRoute>} />
        <Route path="visita/panel-medico" element={<ProtectedRoute recurso="medico.panel" allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><PanelMedico /></ProtectedRoute>} />
        <Route path="visita/panel-farmacia" element={<ProtectedRoute recurso="farmacia.panel" allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><PanelFarmacia /></ProtectedRoute>} />
        <Route path="farmacias/maestro" element={<ProtectedRoute recurso="farmacia.maestro" accion="configure" allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD']}><MaestroFarmacias /></ProtectedRoute>} />
        <Route path="visita/cobertura" element={<ProtectedRoute recurso="cobertura.diaria" allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><CoberturaDashboard /></ProtectedRoute>} />
        <Route path="visita/registrar" element={<ProtectedRoute recurso="visita.registrar" accion="register" allowedRoles={['ADMIN','REPRESENTANTE_MEDICO']}><RegistrarVisita /></ProtectedRoute>} />
        <Route path="visita/planeacion" element={<ProtectedRoute recurso="planeacion.ciclo" allowedRoles={['ADMIN','REPRESENTANTE_MEDICO']}><PlaneacionVisita /></ProtectedRoute>} />
        <Route path="visita/ruptura" element={<ProtectedRoute recurso="cobertura.diaria" allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><RupturaVisita /></ProtectedRoute>} />
        <Route path="visita/parrilla" element={<ProtectedRoute recurso="parrilla.consulta" allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><ParrillaVisita /></ProtectedRoute>} />
        <Route path="visita/costo-roi" element={<ProtectedRoute recurso="costoroi.ver" allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><CostoRoiVisita /></ProtectedRoute>} />
        <Route path="etl" element={<ProtectedRoute recurso="etl.cargar"><ETL /></ProtectedRoute>} />
        <Route path="admin" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD']}><Admin /></ProtectedRoute>} />
        <Route path="usuarios" element={<ProtectedRoute recurso="config.usuarios" allowedRoles={['ADMIN']}><Administracion /></ProtectedRoute>} />
        <Route path="reportes" element={<ProtectedRoute recurso="exportacion" accion="export" allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD','CONSULTA']}><Reportes /></ProtectedRoute>} />
        {/* Plan de Cierre de Brechas (Formación §12). Sin `recurso`: el router backend gatea
            por rol (require_roles), no por la matriz RBAC — un recurso inexistente denegaría a todos. */}
        <Route path="formacion/brechas" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','CAPACITACION','PRESIDENCIA','GERENTE_MEDICO']}><PlanBrechas /></ProtectedRoute>} />
        {/* Calendario de Coaching (Formación §7). Sin `recurso`: el router backend gatea
            por rol (require_roles), no por la matriz RBAC — un recurso inexistente denegaría a todos. */}
        <Route path="formacion/calendario" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO','PRESIDENCIA','GERENTE_MEDICO','CAPACITACION']}><CalendarioCoaching /></ProtectedRoute>} />
        {/* Simulacro de Venta con IA (Formación §9). Sin `recurso`: el router backend gatea
            por rol (require_roles), no por la matriz RBAC — un recurso inexistente denegaría a todos. */}
        <Route path="formacion/simulacro" element={<ProtectedRoute allowedRoles={['ADMIN','REPRESENTANTE_MEDICO','GERENTE_PRODUCTIVIDAD','CAPACITACION','GERENTE_DISTRITO','PRESIDENCIA','GERENTE_MEDICO']}><Simulacro /></ProtectedRoute>} />
      </Route>
      <Route path="*" element={<Navigate to={inicio} />} />
    </Routes>
    </Suspense>
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
