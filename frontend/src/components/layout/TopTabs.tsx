/**
 * Pestañas superiores — el otro patrón de la referencia: icono arriba, etiqueta
 * abajo, y una barra bajo la activa.
 *
 * Muestran los ítems de la sección elegida en la barra inferior. Ese reparto es
 * lo que permite que 5 ranuras cubran ~30 rutas sin esconder nada: abajo se elige
 * el área, arriba se elige la pantalla.
 */
import { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Box, ButtonBase, Typography } from '@mui/material';

import type { NavItem } from './Sidebar';
import { NAV_ACTIVO, NAV_INACTIVO } from './navTokens';
import { tinteDeSeccion } from '../../theme/marca';

export default function TopTabs({ items, seccion }: { items: NavItem[]; seccion?: string | null }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const activaRef = useRef<HTMLButtonElement | null>(null);

  // Una sección puede tener 8 ítems y no caben en pantalla: si la activa quedó
  // fuera de la vista, el usuario no ve dónde está parado. Se trae al centro.
  useEffect(() => {
    activaRef.current?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [pathname]);

  // Con una sola pantalla la fila no aporta nada: sería un adorno que roba alto.
  if (items.length <= 1) return null;

  return (
    <Box
      component="nav"
      aria-label="Secciones"
      sx={{
        // Sin fondo propio: hereda el degradado del AppBar. Si se pintara aparte,
        // el degradado se reiniciaría aquí y se vería un corte a media barra.
        // Centradas con MÁRGENES AUTOMÁTICOS, no con `justifyContent: center`.
        //
        // `center` sobre un contenedor que desborda RECORTA POR EL INICIO: el navegador
        // reparte el sobrante a ambos lados y el desplazamiento no puede recuperar lo que
        // quedó en coordenada negativa. Medido en móvil (375px): la primera pestaña caía
        // en x=-80 y era inalcanzable. En escritorio no se notaba porque las 5 cabían.
        //
        // Con `margin:auto` en el primero y el último se centra cuando sobra sitio y se
        // alinea al inicio cuando falta, que es el comportamiento correcto en ambos casos.
        display: 'flex', gap: 0.5, overflowX: 'auto', bgcolor: 'transparent',
        '& > *': { flexShrink: 0 },
        '& > *:first-of-type': { marginLeft: 'auto' },
        '& > *:last-of-type': { marginRight: 'auto' },
        // `flex: 1` la hace ocupar el hueco entre el logo y las píldoras de la derecha,
        // dentro de la MISMA fila. Ya no lleva reserva a la izquierda: el logo es ahora
        // un hermano en el flex, no algo que se le monte encima.
        flex: 1, minWidth: 0, px: 1,
        // La barra de scroll horizontal en escritorio ensucia y ocupa alto; el
        // desplazamiento sigue disponible con rueda, gesto y teclado.
        scrollbarWidth: 'none', '&::-webkit-scrollbar': { display: 'none' },
      }}
    >
      {items.map((item) => {
        const activa = pathname.startsWith(item.path)
          && (item.path !== '/dashboard' || pathname === '/dashboard');
        return (
          <ButtonBase
            key={item.path}
            ref={activa ? activaRef : undefined}
            onClick={() => navigate(item.path)}
            aria-current={activa ? 'page' : undefined}
            sx={{
              flex: '0 0 auto', px: 1.5, py: 0.5,
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.25,
              color: activa ? NAV_ACTIVO : NAV_INACTIVO,
              '&:focus-visible': { outline: `2px solid ${NAV_ACTIVO}`, outlineOffset: -2 },
              // Los ítems de una misma sección comparten su tinte: la fila entera se lee
              // como un bloque y refuerza en qué sección estás, sin repetir la etiqueta.
              // La activa vuelve a blanco, que es el máximo contraste disponible.
              '& .MuiSvgIcon-root': { fontSize: 24, color: activa ? 'inherit' : tinteDeSeccion(seccion) },
            }}
          >
            {item.icon}
            <Typography
              component="span"
              noWrap
              sx={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.1px' }}
            >
              {item.label}
            </Typography>
            {/* Subrayado de la activa. Siempre presente pero transparente, para que
                al cambiar de pestaña no salte el alto de la fila. */}
            <Box sx={{
              width: '100%', height: 3, borderRadius: '3px 3px 0 0', mt: 0.5,
              bgcolor: activa ? NAV_ACTIVO : 'transparent',
            }} />
          </ButtonBase>
        );
      })}
    </Box>
  );
}
