/**
 * ImportDims.tsx — Wizard de Importación de Dimensiones (DIMs)
 * =============================================================
 * Flujo en 3 pasos:
 *   Paso 1: Seleccionar archivo Excel (.xlsx)
 *   Paso 2: Ver hojas detectadas y seleccionar cuáles importar
 *   Paso 3: Ver resultados de la importación
 */
import { useState, useRef } from 'react';
import {
  Box, Typography, Button, Alert, CircularProgress,
  Stepper, Step, StepLabel, Paper, Chip,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Checkbox, FormControlLabel, Divider, LinearProgress,
} from '@mui/material';
import {
  Upload, CheckCircle, Error as ErrorIcon,
  ArrowForward, ArrowBack, Refresh, TableChart,
} from '@mui/icons-material';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';

// ── Tipos ──────────────────────────────────────────────────────────────
interface HojaInfo {
  nombre_hoja: string;
  tabla_sistema: string;
  label: string;
  filas: number;
  columnas: string[];
  reconocida: boolean;
  orden: number;
}

interface ResultadoHoja {
  nombre_hoja: string;
  label: string;
  exitoso: boolean;
  insertados: number;
  omitidos: number;
  errores: number;
  mensaje: string;
}

const PASOS = ['Seleccionar archivo', 'Elegir hojas a importar', 'Resultados'];

