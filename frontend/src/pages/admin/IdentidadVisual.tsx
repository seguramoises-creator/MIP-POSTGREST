/**
 * Administración → Identidad visual.
 *
 * La pantalla que hace evidente lo que antes había que explicar: dos colores, y
 * toda la aplicación los sigue.
 *
 * SOLO DOS CAMPOS, y es la decisión de diseño de esta pantalla. La paleta tiene
 * ocho tonos, pero no son independientes: el degradado de las barras son
 * oscurecimientos del taupe y el rojo de los enlaces es el rojo de marca bajado
 * hasta cumplir contraste. Ofrecer los ocho invitaría a descuadrarlos, y el día
 * que la aplicación se viera mal nadie sabría cuál de los ocho campos lo causó.
 */
import { useEffect, useState } from 'react';
import {
  Box, Button, Card, CardContent, CircularProgress, Alert,
  Stack, TextField, Typography, Divider,
} from '@mui/material';
import { Palette, RestartAlt, Save } from '@mui/icons-material';
import { api } from '../../services/api';
import { MARCA_FABRICA, contraste, derivar } from '../../theme/marcaViva';
import { IDENTIDADES, IDENTIDAD_FABRICA, identidad } from '../../theme/identidades';
import { TEXTO_TENUE } from '../../components/layout/navTokens';
import { detalleError } from '../../utils/errores';

const HEX = /^#[0-9A-Fa-f]{6}$/;

