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
import { TEXTO_TENUE } from '../../components/layout/navTokens';

const HEX = /^#[0-9A-Fa-f]{6}$/;

export default function IdentidadVisual() {
  const [rojo, setRojo] = useState(MARCA_FABRICA.rojo);
  const [taupe, setTaupe] = useState(MARCA_FABRICA.taupe);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  useEffect(() => {
    api.get('/admin/config/marca')
      .then(({ data }) => {
        if (HEX.test(data.rojo || '')) setRojo(data.rojo.toUpperCase());
        if (HEX.test(data.taupe || '')) setTaupe(data.taupe.toUpperCase());
      })
      .catch(() => { /* sin guardar: quedan los de fábrica */ })
      .finally(() => setCargando(false));
  }, []);

  const valido = HEX.test(rojo) && HEX.test(taupe);
  // La vista previa se calcula con la MISMA función que usa la aplicación al
  // arrancar. Si fuera un cálculo aparte, lo que se ve aquí y lo que se ve al
  // recargar podrían separarse sin que nadie lo notara.
  const previa = valido ? derivar(rojo, taupe) : MARCA_FABRICA;
  const contrasteBarra = valido ? contraste('#FFFFFF', previa.taupe) : 0;
  const contrasteEnlace = valido ? contraste(previa.rojoOscuro, '#FFFFFF') : 0;

  const guardar = async () => {
    setGuardando(true); setMsg(''); setErr('');
    try {
      const { data } = await api.put('/admin/config/marca', { rojo, taupe });
      setMsg(data.message || 'Guardado.');
    } catch (e: any) {
      setErr(e.response?.data?.detail || 'No se pudo guardar.');
    } finally { setGuardando(false); }
  };

  const restablecer = () => {
    setRojo(MARCA_FABRICA.rojo); setTaupe(MARCA_FABRICA.taupe);
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
