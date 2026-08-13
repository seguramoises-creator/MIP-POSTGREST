/**
 * Barra inferior de destinos — el patrón de la referencia: icono arriba, etiqueta
 * abajo, activo en el color de marca.
 *
 * Sustituye al menú lateral como navegación primaria EN TODOS LOS ANCHOS, no solo
 * en teléfono: lo pedido es que la app se vea igual sin importar el dispositivo.
 *
 * Cinco ranuras para ~30 rutas se resuelve en dos niveles, como la referencia:
 * aquí van las SECCIONES, y las pestañas de arriba (`TopTabs`) muestran los ítems
 * de la sección activa. La última ranura es siempre Perfil — ahí se recogió la
 * salida que antes vivía arriba a la derecha.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box, ButtonBase, Typography, Drawer, List, ListItemButton, ListItemIcon, ListItemText, Avatar,
} from '@mui/material';
import { MoreHoriz } from '@mui/icons-material';

import { useAuthStore } from '../../store/auth.store';
import { useNavSecciones, type Destino } from './useNavSecciones';
import { NAV_ACTIVO, NAV_AZUL, NAV_BORDE, NAV_FONDO, NAV_INACTIVO, TEXTO_TENUE, BOTTOM_NAV_H } from './navTokens';

/**
 * Ancho mínimo de una ranura para que su etiqueta se lea entera ("Desempeño" es
 * la más larga). De aquí sale cuántas caben: la referencia usa 5 porque es un
 * teléfono, pero en un monitor esconder secciones detrás de "Más" teniendo sitio
 * de sobra es esconderlas por copiar una restricción que ahí no existe.
 */
const ANCHO_MIN_RANURA = 104;
/** Mínimo razonable en pantallas muy estrechas. */
const RANURAS_MIN = 5;

interface Props {
  /** Sección activa (título, o null para el home). */
  activa: string | null | undefined;
  onPerfil: () => void;
}

export default function BottomNav({ activa, onPerfil }: Props) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { nombreCompleto } = useAuthStore();
  const secciones = useNavSecciones();
  const [masAbierto, setMasAbierto] = useState(false);

  // Cuántas ranuras caben AHORA. Se recalcula al cambiar el tamaño porque el
  // mismo usuario pasa del teléfono al monitor, y girar el teléfono ya cambia
  // el veredicto.
  const [ancho, setAncho] = useState(() => (typeof window === 'undefined' ? 1024 : window.innerWidth));
  useEffect(() => {
    const alRedimensionar = () => setAncho(window.innerWidth);
    window.addEventListener('resize', alRedimensionar);
    return () => window.removeEventListener('resize', alRedimensionar);
  }, []);

  // Las secciones que caben directas + Perfil. Si no caben todas, la última
  // ranura de sección pasa a ser "Más" y recoge el resto: preferible a recortar
  // en silencio destinos a los que el usuario sí tiene acceso.
  const { directas, desbordadas } = useMemo(() => {
    // +1 = la ranura de Perfil, que siempre está.
    const ranuras = Math.max(RANURAS_MIN, Math.min(secciones.length + 1,
                                                   Math.floor(ancho / ANCHO_MIN_RANURA)));
    const cupo = ranuras - 1;
    if (secciones.length <= cupo) return { directas: secciones, desbordadas: [] as Destino[] };
    return { directas: secciones.slice(0, cupo - 1), desbordadas: secciones.slice(cupo - 1) };
  }, [secciones, ancho]);

  const irA = (d: Destino) => {
    // Si ya se está dentro de la sección, no se navega: se respeta la pestaña abierta.
    const dentro = d.items.some((i) => pathname.startsWith(i.path));
    if (!dentro) navigate(d.items[0].path);
    setMasAbierto(false);
  };

  const enDesbordadas = desbordadas.some((d) => d.titulo === activa);

  const ranura = (
    key: string,
    icono: React.ReactNode,
    etiqueta: string,
    activo: boolean,
    onClick: () => void,
  ) => (
    <ButtonBase
      key={key}
      onClick={onClick}
      aria-current={activo ? 'page' : undefined}
      sx={{
        flex: 1, minWidth: 0, height: BOTTOM_NAV_H,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        gap: 0.25, color: activo ? NAV_ACTIVO : NAV_INACTIVO,
        // El foco visible NO se hereda de MUI en ButtonBase: se declara para que
        // la navegación por teclado siga siendo utilizable.
        '&:focus-visible': { outline: `2px solid ${NAV_ACTIVO}`, outlineOffset: -2 },
        '& .MuiSvgIcon-root': { fontSize: 24 },
      }}
    >
      {icono}
      <Typography
        component="span"
        noWrap
        sx={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.1px', maxWidth: '100%', px: 0.25 }}
      >
        {etiqueta}
      </Typography>
    </ButtonBase>
  );

  return (
    <>
      <Box
        component="nav"
        aria-label="Navegación principal"
        sx={{
          position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: (t) => t.zIndex.appBar + 1,
          background: NAV_FONDO,                    // degradado azul de VISTA (ver navTokens)
          borderTop: `1px solid ${NAV_BORDE}`,
          display: 'flex',
          // Área segura de iOS: sin esto la barra queda debajo del indicador de inicio.
          pb: 'env(safe-area-inset-bottom, 0px)',
        }}
      >
        {directas.map((d) =>
          ranura(d.titulo ?? 'inicio', d.icono, d.etiqueta, d.titulo === activa, () => irA(d)))}

        {desbordadas.length > 0 &&
          ranura('mas', <MoreHoriz />, 'Más', enDesbordadas, () => setMasAbierto(true))}

        {ranura(
          'perfil',
          <Avatar sx={{ width: 24, height: 24, fontSize: 12, bgcolor: NAV_ACTIVO, color: NAV_AZUL, fontWeight: 700 }}>
            {nombreCompleto?.[0]?.toUpperCase() || 'U'}
          </Avatar>,
          'Perfil', false, onPerfil,
        )}
      </Box>

      <Drawer
        anchor="bottom"
        open={masAbierto}
        onClose={() => setMasAbierto(false)}
        PaperProps={{ sx: { borderTopLeftRadius: 16, borderTopRightRadius: 16, pb: 'env(safe-area-inset-bottom, 0px)' } }}
      >
        <Box sx={{ px: 2, pt: 2, pb: 1 }}>
          <Typography sx={{ fontWeight: 700, fontSize: 16 }}>Más secciones</Typography>
        </Box>
        <List sx={{ pb: 1 }}>
          {desbordadas.map((d) => (
            <ListItemButton key={d.titulo} onClick={() => irA(d)} selected={d.titulo === activa}>
              <ListItemIcon sx={{ color: d.titulo === activa ? NAV_AZUL : TEXTO_TENUE, minWidth: 40 }}>
                {d.icono}
              </ListItemIcon>
              <ListItemText
                primary={d.titulo}
                primaryTypographyProps={{ fontWeight: 600, fontSize: 15 }}
              />
            </ListItemButton>
          ))}
        </List>
      </Drawer>
    </>
  );
}
