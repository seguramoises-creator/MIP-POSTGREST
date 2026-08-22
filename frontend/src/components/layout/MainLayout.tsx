import { Outlet, useNavigate, useLocation, Navigate } from 'react-router-dom';
import {
  Box, AppBar, Toolbar, Typography,
  Avatar, Divider, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, Button, Alert, Stack,
  Drawer, List, ListItemButton, ListItemIcon, ListItemText,
} from '@mui/material';
import { Logout, LockReset, SupervisorAccount, InstallMobile } from '@mui/icons-material';
import { useState, useEffect, useMemo } from 'react';
import BottomNav from './BottomNav';
import TopTabs from './TopTabs';
import { useNavSecciones } from './useNavSecciones';
import { APP_FONDO, BOTTOM_NAV_H, NAV_ACTIVO, navTaupe, navFondo, TEXTO_TENUE } from './navTokens';
import InstalarAppDialog from '../InstalarAppDialog';
import AvisoErrorGlobal from '../AvisoErrorGlobal';
import { useAuthStore } from '../../store/auth.store';
import { usePermisosStore } from '../../store/permisos.store';
import { authService } from '../../services/auth.service';
import { api } from '../../services/api';
import { miGerente, type MiGerente } from '../../services/visita.service';
import CicloPaisBadge from '../CicloPaisBadge';
import CicloPaisHeader from '../CicloPaisHeader';
import { useCicloStore } from '../../store/ciclo.store';
import { marcaViva } from '../../theme/marcaViva';

