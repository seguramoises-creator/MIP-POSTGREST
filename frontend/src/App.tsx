import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import axios from 'axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider, createTheme, CssBaseline, Box, Typography } from '@mui/material';
import { useAuthStore } from './store/auth.store';
import ProtectedRoute from './components/common/ProtectedRoute';
import MainLayout from './components/layout/MainLayout';
import Login from './pages/auth/Login';
import Setup from './pages/setup/Setup';
import DashboardEjecutivo from './pages/dashboard/DashboardEjecutivo';
import Productividad from './pages/productividad/Productividad';
import CoberturaPredictiva from './pages/cobertura-predictiva/CoberturaPredictiva';
import Coaching from './pages/coaching/Coaching';
import Categorizacion from './pages/categorizacion/Categorizacion';
import Ranking from './pages/ranking/Ranking';
import Reconocimiento from './pages/reconocimiento/Reconocimiento';
import ETL from './pages/etl/ETL';
import Admin from './pages/admin/Admin';
import Usuarios from './pages/admin/Usuarios';
import Reportes from './pages/reportes/Reportes';
import Lsii from './pages/lsii/Lsii';
import Examenes from './pages/examenes/Examenes';
import MisExamenes from './pages/examenes/MisExamenes';
import EquipoExamenes from './pages/examenes/EquipoExamenes';

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 120000, retry: 1 } } });

const theme = createTheme({
  palette: { primary: { main: '#1a237e' }, secondary: { main: '#0d47a1' }, background: { default: '#f5f6fa' } },
  typography: { fontFamily: '"Inter","Roboto","Helvetica","Arial",sans-serif' },
  shape: { borderRadius: 8 },
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
  const { isAuthenticated } = useAuthStore();
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
    <Routes>
      <Route path="/setup" element={<Setup />} />
      <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" /> : <Login />} />
      <Route path="/sin-acceso" element={<SinAcceso />} />
      <Route path="/" element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
        <Route index element={<Navigate to="/dashboard" />} />
        <Route path="dashboard" element={<DashboardEjecutivo />} />
        <Route path="productividad" element={<Productividad />} />
        <Route path="cobertura-predictiva" element={<CoberturaPredictiva />} />
        <Route path="coaching" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO']}><Coaching /></ProtectedRoute>} />
        <Route path="categorizacion" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO','CONSULTA']}><Categorizacion /></ProtectedRoute>} />
        <Route path="ranking" element={<Ranking />} />
        <Route path="reconocimiento" element={<Reconocimiento />} />
        <Route path="lsii" element={<ProtectedRoute allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO','GERENTE_MARCA','CONSULTA']}><Lsii /></ProtectedRoute>} />
        <Route path="mis-examenes" element={<MisExamenes />} />
        <Route path="examenes" element={<ProtectedRoute allowedRoles={['ADMIN','CAPACITACION','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO']}><Examenes /></ProtectedRoute>} />
        <Route path="examenes-equipo" element={<ProtectedRoute allowedRoles={['ADMIN','CAPACITACION','GERENTE_DISTRITO']}><EquipoExamenes /></ProtectedRoute>} />
        <Route path="etl" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD']}><ETL /></ProtectedRoute>} />
        <Route path="admin" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD']}><Admin /></ProtectedRoute>} />
        <Route path="usuarios" element={<ProtectedRoute allowedRoles={['ADMIN']}><Usuarios /></ProtectedRoute>} />
        <Route path="reportes" element={<Reportes />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" />} />
    </Routes>
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