export default function IdentidadVisual() {
  const [rojo, setRojo] = useState(MARCA_FABRICA.rojo);
  const [taupe, setTaupe] = useState(MARCA_FABRICA.taupe);
  const [logo, setLogo] = useState(IDENTIDAD_FABRICA);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  useEffect(() => {
    api.get('/admin/config/marca')
      .then(({ data }) => {
        const ident = identidad(data.logo);
        if (data.logo && IDENTIDADES[data.logo]) setLogo(data.logo);
        // Sin color guardado se muestran los de la identidad elegida, no los de
        // fábrica: es lo mismo que hace la aplicación al arrancar, y si esta
        // pantalla mostrara otra cosa el administrador vería una vista previa
        // que no corresponde a lo que hay en pantalla.
        setRojo(HEX.test(data.rojo || '') ? data.rojo.toUpperCase() : ident.rojo);
        setTaupe(HEX.test(data.taupe || '') ? data.taupe.toUpperCase() : ident.taupe);
      })
      .catch(() => { /* sin guardar: quedan los de fábrica */ })
      .finally(() => setCargando(false));
  }, []);

  const valido = HEX.test(rojo) && HEX.test(taupe);
  // La vista previa se calcula con la MISMA función que usa la aplicación al
  // arrancar. Si fuera un cálculo aparte, lo que se ve aquí y lo que se ve al
  // recargar podrían separarse sin que nadie lo notara.
  const previa = valido ? derivar(rojo, taupe, logo) : MARCA_FABRICA;
  const contrasteBarra = valido ? contraste('#FFFFFF', previa.taupe) : 0;
  const contrasteEnlace = valido ? contraste(previa.rojoOscuro, '#FFFFFF') : 0;

  const guardar = async () => {
    setGuardando(true); setMsg(''); setErr('');
    try {
      const { data } = await api.put('/admin/config/marca', { rojo, taupe, logo });
      setMsg(data.message || 'Guardado.');
    } catch (e: any) {
      setErr(detalleError(e, 'No se pudo guardar.'));
    } finally { setGuardando(false); }
  };

  // Vuelve a la paleta de la IDENTIDAD ELEGIDA, no a la de Mallén: si el
  // administrador está trabajando con la identidad de VISTA, "restablecer" tiene
  // que devolverlo a los colores de VISTA.
  const restablecer = () => {
    const ident = identidad(logo);
    setRojo(ident.rojo); setTaupe(ident.taupe);
    setMsg(''); setErr('');
  };

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  return (
    <Card variant="outlined" sx={{ borderRadius: 2 }}>
      <CardContent sx={{ p: 3 }}>
        <Stack direction="row" spacing={1.2} alignItems="center" sx={{ mb: 0.5 }}>
          <Palette sx={{ color: previa.rojo }} />
          <Typography variant="h6">Identidad visual</Typography>
        </Stack>
        <Typography variant="body2" sx={{ color: TEXTO_TENUE, mb: 3 }}>
          Estos dos colores gobiernan toda la aplicación. Los demás tonos —el degradado de
          las barras, el rojo de los enlaces— se calculan a partir de ellos, así que la
          paleta no se puede descuadrar.
        </Typography>

        {msg && <Alert severity="success" sx={{ mb: 2 }}>{msg}</Alert>}
        {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

        {/* El logotipo va PRIMERO porque elegirlo también cambia los colores: es la
            decisión de la que dependen las otras dos, y ponerlo después haría que
            el administrador viera cambiar unos campos que acaba de ajustar. */}
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Logotipo</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
          {Object.entries(IDENTIDADES).map(([clave, ident]) => (
            <Box key={clave} onClick={() => {
                   setLogo(clave);
                   // Al cambiar de identidad se traen SUS colores. Conservar los
                   // anteriores dejaría, por ejemplo, el logotipo de VISTA sobre
                   // las barras de Mallén — un estado que nadie pidió y que se
                   // ve como un error de la aplicación.
                   setRojo(ident.rojo); setTaupe(ident.taupe); setMsg('');
                 }}
                 sx={{ flex: 1, p: 2, borderRadius: 2, cursor: 'pointer',
                       border: '2px solid', borderColor: logo === clave ? previa.rojo : 'divider',
                       bgcolor: logo === clave ? 'action.hover' : 'transparent',
                       display: 'flex', alignItems: 'center', gap: 2 }}>
              {/* Sobre fondo claro va la versión a color; la blanca sería invisible. */}
              <Box component="img" src={ident.logoColor} alt={ident.nombre}
                   sx={{ height: 34, width: 'auto', flexShrink: 0 }} />
              <Box>
                <Typography sx={{ fontWeight: 600, fontSize: 14 }}>{ident.nombre}</Typography>
                <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
                  {[ident.taupe, ident.rojo].map((c) => (
                    <Box key={c} sx={{ width: 22, height: 12, borderRadius: 0.5, bgcolor: c }} />
                  ))}
                </Stack>
              </Box>
            </Box>
          ))}
        </Stack>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>Colores</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2.5} sx={{ mb: 3 }}>
          {([['Color de acción', rojo, setRojo, 'Botones, estado activo y acentos.'],
             ['Color de estructura', taupe, setTaupe, 'Barras, superficies y texto fuerte.'],
            ] as const).map(([etiqueta, valor, fijar, ayuda]) => (
            <Box key={etiqueta} sx={{ flex: 1 }}>
              <Stack direction="row" spacing={1.5} alignItems="center">
                {/* Un selector nativo junto al campo de texto: elegir un color a ojo es
                    más natural que escribir seis dígitos, pero quien tenga el valor
                    exacto de su manual de marca necesita poder pegarlo. */}
                <Box component="input" type="color" value={HEX.test(valor) ? valor : '#000000'}
                     onChange={(e: any) => fijar(e.target.value.toUpperCase())}
                     sx={{ width: 52, height: 44, p: 0, border: 'none', bgcolor: 'transparent',
                           cursor: 'pointer', flexShrink: 0 }} />
                <TextField fullWidth size="small" label={etiqueta} value={valor}
                           onChange={(e) => fijar(e.target.value.toUpperCase())}
                           error={!HEX.test(valor)}
                           helperText={HEX.test(valor) ? ayuda : 'Formato #RRGGBB'} />
              </Stack>
            </Box>
          ))}
        </Stack>

        <Divider sx={{ mb: 2.5 }} />

        <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Vista previa</Typography>
        <Box sx={{ borderRadius: 2, overflow: 'hidden', border: '1px solid', borderColor: 'divider' }}>
          <Box sx={{ background: previa.degradadoBarra, px: 2.5, py: 1.6,
                     display: 'flex', alignItems: 'center', gap: 2.5 }}>
            <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>Inicio</Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 600, fontSize: 14 }}>
              Panel Médico
            </Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 600, fontSize: 14 }}>
              Desempeño
            </Typography>
          </Box>
          <Box sx={{ p: 2.5, bgcolor: 'background.default' }}>
            <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
              <Box sx={{ bgcolor: previa.rojo, color: '#fff', px: 2, py: 0.9,
                         borderRadius: 1, fontWeight: 600, fontSize: 13 }}>
                Agregar médico
              </Box>
              <Typography sx={{ color: previa.rojoOscuro, fontWeight: 600, fontSize: 13 }}>
                ¿Olvidó su contraseña?
              </Typography>
              <Box sx={{ bgcolor: previa.rojoTenue, color: previa.rojoOscuro, px: 2, py: 0.9,
                         borderRadius: 1, fontSize: 13 }}>
                Aviso informativo
              </Box>
            </Stack>
          </Box>
        </Box>

        {/* El contraste se muestra SIEMPRE, no solo cuando falla: así el administrador
            ve el efecto de su elección mientras la hace, en vez de descubrir que la
            aplicación quedó ilegible cuando ya la usan cincuenta personas. */}
        {valido && (
          <Stack direction="row" spacing={3} sx={{ mt: 2, flexWrap: 'wrap' }} useFlexGap>
            <Typography variant="caption" sx={{ color: TEXTO_TENUE }}>
              Texto blanco sobre la barra:{' '}
              <b style={{ color: contrasteBarra >= 4.5 ? undefined : previa.rojoOscuro }}>
                {contrasteBarra.toFixed(1)} : 1
              </b>{' '}
              {contrasteBarra >= 4.5 ? '· legible' : '· demasiado claro, el texto no se leerá'}
            </Typography>
            <Typography variant="caption" sx={{ color: TEXTO_TENUE }}>
              Enlaces sobre blanco: <b>{contrasteEnlace.toFixed(1)} : 1</b> · ajustado
              automáticamente
            </Typography>
          </Stack>
        )}


        <Divider sx={{ my: 3 }} />

        {/* La tipografía se MUESTRA, no se edita. Las dos familias viajan dentro del
            paquete de la aplicación —no se descargan de internet, para que funcione
            sin conexión en la calle—, así que cambiarlas exige subir archivos de
            fuente, no elegir de una lista. Aquí queda documentado qué usa cada una:
            es lo que un administrador necesita saber para pedir un cambio, y evita
            que alguien busque un desplegable que no existe. */}
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Dos tipos de letra para mantener una presentación uniforme
        </Typography>
        <Typography variant="body2" sx={{ color: TEXTO_TENUE, mb: 2 }}>
          Vienen incluidas en la aplicación y se ven igual en cualquier equipo, con o sin
          conexión.
        </Typography>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          {([
            ['Manrope', 'Títulos y elementos destacados',
             'Para títulos de páginas, secciones, tarjetas, cifras e indicadores.'],
            ['Inter', 'Textos y elementos de navegación',
             'Para menús, botones, formularios, tablas, mensajes y textos.'],
          ] as const).map(([familia, papel, detalle]) => (
            <Box key={familia} sx={{ flex: 1, p: 2.2, borderRadius: 2,
                                     border: '1px solid', borderColor: 'divider',
                                     bgcolor: 'background.default' }}>
              {/* Cada nombre se pinta CON su propia fuente: es la única forma de que
                  el administrador vea la diferencia en vez de leer sobre ella. */}
              <Typography sx={{ fontFamily: `"${familia}", sans-serif`,
                                fontWeight: familia === 'Manrope' ? 800 : 500,
                                fontSize: 30, letterSpacing: '-0.02em', lineHeight: 1.15 }}>
                {familia}
              </Typography>
              <Typography sx={{ fontWeight: 600, fontSize: 13.5, mt: 0.8 }}>{papel}</Typography>
              <Typography variant="body2" sx={{ color: TEXTO_TENUE, mt: 0.3 }}>{detalle}</Typography>
            </Box>
          ))}
        </Stack>

        <Stack direction="row" spacing={1.5} sx={{ mt: 3 }}>
          <Button variant="contained" startIcon={<Save />} disabled={!valido || guardando}
                  onClick={guardar}>
            {guardando ? 'Guardando…' : 'Guardar y aplicar'}
          </Button>
          <Button variant="outlined" startIcon={<RestartAlt />} onClick={restablecer}>
            Volver a los colores de Mallén
          </Button>
        </Stack>
        <Typography variant="caption" sx={{ display: 'block', mt: 1.5, color: TEXTO_TENUE }}>
          El cambio alcanza a todas las pantallas al recargar. No hace falta desplegar nada.
        </Typography>
      </CardContent>
    </Card>
  );
}