export default function MainLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // Franja global País+Ciclo: se oculta donde es redundante — en /visita/registrar
  // (el registro siempre va al ciclo abierto) y en las páginas que ya traen sus
  // propios selectores de País/Ciclo o no dependen del ciclo (dashboard, LSII, los
  // módulos de análisis, ETL/Reportes con filtros propios, y Admin/Usuarios).
  // La píldora de la barra superior (CicloPaisBadge) ya informa país + ciclo abierto: la
  // franja solo se justifica donde de verdad haga falta CAMBIAR el ciclo en consulta.
  const HEADER_OCULTO = [
    '/visita/registrar', '/dashboard', '/lsii',
    '/coaching', '/productividad', '/ranking', '/reconocimiento', '/cobertura-predictiva',
    '/etl', '/reportes', '/usuarios', '/admin',
    // Médicos: la categorización NO depende del ciclo (la categoría del médico es estable
    // entre ciclos, jul-2026), así que la franja no afectaba nada de lo que se ve ahí.
    // Farmacias: mismo caso — el maestro es un catálogo país-level (Config.DIM_Farmacia)
    // sin dependencia del ciclo; la franja duplicaba la píldora País+Ciclo de arriba.
    '/medicos', '/categorizacion', '/farmacias/maestro',
    // Parrilla y Costo/ROI ya traen su PROPIO selector de ciclo: la franja los duplicaba.
    '/visita/parrilla', '/visita/costo-roi',
    // No leen el ciclo en absoluto: la franja solo sugeria que influia en algo.
    '/visita/panel-medico', '/visita/panel-farmacia', '/mis-examenes', '/examenes-equipo',
    // Solo usaban el ciclo para derivar `esSoloLectura` y apagar el boton de guardar. Sin
    // franja no hay forma de elegir un ciclo pasado, asi que siempre se trabaja sobre el
    // ABIERTO — que es la regla. El candado real no se pierde: el backend sigue rechazando
    // con 409 cualquier escritura sobre un ciclo cerrado (recalculo_service).
    '/visita/planeacion', '/visita/ruptura',
  ];
  // Se conserva SOLO donde cambiar el ciclo cambia lo que se ve o lo que se crea:
  //   /visita/cobertura → el panel Salud del Ciclo consulta el ciclo elegido.
  //   /examenes         → define a que ciclo va el examen que se crea.
  const headerEnLayout = !HEADER_OCULTO.includes(pathname);
  const { nombreCompleto, accessToken, rol, logout } = useAuthStore();
  const cicloAbierto = useCicloStore((s) => s.cicloAbierto);
  const debeCambiarPassword = useAuthStore((s) => s.debeCambiarPassword);
  const passwordMotivo = useAuthStore((s) => s.passwordMotivo);
  const passwordExpiraEnDias = useAuthStore((s) => s.passwordExpiraEnDias);
  const [perfilOpen, setPerfilOpen] = useState(false);   // hoja de Perfil (última ranura)
  const [gd, setGd] = useState<MiGerente | null>(null);
  const [instalarOpen, setInstalarOpen] = useState(false); // modal "Instalar app" (PWA)

  // Sección activa = la que contiene la ruta actual. De ella salen las pestañas
  // de arriba y la ranura resaltada abajo, así que se calcula UNA vez aquí.
  const secciones = useNavSecciones();
  const seccionActiva = useMemo(
    () => secciones.find((s) => s.items.some((i) => pathname.startsWith(i.path))),
    [secciones, pathname]);

  // RBAC Fase 2: carga las capacidades del usuario (/authz/me/permisos) una vez, al entrar
  // al layout autenticado. La navegación y las rutas derivan de aquí (con fallback por rol).
  const cargarPermisos = usePermisosStore((s) => s.cargar);
  useEffect(() => { if (accessToken) cargarPermisos(); }, [accessToken, cargarPermisos]);

  // Red de seguridad: cerrar la hoja de Perfil en CADA cambio de ruta. Evita que
  // el Drawer (o su backdrop) quede abierto/atascado tras navegar — causa del velo gris
  // congelado en Safari iOS.
  useEffect(() => { setPerfilOpen(false); }, [pathname]);

  // El representante ve su Gerente de Distrito de la línea arriba a la derecha.
  useEffect(() => {
    if (rol === 'REPRESENTANTE_MEDICO') miGerente().then(setGd).catch(() => setGd(null));
    else setGd(null);
  }, [rol]);

  const [pwOpen, setPwOpen] = useState(false);
  const [pwActual, setPwActual] = useState('');
  const [pwNueva, setPwNueva] = useState('');
  const [pwConfirmar, setPwConfirmar] = useState('');
  const [pwMsg, setPwMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [pwSaving, setPwSaving] = useState(false);
  const pwCoincide = pwNueva.length > 0 && pwNueva === pwConfirmar;

  const resetPermisos = usePermisosStore((s) => s.reset);
  const handleLogout = async () => {
    await authService.logout(accessToken || '');
    resetPermisos();
    logout();
    navigate('/login');
  };

  const abrirCambioPassword = () => { setPerfilOpen(false); setPwMsg(null); setPwActual(''); setPwNueva(''); setPwConfirmar(''); setPwOpen(true); };

  const handleCambiarPassword = async () => {
    if (!pwCoincide) { setPwMsg({ tipo: 'error', texto: 'La nueva contraseña y su confirmación no coinciden.' }); return; }
    setPwSaving(true); setPwMsg(null);
    try {
      await api.post('/auth/change-password', { password_actual: pwActual, password_nuevo: pwNueva });
      setPwMsg({ tipo: 'success', texto: 'Contraseña actualizada correctamente.' });
      setPwActual(''); setPwNueva(''); setPwConfirmar('');
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
      <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <AppBar
          position="sticky"
          elevation={0}
          sx={{
            background: navFondo(),
            borderBottom: 'none',
            color: NAV_ACTIVO,
          }}
        >
          {/* Cabecera reducida a lo que informa: dónde estoy y sobre qué ciclo/país
              trabajo. La cuenta y la salida bajaron a la ranura Perfil. */}
          <Toolbar variant="dense" sx={{ gap: 1, minHeight: { xs: 56, sm: 72 }, alignItems: 'center', px: { xs: 1, sm: 2 } }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, minWidth: 0 }}>
              {/* El logo vivía en el menú lateral y se fue con él al rediseñar la
                  navegación. Vuelve aquí, que es donde se ve en todas las pantallas.

                  64px: el vectorial de Mallén reserva casi la mitad de su alto al aire
                  sobre la abeja, así que la marca ocupa bastante menos que su caja y los
                  tamaños intermedios seguían leyéndose pequeños. Al quitar el título de
                  sección, el logo pasa a ser el único elemento de la izquierda y puede
                  ocupar ese espacio sin apretar nada. */}
              <Box component="img" src={marcaViva.logo.logoBlanco} alt={marcaViva.logo.nombre}
                   sx={{ height: { xs: 44, sm: 60 }, width: 'auto', display: 'block', flexShrink: 0,
                         // Sin márgenes negativos: la versión anterior hacía que el logo
                         // desbordara hacia la fila de pestañas, y en las secciones de un
                         // solo ítem esa fila NO se renderiza — el logo quedaba cortado por
                         // el área de contenido. Ahora cabe entero en la barra. */}
                          }} />
            </Box>
            <TopTabs items={seccionActiva?.items ?? []} seccion={seccionActiva?.titulo ?? 'Inicio'} />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0 }}>
              {gd?.gerente && (
                <Chip
                  size="small"
                  variant="outlined"
                  icon={<SupervisorAccount sx={{ color: `${NAV_ACTIVO} !important` }} />}
                  label={gd.gerente}
                  sx={{
                    fontWeight: 600, display: { xs: 'none', md: 'inline-flex' },
                    color: NAV_ACTIVO, borderColor: 'rgba(255,255,255,0.45)',
                  }}
                />
              )}
              <CicloPaisBadge />
            </Box>
          </Toolbar>
        </AppBar>

        {/* Perfil — recoge lo que antes colgaba del avatar de arriba a la derecha. */}
        <Drawer
          anchor="bottom"
          open={perfilOpen}
          onClose={() => setPerfilOpen(false)}
          PaperProps={{ sx: { borderTopLeftRadius: 16, borderTopRightRadius: 16, pb: 'env(safe-area-inset-bottom, 0px)' } }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 2, pt: 2, pb: 1.5 }}>
            <Avatar sx={{ width: 44, height: 44, bgcolor: navTaupe(), fontWeight: 700 }}>
              {nombreCompleto?.[0]?.toUpperCase() || 'U'}
            </Avatar>
            <Box sx={{ minWidth: 0 }}>
              <Typography noWrap sx={{ fontWeight: 700, fontSize: 16 }}>{nombreCompleto}</Typography>
              {rol && <Typography sx={{ fontSize: 13, color: TEXTO_TENUE }}>{rol.replace(/_/g, ' ')}</Typography>}
            </Box>
          </Box>
          <Divider />
          <List>
            <ListItemButton onClick={() => { setPerfilOpen(false); setInstalarOpen(true); }}>
              <ListItemIcon sx={{ minWidth: 40, color: TEXTO_TENUE }}><InstallMobile /></ListItemIcon>
              <ListItemText primary="Instalar app" primaryTypographyProps={{ fontWeight: 600 }} />
            </ListItemButton>
            <ListItemButton onClick={abrirCambioPassword}>
              <ListItemIcon sx={{ minWidth: 40, color: TEXTO_TENUE }}><LockReset /></ListItemIcon>
              <ListItemText primary="Cambiar contraseña" primaryTypographyProps={{ fontWeight: 600 }} />
            </ListItemButton>
            <ListItemButton onClick={handleLogout} sx={{ color: 'error.main' }}>
              <ListItemIcon sx={{ minWidth: 40, color: 'error.main' }}><Logout /></ListItemIcon>
              <ListItemText primary="Cerrar sesión" primaryTypographyProps={{ fontWeight: 700 }} />
            </ListItemButton>
          </List>
        </Drawer>

        <InstalarAppDialog open={instalarOpen} onClose={() => setInstalarOpen(false)} />
        <AvisoErrorGlobal />

        <Dialog open={pwOpen} onClose={() => setPwOpen(false)} maxWidth="xs" fullWidth>
          <DialogTitle>Cambiar contraseña</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              {pwMsg && <Alert severity={pwMsg.tipo}>{pwMsg.texto}</Alert>}
              <TextField label="Contraseña actual" type="password" value={pwActual}
                         onChange={(e) => setPwActual(e.target.value)} fullWidth autoComplete="current-password" />
              <TextField label="Contraseña nueva" type="password" value={pwNueva}
                         onChange={(e) => setPwNueva(e.target.value)} fullWidth autoComplete="new-password"
                         helperText="Mín. 8 (12 para ADMIN), con mayúscula, minúscula, número y carácter especial." />
              <TextField label="Confirmar contraseña nueva" type="password" value={pwConfirmar}
                         onChange={(e) => setPwConfirmar(e.target.value)} fullWidth autoComplete="new-password"
                         error={pwConfirmar.length > 0 && !pwCoincide}
                         helperText={pwConfirmar.length > 0 && !pwCoincide ? 'No coinciden' : ' '} />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setPwOpen(false)}>Cerrar</Button>
            <Button variant="contained" onClick={handleCambiarPassword}
                    disabled={pwSaving || !pwActual || !pwNueva || !pwCoincide}>
              {pwSaving ? 'Guardando…' : 'Cambiar'}
            </Button>
          </DialogActions>
        </Dialog>

        {/* El relleno inferior deja libre el alto de la barra fija MÁS el área segura
            de iOS: sin él, la última fila de cada pantalla queda tapada. */}
        {/* Área de información: blanca/gris claro como siempre. El azul se queda
            en las dos barras, que son el marco de la app. */}
        <Box sx={{
          flexGrow: 1, bgcolor: APP_FONDO, minWidth: 0, overflowX: 'hidden',
          // El relleno SUPERIOR va aparte del resto y mucho menor: con los 24px
          // uniformes quedaba una banda muerta entre el menú y el primer elemento de
          // cada pantalla, que se leía como un corte y no como aire. Los laterales sí
          // necesitan ese aire — son el margen de lectura del contenido.
          pt: { xs: 1, sm: 1.25 }, px: { xs: 1.5, sm: 3 },
          pb: { xs: `calc(${BOTTOM_NAV_H}px + env(safe-area-inset-bottom, 0px) + 16px)`,
                sm: `calc(${BOTTOM_NAV_H}px + env(safe-area-inset-bottom, 0px) + 24px)` },
        }}>
          {cicloAbierto?.vencido && (
            <Alert
              severity="warning"
              sx={{ mb: 2 }}
              action={
                (rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD') ? (
                  <Button color="inherit" size="small" onClick={() => navigate('/admin')}>
                    Ir a Ciclos
                  </Button>
                ) : undefined
              }
            >
              El ciclo de trabajo <b>{cicloAbierto.nombre}</b> ya venció (fin {cicloAbierto.fecha_fin}).
              Actualiza sus fechas al mes en curso, o ciérralo y abre el siguiente. Mientras tanto,
              el registro de visitas y el "ritmo diario requerido" no aplican.
            </Alert>
          )}
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

      <BottomNav activa={seccionActiva?.titulo ?? null} onPerfil={() => setPerfilOpen(true)} />
    </Box>
  );
}