export default function ImportDims() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [paso, setPaso] = useState(0);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [hojas, setHojas] = useState<HojaInfo[]>([]);
  const [seleccionadas, setSeleccionadas] = useState<Set<string>>(new Set());
  const [resultados, setResultados] = useState<ResultadoHoja[]>([]);
  const [totalIns, setTotalIns] = useState(0);
  const [totalOm, setTotalOm] = useState(0);
  const [totalErr, setTotalErr] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // ── Paso 1: Leer el archivo y obtener preview ──────────────────────
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setArchivo(file);
    setError('');
    setLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const { data } = await api.post('/dims/preview', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setHojas(data.hojas);
      // Pre-seleccionar todas las hojas reconocidas
      setSeleccionadas(new Set(data.hojas.filter((h: HojaInfo) => h.reconocida).map((h: HojaInfo) => h.nombre_hoja)));
      setPaso(1);
    } catch (err: any) {
      setError(`Error leyendo el archivo: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
      e.target.value = '';
    }
  };

  // ── Toggle selección de hoja ───────────────────────────────────────
  const toggleHoja = (nombre: string) => {
    setSeleccionadas(prev => {
      const next = new Set(prev);
      next.has(nombre) ? next.delete(nombre) : next.add(nombre);
      return next;
    });
  };

  const toggleTodas = () => {
    const reconocidas = hojas.filter(h => h.reconocida).map(h => h.nombre_hoja);
    if (reconocidas.every(n => seleccionadas.has(n))) {
      setSeleccionadas(new Set());
    } else {
      setSeleccionadas(new Set(reconocidas));
    }
  };

  // ── Paso 2: Ejecutar la importación ───────────────────────────────
  const handleImportar = async () => {
    if (!archivo || seleccionadas.size === 0) return;
    setLoading(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', archivo);
      form.append('hojas', JSON.stringify(Array.from(seleccionadas)));
      const { data } = await api.post('/dims/importar', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResultados(data.resultados);
      setTotalIns(data.total_insertados);
      setTotalOm(data.total_omitidos);
      setTotalErr(data.total_errores);
      // Eliminar cache y re-fetch activo para que el filtro por país muestre datos frescos
      ['paises', 'lineas', 'gerentes', 'rms', 'indicadores', 'ciclos', 'rangos'].forEach(k =>
        qc.removeQueries({ queryKey: [k] })
      );
      setPaso(2);
    } catch (err: any) {
      setError(`Error durante la importación: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // ── Reiniciar proceso ──────────────────────────────────────────────
  const reiniciar = () => {
    setPaso(0);
    setArchivo(null);
    setHojas([]);
    setSeleccionadas(new Set());
    setResultados([]);
    setError('');
  };

  return (
    <Box>
      <Typography variant="h6" fontWeight={600} mb={1}>
        Importar Dimensiones desde Excel
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Carga masiva de catálogos maestros (Países, Líneas, Gerentes, RMs, Indicadores, etc.)
        desde un archivo Excel con múltiples hojas.
      </Typography>

      {/* Indicador de pasos */}
      <Stepper activeStep={paso} sx={{ mb: 4 }}>
        {PASOS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

      {/* ── PASO 0: Seleccionar archivo ─────────────────────────── */}
      {paso === 0 && (
        <Box sx={{ textAlign: 'center', py: 6 }}>
          <TableChart sx={{ fontSize: 80, color: 'primary.light', mb: 2 }} />
          <Typography variant="h6" mb={1}>Selecciona el archivo Excel con las DIMs</Typography>
          <Typography variant="body2" color="text.secondary" mb={3}>
            El archivo debe tener una hoja por cada dimensión:<br />
            <strong>DIM_PAIS, DIM_LINEA, DIM_GERENTE, DIM_RM, DIM_INDICADOR, DIM_INDICADOR_TABLA, DIM_CICLO, DIM_MES</strong>
          </Typography>
          <input
            type="file" accept=".xlsx,.xls" ref={fileRef}
            style={{ display: 'none' }} onChange={handleFileChange}
          />
          <Button
            variant="contained" size="large" startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <Upload />}
            onClick={() => fileRef.current?.click()}
            disabled={loading}
            sx={{ px: 4, py: 1.5 }}
          >
            {loading ? 'Leyendo archivo...' : 'Seleccionar archivo Excel'}
          </Button>
        </Box>
      )}

      {/* ── PASO 1: Seleccionar hojas ───────────────────────────── */}
      {paso === 1 && (
        <Box>
          <Alert severity="success" sx={{ mb: 2 }}>
            <strong>Archivo leído correctamente:</strong> {archivo?.name} — {hojas.length} hoja(s) detectadas,{' '}
            {hojas.filter(h => h.reconocida).length} reconocidas como DIMs del sistema.
          </Alert>

          {/* Botón seleccionar/deseleccionar todas */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={hojas.filter(h => h.reconocida).every(h => seleccionadas.has(h.nombre_hoja))}
                  indeterminate={
                    seleccionadas.size > 0 &&
                    !hojas.filter(h => h.reconocida).every(h => seleccionadas.has(h.nombre_hoja))
                  }
                  onChange={toggleTodas}
                />
              }
              label={<Typography fontWeight={600}>Seleccionar todas las DIMs reconocidas</Typography>}
            />
            <Chip label={`${seleccionadas.size} seleccionada(s)`} color="primary" variant="outlined" />
          </Box>

          {/* Tabla de hojas detectadas */}
          <TableContainer component={Paper} elevation={1} sx={{ borderRadius: 2, mb: 3 }}>
            <Table size="small">
              <TableHead sx={{ bgcolor: 'primary.main' }}>
                <TableRow>
                  <TableCell sx={{ color: 'white', fontWeight: 700, width: 56 }}>Importar</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }}>Hoja en Excel</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }}>Tabla del Sistema</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }}>Descripción</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }} align="center">Filas</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }} align="center">Estado</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {hojas.map((hoja) => (
                  <TableRow
                    key={hoja.nombre_hoja}
                    hover
                    selected={seleccionadas.has(hoja.nombre_hoja)}
                    sx={{ opacity: hoja.reconocida ? 1 : 0.5 }}
                  >
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={seleccionadas.has(hoja.nombre_hoja)}
                        onChange={() => toggleHoja(hoja.nombre_hoja)}
                        disabled={!hoja.reconocida}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography fontFamily="monospace" fontSize="0.85rem" fontWeight={600}>
                        {hoja.nombre_hoja}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography fontSize="0.85rem" color="text.secondary">
                        {hoja.tabla_sistema}
                      </Typography>
                    </TableCell>
                    <TableCell>{hoja.label}</TableCell>
                    <TableCell align="center">
                      <Chip label={hoja.filas} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell align="center">
                      {hoja.reconocida
                        ? <Chip label="Reconocida" color="success" size="small" />
                        : <Chip label="No reconocida" color="default" size="small" />
                      }
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Columnas detectadas (info expandida) */}
          {hojas.filter(h => seleccionadas.has(h.nombre_hoja)).map(hoja => (
            <Alert key={hoja.nombre_hoja} severity="info" sx={{ mb: 1 }} icon={false}>
              <Typography variant="caption" fontWeight={600}>{hoja.nombre_hoja}</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                Columnas: {hoja.columnas.join(', ')}
              </Typography>
            </Alert>
          ))}

          {/* Botones de navegación */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 3 }}>
            <Button startIcon={<ArrowBack />} onClick={reiniciar}>
              Cambiar archivo
            </Button>
            <Button
              variant="contained" endIcon={loading ? <CircularProgress size={18} color="inherit" /> : <ArrowForward />}
              onClick={handleImportar}
              disabled={seleccionadas.size === 0 || loading}
              size="large"
            >
              {loading ? 'Importando...' : `Importar ${seleccionadas.size} hoja(s)`}
            </Button>
          </Box>
          {loading && <LinearProgress sx={{ mt: 2 }} />}
        </Box>
      )}

      {/* ── PASO 2: Resultados ──────────────────────────────────── */}
      {paso === 2 && (
        <Box>
          {/* Resumen general */}
          <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap' }}>
            <Paper elevation={2} sx={{ p: 2, flex: 1, minWidth: 150, textAlign: 'center', borderTop: '4px solid #4caf50' }}>
              <Typography variant="h4" fontWeight={700} color="success.main">{totalIns}</Typography>
              <Typography variant="body2" color="text.secondary">Registros insertados</Typography>
            </Paper>
            <Paper elevation={2} sx={{ p: 2, flex: 1, minWidth: 150, textAlign: 'center', borderTop: '4px solid #ff9800' }}>
              <Typography variant="h4" fontWeight={700} color="warning.main">{totalOm}</Typography>
              <Typography variant="body2" color="text.secondary">Ya existían (omitidos)</Typography>
            </Paper>
            <Paper elevation={2} sx={{ p: 2, flex: 1, minWidth: 150, textAlign: 'center', borderTop: '4px solid #f44336' }}>
              <Typography variant="h4" fontWeight={700} color="error.main">{totalErr}</Typography>
              <Typography variant="body2" color="text.secondary">Errores</Typography>
            </Paper>
          </Box>

          {/* Detalle por hoja */}
          <TableContainer component={Paper} elevation={1} sx={{ borderRadius: 2, mb: 3 }}>
            <Table size="small">
              <TableHead sx={{ bgcolor: 'primary.main' }}>
                <TableRow>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }}>Hoja / DIM</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }} align="center">Insertados</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }} align="center">Ya existían</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }} align="center">Errores</TableCell>
                  <TableCell sx={{ color: 'white', fontWeight: 700 }}>Resultado</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {resultados.map((r) => (
                  <TableRow key={r.nombre_hoja} hover>
                    <TableCell>
                      <Typography fontWeight={600}>{r.label}</Typography>
                      <Typography variant="caption" fontFamily="monospace" color="text.secondary">
                        {r.nombre_hoja}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Chip label={r.insertados} color="success" size="small" variant={r.insertados > 0 ? 'filled' : 'outlined'} />
                    </TableCell>
                    <TableCell align="center">
                      <Chip label={r.omitidos} color="warning" size="small" variant={r.omitidos > 0 ? 'filled' : 'outlined'} />
                    </TableCell>
                    <TableCell align="center">
                      <Chip label={r.errores} color={r.errores > 0 ? 'error' : 'default'} size="small" variant={r.errores > 0 ? 'filled' : 'outlined'} />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {r.exitoso
                          ? <CheckCircle fontSize="small" color="success" />
                          : <ErrorIcon fontSize="small" color="error" />
                        }
                        <Typography variant="caption" color="text.secondary">{r.mensaje}</Typography>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2 }}>
            <Button variant="outlined" startIcon={<Refresh />} onClick={reiniciar}>
              Importar otro archivo
            </Button>
            <Button variant="contained" color="success" startIcon={<CheckCircle />} onClick={reiniciar}>
              Finalizar
            </Button>
          </Box>
        </Box>
      )}
    </Box>
  );
}
