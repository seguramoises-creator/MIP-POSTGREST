import { useEffect, useState } from 'react';
import { Box, Card, CardContent, Typography, Button, Stack, Alert, Chip, Divider } from '@mui/material';
import { Android, Download, PhoneIphone, WifiOff, CheckCircle } from '@mui/icons-material';
import { TEXTO_TENUE } from '../../components/layout/navTokens';

/**
 * Descarga de VISTA Campo, la app de campo, desde la propia suite.
 *
 * El archivo se sirve como fichero estático desde nginx (`/descargas/…`), no por la
 * API: es un binario de decenas de megas que no necesita sesión ni pasa por el backend.
 */
const APK = '/descargas/vista-campo.apk';

/** Cómo se lee un tamaño en bytes sin obligar a contar ceros. */
function tamano(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

export default function AppMovil() {
  // Estado REAL del archivo, preguntado al servidor. No se pinta un botón de descarga
  // que lleve a un 404: en esta misma ruta, antes de servirlo, cualquier URL devolvía
  // el index.html con código 200 — el enlace «funcionaba» y bajaba una página web con
  // nombre de APK. Un botón que promete un archivo tiene que saber que existe.
  const [estado, setEstado] = useState<'buscando' | 'listo' | 'ausente'>('buscando');
  const [info, setInfo] = useState<{ bytes: number; fecha: string | null }>({ bytes: 0, fecha: null });

  useEffect(() => {
    fetch(APK, { method: 'HEAD' })
      .then((r) => {
        const tipo = r.headers.get('content-type') ?? '';
        // Un 200 no basta: hay que comprobar que lo servido NO es el HTML del SPA.
        if (!r.ok || tipo.includes('text/html')) { setEstado('ausente'); return; }
        setInfo({
          bytes: Number(r.headers.get('content-length') ?? 0),
          fecha: r.headers.get('last-modified'),
        });
        setEstado('listo');
      })
      .catch(() => setEstado('ausente'));
  }, []);

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 780 }}>
      <Typography variant="overline" sx={{ color: TEXTO_TENUE, letterSpacing: 1 }}>
        Fuerza de ventas
      </Typography>
      <Typography variant="h5" fontWeight={800}>VISTA Campo</Typography>
      <Typography variant="body2" sx={{ color: TEXTO_TENUE, mb: 2 }}>
        La app del representante para registrar su jornada desde el teléfono.
      </Typography>

      <Card variant="outlined" sx={{ borderRadius: 2, mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1.5 }}>
            <Android sx={{ fontSize: 30 }} />
            <Box sx={{ flex: 1 }}>
              <Typography fontWeight={700}>Android</Typography>
              <Typography variant="caption" sx={{ color: TEXTO_TENUE }}>
                {estado === 'listo' && info.bytes > 0
                  ? `${tamano(info.bytes)}${info.fecha ? ` · publicada el ${new Date(info.fecha).toLocaleDateString()}` : ''}`
                  : 'Instalación directa, sin tienda'}
              </Typography>
            </Box>
            {estado === 'listo' && <Chip size="small" color="success" variant="outlined" label="Disponible" />}
          </Stack>

          {estado === 'ausente' ? (
            <Alert severity="warning">
              Todavía no hay ninguna versión publicada. Un administrador debe copiar el
              archivo <code>vista-campo.apk</code> en la carpeta <code>descargas/</code> del
              servidor.
            </Alert>
          ) : (
            <Button variant="contained" size="large" startIcon={<Download />}
                    href={APK} disabled={estado !== 'listo'}
                    sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700 }}>
              Descargar la app
            </Button>
          )}
        </CardContent>
      </Card>

      <Card variant="outlined" sx={{ borderRadius: 2 }}>
        <CardContent>
          <Typography fontWeight={700} sx={{ mb: 1 }}>Cómo instalarla</Typography>
          <Stack spacing={1}>
            <Typography variant="body2">
              1. Abre esta página <b>desde el teléfono</b> y pulsa «Descargar la app».
            </Typography>
            <Typography variant="body2">
              2. Android pedirá permiso para instalar desde el navegador. Acéptalo: la app
              no está en la tienda porque es de uso interno.
            </Typography>
            <Typography variant="body2">
              3. Al abrirla, entra con <b>tu mismo usuario y contraseña</b> de esta suite.
              La primera vez te pedirá cambiar la contraseña.
            </Typography>
          </Stack>

          <Divider sx={{ my: 2 }} />
          <Typography fontWeight={700} sx={{ mb: 1 }}>Qué hace</Typography>
          <Stack spacing={0.75}>
            {[
              [<CheckCircle key="a" fontSize="small" color="success" />,
               'Registra visitas, revisitas, no-visitas y visitas a farmacia, con productos y muestras.'],
              [<WifiOff key="b" fontSize="small" />,
               'Funciona sin señal: lo capturado se guarda en el teléfono y sube solo cuando vuelve la conexión.'],
              [<PhoneIphone key="c" fontSize="small" />,
               'Captura la ubicación y una foto opcional del centro.'],
            ].map(([icono, texto], i) => (
              <Stack key={i} direction="row" spacing={1} alignItems="flex-start">
                <Box sx={{ mt: 0.3 }}>{icono as React.ReactNode}</Box>
                <Typography variant="body2">{texto as string}</Typography>
              </Stack>
            ))}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
