/**
 * InstalarAppDialog — Modal para "descargar"/instalar la PWA de VISTA.
 * Dos botones: Android e iPhone/iPad (iOS), cada uno con sus pasos.
 * En Android/Chrome lanza la instalación nativa (beforeinstallprompt);
 * en iOS Apple no expone API de instalación → se muestran los pasos.
 * Aditivo: no depende de nada del resto del sistema.
 */
import { useEffect, useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Box,
  Typography, Stack, IconButton, Alert,
} from '@mui/material';
import { Android, Apple, InstallMobile, Close } from '@mui/icons-material';

type BIPEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

function PasosLista({ pasos }: { pasos: string[] }) {
  return (
    <Stack component="ol" spacing={1} sx={{ pl: 2.5, m: 0 }}>
      {pasos.map((p, i) => (
        <Typography key={i} component="li" variant="body2">{p}</Typography>
      ))}
    </Stack>
  );
}

export default function InstalarAppDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [deferred, setDeferred] = useState<BIPEvent | null>(null);
  const [instalada, setInstalada] = useState(false);
  const [plataforma, setPlataforma] = useState<'android' | 'ios' | null>(null);

  useEffect(() => {
    const onBIP = (e: Event) => { e.preventDefault(); setDeferred(e as BIPEvent); };
    const onInstalled = () => { setInstalada(true); setDeferred(null); };
    window.addEventListener('beforeinstallprompt', onBIP);
    window.addEventListener('appinstalled', onInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBIP);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, []);

  // Preselecciona la plataforma del dispositivo al abrir.
  useEffect(() => {
    if (!open) return;
    const ua = navigator.userAgent || '';
    if (/iPhone|iPad|iPod/i.test(ua)) setPlataforma('ios');
    else if (/Android/i.test(ua)) setPlataforma('android');
  }, [open]);

  const instalarAndroid = async () => {
    if (!deferred) return;
    await deferred.prompt();
    try { await deferred.userChoice; } catch { /* noop */ }
    setDeferred(null);
  };

  const yaInstalada =
    typeof window !== 'undefined' &&
    (window.matchMedia?.('(display-mode: standalone)').matches ||
      (navigator as unknown as { standalone?: boolean }).standalone === true);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pr: 1 }}>
        <InstallMobile color="primary" /> Instalar la app VISTA
        <IconButton onClick={onClose} size="small" sx={{ ml: 'auto' }} aria-label="Cerrar">
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {yaInstalada ? (
          <Alert severity="success">Ya estás usando VISTA instalada como app. 🎉</Alert>
        ) : instalada ? (
          <Alert severity="success">¡Listo! VISTA se instaló en tu dispositivo.</Alert>
        ) : (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Instala VISTA para abrirla como una app: pantalla completa, ícono en tu inicio y
              acceso rápido. Elige tu sistema:
            </Typography>

            <Stack direction="row" spacing={1.5} sx={{ mb: 2 }}>
              <Button fullWidth size="large" startIcon={<Android />} sx={{ py: 1.25 }}
                      variant={plataforma === 'android' ? 'contained' : 'outlined'}
                      onClick={() => setPlataforma('android')}>
                Android
              </Button>
              <Button fullWidth size="large" startIcon={<Apple />} sx={{ py: 1.25 }}
                      variant={plataforma === 'ios' ? 'contained' : 'outlined'}
                      onClick={() => setPlataforma('ios')}>
                iPhone / iPad
              </Button>
            </Stack>

            {plataforma === 'android' && (
              <Box>
                {deferred ? (
                  <>
                    <Button fullWidth size="large" variant="contained" startIcon={<InstallMobile />}
                            onClick={instalarAndroid}>
                      Instalar ahora
                    </Button>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                      Se abrirá el diálogo de instalación de tu navegador.
                    </Typography>
                  </>
                ) : (
                  <PasosLista pasos={[
                    'Abre esta página en Chrome (Android).',
                    'Toca el menú ⋮ (arriba a la derecha).',
                    'Elige “Instalar aplicación” o “Agregar a pantalla principal”.',
                    'Confirma: el ícono de VISTA quedará en tu inicio.',
                  ]} />
                )}
              </Box>
            )}

            {plataforma === 'ios' && (
              <PasosLista pasos={[
                'Abre esta página en Safari (no Chrome) en tu iPhone/iPad.',
                'Toca el botón Compartir ⬆️ (barra inferior).',
                'Desliza y elige “Agregar a pantalla de inicio”.',
                'Toca “Agregar”: el ícono de VISTA quedará en tu inicio.',
              ]} />
            )}

            {!plataforma && (
              <Typography variant="caption" color="text.secondary">
                Selecciona Android o iPhone/iPad para ver los pasos.
              </Typography>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  );
}
