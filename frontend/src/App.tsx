import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useEffect, useState, lazy, Suspense } from 'react';
import axios from 'axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme, CssBaseline, Box, Typography } from '@mui/material';
import { useAuthStore } from './store/auth.store';
import ProtectedRoute from './components/common/ProtectedRoute';
import MainLayout from './components/layout/MainLayout';
import Login from './pages/auth/Login';
import CambiarPassword from './pages/auth/CambiarPassword';
import Setup from './pages/setup/Setup';
const DashboardEjecutivo = lazy(() => import('./pages/dashboard/DashboardEjecutivo'));
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
const Productividad = lazy(() => import('./pages/productividad/Productividad'));
const CoberturaPredictiva = lazy(() => import('./pages/cobertura-predictiva/CoberturaPredictiva'));
const Coaching = lazy(() => import('./pages/coaching/Coaching'));
const CoachingMore = lazy(() => import('./pages/coaching-more/CoachingMore'));
const Categorizacion = lazy(() => import('./pages/categorizacion/Categorizacion'));
const Ranking = lazy(() => import('./pages/ranking/Ranking'));
const Reconocimiento = lazy(() => import('./pages/reconocimiento/Reconocimiento'));
const ETL = lazy(() => import('./pages/etl/ETL'));
const Admin = lazy(() => import('./pages/admin/Admin'));
const Administracion = lazy(() => import('./pages/admin/Administracion'));
const Reportes = lazy(() => import('./pages/reportes/Reportes'));
const Lsii = lazy(() => import('./pages/lsii/Lsii'));
const Examenes = lazy(() => import('./pages/examenes/Examenes'));
const MisExamenes = lazy(() => import('./pages/examenes/MisExamenes'));
const EquipoExamenes = lazy(() => import('./pages/examenes/EquipoExamenes'));
const PanelMedico = lazy(() => import('./pages/visita/PanelMedico'));
const CoberturaDashboard = lazy(() => import('./pages/visita/CoberturaDashboard'));
const RegistrarVisita = lazy(() => import('./pages/visita/RegistrarVisita'));
const PlaneacionVisita = lazy(() => import('./pages/visita/PlaneacionVisita'));
const RupturaVisita = lazy(() => import('./pages/visita/RupturaVisita'));
const ParrillaVisita = lazy(() => import('./pages/visita/ParrillaVisita'));
const CostoRoiVisita = lazy(() => import('./pages/visita/CostoRoiVisita'));

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 120000, retry: 1 } } });

const theme = createTheme({
  palette: { primary: { main: '#1a237e' }, secondary: { main: '#0d47a1' }, background: { default: '#f5f6fa' } },
  typography: { fontFamily: '"Inter","Roboto","Helvetica","Arial",sans-serif' },
  shape: { borderRadius: 8 },
  components: {
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
    <Suspense fallback={<Box sx={{ p: 6, textAlign: 'center' }}><Typography color="text.secondary">Cargando…</Typography></Box>}>
    <Routes>
      <Route path="/setup" element={<Setup />} />
      <Route path="/login" element={isAuthenticated ? <Navigate to={inicio} /> : <Login />} />
      <Route path="/cambiar-password" element={isAuthenticated ? <CambiarPassword /> : <Navigate to="/login" />} />
      <Route path="/sin-acceso" element={<SinAcceso />} />
      <Route path="/" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
        <Route index element={<Navigate to={inicio} />} />
        <Route path="dashboard" element={<ProtectedRoute allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD']}><DashboardEjecutivo /></ProtectedRoute>} />
        <Route path="productividad" element={<Productividad />} />
        <Route path="cobertura-predictiva" element={<CoberturaPredictiva />} />
        <Route path="coaching" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO']}><Coaching /></ProtectedRoute>} />
        <Route path="coaching-more" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO','REPRESENTANTE_MEDICO']}><CoachingMore /></ProtectedRoute>} />
        <Route path="categorizacion" element={<ProtectedRoute allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD','GERENTE_MARCA','GERENTE_DISTRITO','REPRESENTANTE_MEDICO','CONSULTA']}><Categorizacion /></ProtectedRoute>} />
        <Route path="ranking" element={<Ranking />} />
        <Route path="reconocimiento" element={<Reconocimiento />} />
        <Route path="lsii" element={<ProtectedRoute allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO','GERENTE_MARCA','CONSULTA']}><Lsii /></ProtectedRoute>} />
        <Route path="mis-examenes" element={<ProtectedRoute allowedRoles={['GERENTE_DISTRITO','REPRESENTANTE_MEDICO']}><MisExamenes /></ProtectedRoute>} />
        <Route path="examenes" element={<ProtectedRoute allowedRoles={['ADMIN','CAPACITACION','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO']}><Examenes /></ProtectedRoute>} />
        <Route path="examenes-equipo" element={<ProtectedRoute allowedRoles={['GERENTE_DISTRITO']}><EquipoExamenes /></ProtectedRoute>} />
        <Route path="visita/panel-medico" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><PanelMedico /></ProtectedRoute>} />
        <Route path="visita/cobertura" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><CoberturaDashboard /></ProtectedRoute>} />
        <Route path="visita/registrar" element={<ProtectedRoute allowedRoles={['ADMIN','REPRESENTANTE_MEDICO']}><RegistrarVisita /></ProtectedRoute>} />
        <Route path="visita/planeacion" element={<ProtectedRoute allowedRoles={['ADMIN','REPRESENTANTE_MEDICO']}><PlaneacionVisita /></ProtectedRoute>} />
        <Route path="visita/ruptura" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><RupturaVisita /></ProtectedRoute>} />
        <Route path="visita/parrilla" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><ParrillaVisita /></ProtectedRoute>} />
        <Route path="visita/costo-roi" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_DISTRITO','GERENTE_PRODUCTIVIDAD','REPRESENTANTE_MEDICO']}><CostoRoiVisita /></ProtectedRoute>} />
        <Route path="etl" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD']}><ETL /></ProtectedRoute>} />
        <Route path="admin" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD']}><Admin /></ProtectedRoute>} />
        <Route path="usuarios" element={<ProtectedRoute allowedRoles={['ADMIN']}><Administracion /></ProtectedRoute>} />
        <Route path="reportes" element={<Reportes />} />
      </Route>
      <Route path="*" element={<Navigate to={inicio} />} />
    </Routes>
    </Suspense>
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
