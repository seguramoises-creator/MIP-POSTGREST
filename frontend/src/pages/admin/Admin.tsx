/**
 * Admin.tsx — Página de Administración del Sistema SCGCPR
 *
 * Permite gestionar todos los catálogos maestros del sistema:
 * Países, Líneas, Gerentes, RMs, Indicadores, Ciclos, Usuarios y Rangos de Puntuación.
 *
 * Cada pestaña ofrece:
 * - Listado con columnas relevantes
 * - Botón Nuevo (con formulario modal)
 * - Botón Editar por fila
 * - Botón Eliminar/Desactivar por fila
 * - Botón Importar (solo en tabs que tienen endpoint de importación en el backend)
 *
 * El país siempre se muestra como "CR — Costa Rica" (no como ID numérico).
 */
import { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Tabs, Tab, Card, CardContent,
  Table, TableBody, TableCell, TableContainer, TableFooter, TableHead,
  TableRow, Paper, Button, Chip, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, Grid, Alert,
  CircularProgress, MenuItem, Select, FormControl, InputLabel, FormHelperText,
  IconButton, Tooltip, Autocomplete, Checkbox,
} from '@mui/material';
import { Add, Refresh, TableChart, Edit, Upload, ToggleOn, ToggleOff, LockOpen, Lock, Delete, Psychology, TrendingUp, LocalHospital } from '@mui/icons-material';
import { api } from '../../services/api';
import { useCicloStore } from '../../store/ciclo.store';
import ImportDims from './ImportDims';
import LsiiAdmin from './LsiiAdmin';
import CoberturaPredictivaAdmin from './CoberturaPredictivaAdmin';
import CategorizacionAdmin, { TabGeo } from './CategorizacionAdmin';
import { BORDE_FUERTE, EXITO, ROJO, ROJO_OSCURO, SUPERFICIE_2, SUPERFICIE_3, TAUPE } from '../../theme/marca';

// ── Hook: carga la lista de países y la reutiliza en toda la página ──
function usePaises() {
  return useQuery({
    queryKey: ['paises'],
    queryFn: () => api.get('/admin/paises').then((r) => {
      const d = r.data;
      return (Array.isArray(d) ? d : (d?.items ?? [])) as { id: number; codigo: string; nombre: string }[];
    }),
    staleTime: 0, // siempre considera los datos desactualizados → refetch en cada mount
  });
}

// ── Hook: líneas filtradas por país — para resolver nombre, nunca ID crudo ──
function useLineas(paisCodigo: number | string | '') {
  return useQuery({
    queryKey: ['lineas', paisCodigo],
    queryFn: () => api.get('/admin/lineas', { params: paisCodigo ? { pais_codigo: paisCodigo } : {} }).then((r) => {
      const d = r.data;
      return (Array.isArray(d) ? d : (d?.items ?? [])) as { id: number; codigo: string; nombre: string; pais_codigo: string }[];
    }),
    enabled: paisCodigo !== '' && paisCodigo !== undefined,
    staleTime: 0,
  });
}

// ── Hook: gerentes filtrados por país — para resolver nombre, nunca ID crudo ──
function useGerentes(paisCodigo: number | string | '') {
  return useQuery({
    queryKey: ['gerentes', paisCodigo],
    queryFn: () => api.get('/admin/gerentes', { params: paisCodigo ? { pais_codigo: paisCodigo } : {} }).then((r) => {
      const d = r.data;
      return (Array.isArray(d) ? d : (d?.items ?? [])) as { id: number; codigo: string; nombre: string; tipo: string; pais_codigo: string }[];
    }),
    enabled: paisCodigo !== '' && paisCodigo !== undefined,
    staleTime: 0,
  });
}

/**
 * PaisLabel — Muestra "CR — Costa Rica" dado un pais_codigo numérico.
 * Usa la lista de países ya cargada para resolver el nombre.
 */
function PaisLabel({ paisCodigo, paises }: { paisCodigo: string | null; paises: { id: number; codigo: string; nombre: string }[] | undefined }) {
  if (!paisCodigo || !paises) return <span style={{ color: '#999' }}>—</span>;
  const p = paises.find((x) => x.codigo === paisCodigo);
  return p ? <Chip label={`${p.codigo} — ${p.nombre}`} size="small" variant="outlined" /> : <span>{paisCodigo}</span>;
}

/**
 * PaisSelector — Select de país con formato "CR — Costa Rica".
 * Usado en formularios de creación/edición y en filtros.
 */
function PaisSelector({ value, onChange, label = 'País' }: {
  value: string | number;
  onChange: (v: string) => void;
  label?: string;
}) {
  const { data: paises } = usePaises();
  return (
    <FormControl fullWidth size="small">
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={value} onChange={(e) => onChange(String(e.target.value))}>
        {(paises || []).map((p) => (
          <MenuItem key={p.id} value={p.codigo}>
            {p.codigo} — {p.nombre}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

/**
 * LineaSelector — Select de línea con formato "CAR — Cardiovascular".
 * Se filtra por el país ya elegido en el mismo formulario; nunca pide un ID crudo.
 */
function LineaSelector({ value, onChange, paisCodigo, label = 'Línea' }: {
  value: string | number;
  onChange: (v: string) => void;
  paisCodigo: string | number | '';
  label?: string;
}) {
  const { data: lineas } = useLineas(paisCodigo);
  return (
    <FormControl fullWidth size="small" disabled={!paisCodigo}>
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={value} onChange={(e) => onChange(String(e.target.value))}>
        {(lineas || []).map((l) => (
          <MenuItem key={l.id} value={l.id}>
            {l.codigo} — {l.nombre}
          </MenuItem>
        ))}
      </Select>
      {!paisCodigo && <FormHelperText>Seleccione primero el país</FormHelperText>}
    </FormControl>
  );
}

/**
 * GerenteSelector — Select de gerente con formato "GD001 — Juan Pérez (DISTRITO)".
 * Se filtra por el país ya elegido en el mismo formulario; nunca pide un ID crudo.
 */
function GerenteSelector({ value, onChange, paisCodigo, label = 'Gerente' }: {
  value: string | number;
  onChange: (v: string) => void;
  paisCodigo: string | number | '';
  label?: string;
}) {
  const { data: gerentes } = useGerentes(paisCodigo);
  return (
    <FormControl fullWidth size="small" disabled={!paisCodigo}>
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={value} onChange={(e) => onChange(String(e.target.value))}>
        {(gerentes || []).map((g) => (
          <MenuItem key={g.id} value={g.id}>
            {g.codigo} — {g.nombre} ({g.tipo})
          </MenuItem>
        ))}
      </Select>
      {!paisCodigo && <FormHelperText>Seleccione primero el país</FormHelperText>}
    </FormControl>
  );
}

/**
 * GerenteProductoSelector — Select de "Gerente de Producto" alimentado desde DIM_Gerente
 * filtrado por CÓDIGO que inicia con "GP" (Gerente de Producto). La columna
 * DIM_Producto.gerente_producto es texto, así que se guarda el NOMBRE (no el ID).
 * Formato "GP01 — Ana Ruiz". Conserva un valor histórico de texto libre que no esté
 * en la lista GP para no perderlo al editar.
 */
function GerenteProductoSelector({ value, onChange, paisCodigo, label = 'Gerente de Producto (responsable)' }: {
  value: string | number;
  onChange: (v: string) => void;
  paisCodigo: string | number | '';
  label?: string;
}) {
  const { data: gerentes } = useGerentes(paisCodigo);
  const gp = (gerentes || []).filter((g) => g.codigo?.toUpperCase().startsWith('GP'));
  const val = value ? String(value) : '';
  const faltante = !!val && !gp.some((g) => g.nombre === val);
  return (
    <FormControl fullWidth size="small" disabled={!paisCodigo}>
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={val} onChange={(e) => onChange(String(e.target.value))}>
        {faltante && <MenuItem value={val}>{val} (actual)</MenuItem>}
        {gp.map((g) => (
          <MenuItem key={g.id} value={g.nombre}>{g.codigo} — {g.nombre}</MenuItem>
        ))}
        {gp.length === 0 && !faltante && (
          <MenuItem value="" disabled>Sin gerentes con código GP…</MenuItem>
        )}
      </Select>
      {!paisCodigo && <FormHelperText>Seleccione primero el país</FormHelperText>}
    </FormControl>
  );
}

/**
 * LineaReadOnly — Muestra la línea (nombre visible, nunca ID crudo) en solo lectura.
 * Usada para `DIM_Gerente.linea_id`: se conserva por compatibilidad ("línea principal
 * heredada"), pero la fuente de verdad de las líneas de un gerente pasó a ser
 * `DIM_GerenteLinea` (ver GerenteLineasEditor).
 */
function LineaReadOnly({ lineaId, paisCodigo, label }: {
  lineaId: string | number | '';
  paisCodigo: string | number | '';
  label: string;
}) {
  const { data: lineas } = useLineas(paisCodigo);
  const l = (lineas || []).find((x) => String(x.id) === String(lineaId));
  return (
    <TextField
      fullWidth size="small" label={label}
      value={l ? `${l.codigo} — ${l.nombre}` : (lineaId ? String(lineaId) : '—')}
      InputProps={{ readOnly: true }}
      disabled
    />
  );
}

/**
 * GerenteLineasEditor — Selector múltiple de líneas de un gerente, respaldado por
 * `DIM_GerenteLinea` (Tarea 1) vía `GET/PUT /admin/gerentes/{id}/lineas`.
 *
 * Es un mini-formulario AUTOCONTENIDO con su propio botón "Guardar líneas": el PUT
 * reemplaza el conjunto completo (no se puede mezclar con el PUT de los demás campos
 * del gerente, que va a un endpoint distinto).
 */
function GerenteLineasEditor({ gerenteId, paisCodigo }: {
  gerenteId: number | undefined;
  paisCodigo: string | number | '';
}) {
  const qc = useQueryClient();
  const { data: lineas } = useLineas(paisCodigo);
  const [selected, setSelected] = useState<number[]>([]);
  const [cargado, setCargado] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    setCargado(false);
    setSelected([]);
    if (!gerenteId) return;
    api.get(`/admin/gerentes/${gerenteId}/lineas`)
      .then((r) => setSelected(r.data?.lineas || []))
      .finally(() => setCargado(true));
  }, [gerenteId]);

  const saveMut = useMutation({
    mutationFn: () => api.put(`/admin/gerentes/${gerenteId}/lineas`, { lineas: selected }),
    onSuccess: () => { setMsg('Líneas guardadas'); qc.invalidateQueries({ queryKey: ['gerentes'] }); },
    onError: (e: any) => setMsg(`Error: ${e.response?.data?.detail || e.message}`),
  });

  if (!gerenteId) return null;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <FormControl fullWidth size="small" disabled={!cargado}>
        <InputLabel>Líneas asignadas</InputLabel>
        <Select
          multiple
          label="Líneas asignadas"
          value={selected}
          onChange={(e) => {
            const v = e.target.value;
            setSelected(typeof v === 'string' ? v.split(',').map(Number) : (v as number[]));
          }}
          renderValue={(sel: number[]) =>
            sel.length === 0
              ? '— Sin líneas asignadas —'
              : (lineas || []).filter((l) => sel.includes(l.id))
                  .map((l) => `${l.codigo} — ${l.nombre}`).join(', ')
          }
        >
          {(lineas || []).map((l) => (
            <MenuItem key={l.id} value={l.id}>
              <Checkbox size="small" checked={selected.includes(l.id)} />
              {l.codigo} — {l.nombre}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <Button size="small" variant="outlined" disabled={saveMut.isPending || !cargado}
          onClick={() => saveMut.mutate()}>
          {saveMut.isPending ? <CircularProgress size={16} /> : 'Guardar líneas'}
        </Button>
        {msg && (
          <Typography variant="caption" color={msg.startsWith('Error') ? 'error' : 'success.main'}>{msg}</Typography>
        )}
      </Box>
    </Box>
  );
}

// ── Botón de importación desde Excel ──────────────────────────────────
/**
 * ImportButton — Botón que abre un selector de archivo Excel.
 * Al seleccionar el archivo lo sube al endpoint /admin/{endpoint}/importar.
 * Solo se muestra en tabs que tienen ese endpoint implementado en el backend.
 */
function ImportButton({ endpoint, label }: { endpoint: string; label: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const [msg, setMsg] = useState('');
  const qc = useQueryClient();

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      await api.post(`/admin/${endpoint}/importar`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMsg('Importación exitosa');
      qc.invalidateQueries({ queryKey: [endpoint] });
    } catch (err: any) {
      setMsg(`Error: ${err.response?.data?.detail || err.message}`);
    }
    e.target.value = '';
  };

  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}>
      <input type="file" accept=".xlsx,.xls,.csv" ref={ref} style={{ display: 'none' }} onChange={handleFile} />
      <Tooltip title={`Importar ${label} desde Excel (.xlsx)`}>
        <Button startIcon={<Upload />} size="small" variant="outlined" color="secondary"
          onClick={() => ref.current?.click()}>
          Importar
        </Button>
      </Tooltip>
      {msg && (
        <Alert severity={msg.startsWith('Error') ? 'error' : 'success'} sx={{ py: 0 }}
          onClose={() => setMsg('')}>{msg}</Alert>
      )}
    </Box>
  );
}

// ── Definición de campos de formulario ───────────────────────────────
type FieldDef = {
  key: string;
  label: string;
  type?: string;
  options?: string[];
  freeSoloFrom?: string; // key: Autocomplete con opciones = valores distintos ya usados en esa columna (dropdown + escribir nuevo)
  optionsEspecialidad?: boolean; // Autocomplete cuyas opciones son las especialidades ACTIVAS del catálogo (freeSolo)
  isPais?: boolean;    // true = usar PaisSelector en vez de TextField
  isLinea?: boolean;   // true = usar LineaSelector (filtrado por pais_codigo del mismo form)
  isGerente?: boolean; // true = usar GerenteSelector (filtrado por pais_codigo del mismo form)
  isGerenteProducto?: boolean; // true = usar GerenteProductoSelector (DIM_Gerente con código GP*)
  isLineaReadOnly?: boolean;   // true = mostrar la línea en solo lectura (nombre visible, nunca ID)
  isLineasGerente?: boolean;   // true = usar GerenteLineasEditor (DIM_GerenteLinea, GET/PUT propios)
};

// ── Pestaña genérica de catálogo ──────────────────────────────────────
/**
 * CatalogoTab — Componente genérico para mostrar y gestionar cualquier catálogo.
 *
 * Props:
 * - endpoint: ruta relativa de la API (e.g. "paises", "rms")
 * - columns: columnas a mostrar en la tabla
 * - title: título del catálogo
 * - addFields: campos del formulario de creación
 * - editFields: campos del formulario de edición (si difieren del de creación)
 * - importable: true si el backend tiene endpoint /importar para este catálogo
 */
function CatalogoTab({
  endpoint, columns, title, addFields, editFields, toggleActive = false, extraActions, paisFilter, showWeightTotal = false,
}: {
  endpoint: string;
  columns: { key: string; label: string; align?: 'left' | 'right' | 'center'; render?: (v: any, row: any) => React.ReactNode }[];
  title: string;
  addFields?: FieldDef[];
  editFields?: FieldDef[];
  toggleActive?: boolean;
  extraActions?: (row: any, refetch: () => void) => React.ReactNode;
  paisFilter?: string | '';
  showWeightTotal?: boolean;
}) {
  const qc = useQueryClient();
  const { data: paises } = usePaises();
  const [openNew, setOpenNew] = useState(false);
  const [openEdit, setOpenEdit] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [editItem, setEditItem] = useState<any>(null);
  const [msg, setMsg] = useState('');

  const fields = addFields || [];
  const eFields = editFields || addFields || [];

  const { data, isLoading, refetch } = useQuery({
    queryKey: [endpoint, paisFilter],
    queryFn: () => api.get(`/admin/${endpoint}`, {
      params: paisFilter ? { pais_codigo: paisFilter } : {},
    }).then((r) => r.data),
    retry: 1,
  });

  // Especialidades ACTIVAS del sistema (para campos que se eligen del catálogo, ej. Área Terapéutica).
  const { data: especialidades = [] } = useQuery<{ nombre: string }[]>({
    queryKey: ['geo-especialidades-activas'],
    queryFn: () => api.get('/categorizacion/geo/especialidades').then((r) => r.data),
    staleTime: 60_000,
  });

  // Los campos opcionales vacíos ("") rompen la validación de Pydantic (int/date).
  // Se omiten del payload → el backend los toma como no enviados (None).
  const limpiar = (f: Record<string, any>) =>
    Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '' && v !== null && v !== undefined));

  const createMutation = useMutation({
    mutationFn: () => api.post(`/admin/${endpoint}`, limpiar(form)),
    onSuccess: () => { setOpenNew(false); setForm({}); setMsg('Creado correctamente'); qc.invalidateQueries({ queryKey: [endpoint] }); },
    onError: (e: any) => setMsg(`Error: ${e.response?.data?.detail || e.message}`),
  });

  const updateMutation = useMutation({
    mutationFn: () => api.put(`/admin/${endpoint}/${editItem?.id}`, limpiar(form)),
    onSuccess: () => { setOpenEdit(false); setForm({}); setEditItem(null); setMsg('Actualizado'); qc.invalidateQueries({ queryKey: [endpoint] }); },
    onError: (e: any) => setMsg(`Error: ${e.response?.data?.detail || e.message}`),
  });

  const toggleMutation = useMutation({
    mutationFn: (row: any) => api.put(`/admin/${endpoint}/${row.id}`, { activo: !row.activo }),
    onSuccess: () => { setMsg('Estado actualizado'); qc.invalidateQueries({ queryKey: [endpoint] }); },
    onError: (e: any) => setMsg(`Error: ${e.response?.data?.detail || e.message}`),
  });

  const activarMutation = useMutation({
    mutationFn: (row: any) => api.put(`/admin/${endpoint}/${row.id}`, { activo: true }),
    onSuccess: () => { setMsg('Registro activado'); qc.invalidateQueries({ queryKey: [endpoint] }); },
    onError: (e: any) => setMsg(`Error: ${e.response?.data?.detail || e.message}`),
  });

  const handleEdit = (row: any) => {
    setEditItem(row);
    const f: Record<string, string> = {};
    eFields.forEach((field) => { f[field.key] = row[field.key] ?? ''; });
    setForm(f);
    setOpenEdit(true);
  };

  const items: any[] = Array.isArray(data) ? data : (data?.items ?? []);

  // Agrega columna de acciones al final
  const allColumns = [
    ...columns,
    {
      key: '__actions', label: 'Acciones',
      render: (_: any, row: any) => (
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          {eFields.length > 0 && (
            <Tooltip title="Editar">
              <IconButton size="small" color="primary" onClick={() => handleEdit(row)}>
                <Edit fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {toggleActive ? (
            <Tooltip title={row.activo ? 'Desactivar' : 'Activar'}>
              <IconButton size="small" color={row.activo ? 'warning' : 'success'}
                onClick={() => toggleMutation.mutate(row)}>
                {row.activo ? <ToggleOff fontSize="small" /> : <ToggleOn fontSize="small" />}
              </IconButton>
            </Tooltip>
          ) : (
            !row.activo && (
              <Tooltip title="Activar">
                <IconButton size="small" color="success" onClick={() => activarMutation.mutate(row)}>
                  <ToggleOn fontSize="small" />
                </IconButton>
              </Tooltip>
            )
          )}
          {extraActions && extraActions(row, refetch)}
        </Box>
      ),
    },
  ];

  // Renderiza un campo del formulario según su tipo
  const renderField = (f: FieldDef) => (
    <Grid item xs={12} sm={f.isLineasGerente ? 12 : 6} key={f.key}>
      {f.isLineasGerente ? (
        // Campo especial: selector múltiple de líneas de un gerente (DIM_GerenteLinea).
        // Solo tiene sentido en Editar (necesita el id del registro ya existente).
        <GerenteLineasEditor
          gerenteId={editItem?.id}
          paisCodigo={form['pais_codigo'] || editItem?.pais_codigo || ''}
        />
      ) : f.isLineaReadOnly ? (
        // Campo especial: línea principal heredada, en solo lectura (nombre visible)
        <LineaReadOnly
          lineaId={form[f.key] || ''}
          paisCodigo={form['pais_codigo'] || editItem?.pais_codigo || ''}
          label={f.label}
        />
      ) : f.isPais ? (
        // Campo especial: selector de país con formato "CR — Costa Rica"
        <PaisSelector value={form[f.key] || ''} onChange={(v) => setForm({ ...form, [f.key]: v }) } />
      ) : f.isLinea ? (
        // Campo especial: selector de línea con formato "CAR — Cardiovascular" (nunca ID crudo)
        <LineaSelector
          value={form[f.key] || ''}
          paisCodigo={form['pais_codigo'] || ''}
          onChange={(v) => setForm({ ...form, [f.key]: v })}
        />
      ) : f.isGerente ? (
        // Campo especial: selector de gerente con formato "GD001 — Juan Pérez (DISTRITO)" (nunca ID crudo)
        <GerenteSelector
          value={form[f.key] || ''}
          paisCodigo={form['pais_codigo'] || ''}
          onChange={(v) => setForm({ ...form, [f.key]: v })}
        />
      ) : f.isGerenteProducto ? (
        // Campo especial: gerente de producto desde DIM_Gerente filtrado por código "GP*"
        <GerenteProductoSelector
          value={form[f.key] || ''}
          paisCodigo={form['pais_codigo'] || ''}
          onChange={(v) => setForm({ ...form, [f.key]: v })}
        />
      ) : f.options ? (
        <FormControl fullWidth size="small">
          <InputLabel>{f.label}</InputLabel>
          <Select label={f.label} value={form[f.key] || ''}
            onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}>
            {f.options.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
          </Select>
        </FormControl>
      ) : f.optionsEspecialidad ? (
        // Desplegable con las especialidades ACTIVAS del catálogo (permite elegir o escribir una nueva).
        <Autocomplete
          freeSolo size="small"
          options={especialidades.map((e) => e.nombre).sort((a, b) => a.localeCompare(b))}
          value={form[f.key] || ''}
          onChange={(_, v) => setForm({ ...form, [f.key]: v ?? '' })}
          onInputChange={(_, v, reason) => { if (reason === 'input') setForm({ ...form, [f.key]: v }); }}
          renderInput={(params) => <TextField {...params} label={f.label} />}
        />
      ) : f.freeSoloFrom ? (
        // Desplegable con los valores ya usados en esa columna (permite elegir o escribir uno nuevo).
        <Autocomplete
          freeSolo size="small"
          options={(() => {
            const seen = new Set<string>(); const out: string[] = [];
            for (const r of ((data as any[]) ?? [])) {
              const v = String(r?.[f.freeSoloFrom as string] ?? '').trim();
              if (v && !seen.has(v.toLowerCase())) { seen.add(v.toLowerCase()); out.push(v); }
            }
            return out.sort((a, b) => a.localeCompare(b));
          })()}
          value={form[f.key] || ''}
          onChange={(_, v) => setForm({ ...form, [f.key]: v ?? '' })}
          onInputChange={(_, v, reason) => { if (reason === 'input') setForm({ ...form, [f.key]: v }); }}
          renderInput={(params) => <TextField {...params} label={f.label} />}
        />
      ) : (
        <TextField fullWidth size="small" label={f.label} type={f.type || 'text'}
          value={form[f.key] || ''}
          onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
      )}
    </Grid>
  );

  return (
    <Box>
      {/* Barra de título y acciones */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="h6" fontWeight={600}>{title}</Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
          <Button startIcon={<Refresh />} size="small" onClick={() => refetch()}>Actualizar</Button>
          {fields.length > 0 && (
            <Button variant="contained" startIcon={<Add />} size="small" onClick={() => { setForm({}); setOpenNew(true); }}>
              Nuevo
            </Button>
          )}
        </Box>
      </Box>

      {msg && <Alert severity={msg.startsWith('Error') ? 'error' : 'success'} sx={{ mb: 2 }} onClose={() => setMsg('')}>{msg}</Alert>}

      {/* Tabla de datos */}
      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>
      ) : (
        <TableContainer component={Paper} elevation={1} sx={{ borderRadius: 2 }}>
          <Table size="small">
            <TableHead sx={{ bgcolor: 'primary.main' }}>
              <TableRow>
                {allColumns.map((c) => (
                  <TableCell key={c.key} align={(c as any).align || 'left'} sx={{ color: 'white', fontWeight: 700 }}>{c.label}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={allColumns.length} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                    Sin registros
                  </TableCell>
                </TableRow>
              ) : (
                items.map((row: any, i: number) => (
                  <TableRow key={i} hover>
                    {allColumns.map((c) => (
                      <TableCell key={c.key} align={(c as any).align || 'left'}>
                        {c.render
                          ? c.render(row[c.key], row)
                          : c.key === 'pais_codigo'
                            ? <PaisLabel paisCodigo={row.pais_codigo} paises={paises} />
                            : (row[c.key] ?? '—')}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              )}
            </TableBody>
            {showWeightTotal && items.length > 0 && (() => {
              const total = items.reduce((acc: number, r: any) => acc + (Number(r.ponderacion_pct) || 0), 0);
              const weightColIdx = columns.findIndex((c) => c.key === 'ponderacion_pct');
              return (
                <TableFooter>
                  <TableRow sx={{ bgcolor: 'primary.dark' }}>
                    {allColumns.map((c, i) => (
                      <TableCell key={c.key} align={(c as any).align || 'left'} sx={{ color: 'white', fontWeight: 700, py: 0.8 }}>
                        {i === weightColIdx
                          ? `Total: ${total} pts`
                          : i === 0 ? 'TOTAL' : ''}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableFooter>
              );
            })()}
          </Table>
        </TableContainer>
      )}

      {/* Dialog: Crear nuevo registro */}
      <Dialog open={openNew} onClose={() => setOpenNew(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Nuevo {title}</DialogTitle>
        <DialogContent><Grid container spacing={2} sx={{ mt: 0.5 }}>{fields.map(renderField)}</Grid></DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenNew(false)}>Cancelar</Button>
          <Button variant="contained" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>Guardar</Button>
        </DialogActions>
      </Dialog>

      {/* Dialog: Editar registro */}
      <Dialog open={openEdit} onClose={() => setOpenEdit(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Editar {title}</DialogTitle>
        <DialogContent><Grid container spacing={2} sx={{ mt: 0.5 }}>{eFields.map(renderField)}</Grid></DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenEdit(false)}>Cancelar</Button>
          <Button variant="contained" onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>Actualizar</Button>
        </DialogActions>
      </Dialog>

    </Box>
  );
}

// ── Pestaña especial: Rangos de Puntuación ────────────────────────────
/**
 * RangosIndicadorTab — Gestión de rangos KPI→Puntos.
 *
 * Permite seleccionar un indicador y un país para ver, agregar
 * y eliminar los rangos de puntuación configurados.
 * Los rangos definen cuántos puntos obtiene un RM según su
 * valor real en ese indicador (e.g. 87% cobertura → 80 puntos).
 */
function RangosIndicadorTab() {
  const [selectedIndicadorId, setSelectedIndicadorId] = useState<number | ''>('');
  const selectedPaisId = useCicloStore((s) => s.paisCodigo) || '';
  const [open, setOpen] = useState(false);
  const [openDel, setOpenDel] = useState(false);
  const [openEdit, setOpenEdit] = useState(false);
  const [delItem, setDelItem] = useState<any>(null);
  const [editItem, setEditItem] = useState<any>(null);
  const [form, setForm] = useState({ rango_desde: '', rango_hasta: '', puntos: '', descripcion: '' });
  const [editForm, setEditForm] = useState({ rango_desde: '', rango_hasta: '', puntos: '', descripcion: '' });
  const [msg, setMsg] = useState('');
  const qc = useQueryClient();

  // El país ahora viene del contexto global (CicloPaisHeader) — al cambiar, se limpia el
  // indicador seleccionado (que pertenecía al país anterior).
  useEffect(() => { setSelectedIndicadorId(''); }, [selectedPaisId]);

  const { data: _indRaw } = useQuery({
    queryKey: ['indicadores-rangos', selectedPaisId],
    queryFn: () => api.get('/admin/indicadores', {
      params: { size: 200, ...(selectedPaisId ? { pais_codigo: selectedPaisId } : {}) },
    }).then((r) => r.data),
    enabled: !!selectedPaisId,
  });
  // El endpoint /admin/indicadores devuelve {items:[...], total:N} — normalizar a array
  const indicadores: any[] = Array.isArray(_indRaw) ? _indRaw : (_indRaw?.items ?? []);

  const { data: rangos, isLoading, refetch } = useQuery({
    queryKey: ['rangos', selectedIndicadorId, selectedPaisId],
    queryFn: () => selectedIndicadorId
      ? api.get(`/admin/indicadores/${selectedIndicadorId}/tabla`, {
          params: selectedPaisId ? { pais_codigo: selectedPaisId } : {},
        }).then((r) => r.data)
      : Promise.resolve([]),
    enabled: !!selectedIndicadorId,
  });

  const createMutation = useMutation({
    mutationFn: () => api.post(`/admin/indicadores/${selectedIndicadorId}/tabla`, {
      indicador_id: selectedIndicadorId, pais_codigo: selectedPaisId,
      rango_desde: parseFloat(form.rango_desde), rango_hasta: parseFloat(form.rango_hasta),
      puntos: parseFloat(form.puntos), descripcion: form.descripcion || null,
    }),
    onSuccess: () => {
      setOpen(false);
      setForm({ rango_desde: '', rango_hasta: '', puntos: '', descripcion: '' });
      setMsg('Rango creado');
      qc.invalidateQueries({ queryKey: ['rangos'] });
    },
    onError: (e: any) => setMsg(`Error: ${e.response?.data?.detail || e.message}`),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/admin/indicadores/${selectedIndicadorId}/tabla/${delItem?.id}`),
    onSuccess: () => { setOpenDel(false); setDelItem(null); setMsg('Rango eliminado'); qc.invalidateQueries({ queryKey: ['rangos'] }); },
    onError: (e: any) => setMsg(`Error: ${e.response?.data?.detail || e.message}`),
  });

  const updateMutation = useMutation({
    mutationFn: () => api.put(`/admin/indicadores/${selectedIndicadorId}/tabla/${editItem?.id}`, {
      indicador_id: selectedIndicadorId, pais_codigo: selectedPaisId,
      rango_desde: parseFloat(editForm.rango_desde), rango_hasta: parseFloat(editForm.rango_hasta),
      puntos: parseFloat(editForm.puntos), descripcion: editForm.descripcion || null,
    }),
    onSuccess: () => {
      setOpenEdit(false); setEditItem(null);
      setMsg('Rango actualizado');
      qc.invalidateQueries({ queryKey: ['rangos'] });
    },
    onError: (e: any) => setMsg(`Error: ${e.response?.data?.detail || e.message}`),
  });

  const handleOpenEdit = (r: any) => {
    setEditItem(r);
    setEditForm({
      rango_desde: String(r.rango_desde),
      rango_hasta: String(r.rango_hasta),
      puntos: String(r.puntos),
      descripcion: r.descripcion ?? '',
    });
    setOpenEdit(true);
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
        <Box>
          <Typography variant="h6" fontWeight={600}>Rangos de Puntuación</Typography>
          <Typography variant="caption" color="text.secondary">
            Los rangos se cargan automáticamente al importar los DIMs (hoja DIM_INDICADOR_TABLA)
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button startIcon={<Refresh />} size="small" onClick={() => refetch()}>Actualizar</Button>
          {selectedIndicadorId && selectedPaisId && (
            <Button variant="contained" startIcon={<Add />} size="small" onClick={() => setOpen(true)}>Nuevo Rango</Button>
          )}
        </Box>
      </Box>

      {msg && <Alert severity={msg.startsWith('Error') ? 'error' : 'success'} sx={{ mb: 2 }} onClose={() => setMsg('')}>{msg}</Alert>}

      {/* Filtro de indicador (el país viene del contexto global — CicloPaisHeader) */}
      <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
        <Box sx={{ flex: 1, minWidth: 260 }}>
          <FormControl fullWidth size="small">
            <InputLabel>Indicador</InputLabel>
            <Select
              label="Indicador"
              value={selectedIndicadorId}
              onChange={(e) => setSelectedIndicadorId(e.target.value as number)}
              disabled={!selectedPaisId}
            >
              {indicadores.map((ind: any) => (
                <MenuItem key={ind.id} value={ind.id}>
                  {ind.codigo} — {ind.nombre}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      </Box>

      <TableContainer component={Paper} elevation={1} sx={{ borderRadius: 2 }}>
        <Table size="small">
          <TableHead sx={{ bgcolor: 'primary.main' }}>
            <TableRow>
              {['Código Indicador', 'Peso (%)', 'Resultado', 'Factor', ''].map((h) => (
                <TableCell key={h} align="center" sx={{ color: 'white', fontWeight: 700 }}>{h}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {!selectedIndicadorId ? (
              <TableRow><TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                Selecciona un país e indicador para ver los rangos
              </TableCell></TableRow>
            ) : isLoading ? (
              <TableRow><TableCell colSpan={5} align="center"><CircularProgress size={24} /></TableCell></TableRow>
            ) : (rangos || []).length === 0 ? (
              <TableRow><TableCell colSpan={5} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                Sin rangos configurados
              </TableCell></TableRow>
            ) : (() => {
              const selInd = indicadores.find((i: any) => i.id === selectedIndicadorId);
              const rows = [...(rangos || [])].sort((a: any, b: any) => Number(a.rango_desde) - Number(b.rango_desde));
              return rows.map((r: any, idx: number) => {
                const isFirst = idx === 0;
                const resultadoLabel = isFirst
                  ? `< ${Number(rows[1]?.rango_desde ?? r.rango_hasta).toFixed(0)}`
                  : Number(r.rango_desde).toFixed(0);
                return (
                  <TableRow key={r.id} hover>
                    <TableCell align="center" sx={{ fontFamily: 'monospace', fontSize: 13 }}>{selInd?.codigo ?? '—'}</TableCell>
                    <TableCell align="center">{selInd?.ponderacion_pct ?? '—'}</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 600 }}>{resultadoLabel}</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 700, color: Number(r.puntos) >= 1 ? 'success.main' : 'text.primary' }}>
                      {Number(r.puntos).toFixed(2)}
                    </TableCell>
                    <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>
                      <Tooltip title="Editar rango">
                        <IconButton size="small" color="primary" onClick={() => handleOpenEdit(r)}>
                          <Edit fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Eliminar rango">
                        <IconButton size="small" color="error" onClick={() => { setDelItem(r); setOpenDel(true); }}>
                          <Delete fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              });
            })()}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Nuevo Rango de Puntuación</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            {[
              { key: 'rango_desde', label: 'Resultado Desde' },
              { key: 'rango_hasta', label: 'Resultado Hasta' },
              { key: 'puntos', label: 'Factor' },
              { key: 'descripcion', label: 'Descripción (opcional)' },
            ].map((f) => (
              <Grid item xs={12} sm={6} key={f.key}>
                <TextField fullWidth size="small" label={f.label}
                  type={f.key !== 'descripcion' ? 'number' : 'text'}
                  value={(form as any)[f.key]}
                  onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} />
              </Grid>
            ))}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>Guardar</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={openDel} onClose={() => setOpenDel(false)}>
        <DialogTitle>Confirmar eliminación</DialogTitle>
        <DialogContent>
          <Typography>¿Eliminar rango con Resultado <strong>{Number(delItem?.rango_desde ?? 0).toFixed(0)}</strong> → Factor <strong>{Number(delItem?.puntos ?? 0).toFixed(2)}</strong>?</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDel(false)}>Cancelar</Button>
          <Button variant="contained" color="error" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>Eliminar</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={openEdit} onClose={() => setOpenEdit(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Editar Rango de Puntuación</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            {[
              { key: 'rango_desde', label: 'Resultado Desde' },
              { key: 'rango_hasta', label: 'Resultado Hasta' },
              { key: 'puntos', label: 'Factor' },
              { key: 'descripcion', label: 'Descripción (opcional)' },
            ].map((f) => (
              <Grid item xs={12} sm={6} key={f.key}>
                <TextField fullWidth size="small" label={f.label}
                  type={f.key !== 'descripcion' ? 'number' : 'text'}
                  value={(editForm as any)[f.key]}
                  onChange={(e) => setEditForm({ ...editForm, [f.key]: e.target.value })} />
              </Grid>
            ))}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenEdit(false)}>Cancelar</Button>
          <Button variant="contained" onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending}>Guardar Cambios</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Botones Cerrar / Abrir ciclo ──────────────────────────────────────
/**
 * CicloStateButtons — Renderiza botones Cerrar / Abrir en la fila del ciclo.
 * Muestra diálogo de confirmación antes de actuar.
 * Al abrir un ciclo cerrado, lanza automáticamente el recálculo de ese ciclo.
 */
function CicloStateButtons({ row, refetch }: { row: any; refetch: () => void }) {
  const [confirm, setConfirm] = useState<null | 'cerrar' | 'abrir'>(null);
  const [msg, setMsg] = useState('');
  const [recalcMsg, setRecalcMsg] = useState('');
  const qc = useQueryClient();

  const cerrarMutation = useMutation({
    mutationFn: () => api.patch(`/admin/ciclos/${row.id}/cerrar`),
    onSuccess: (res: any) => {
      setConfirm(null);
      setMsg(res.data?.message || 'Ciclo cerrado');
      qc.invalidateQueries({ queryKey: ['ciclos'] });
      refetch();
    },
    onError: (e: any) => { setConfirm(null); setMsg(`Error: ${e.response?.data?.detail || e.message}`); },
  });

  const abrirMutation = useMutation({
    mutationFn: () => api.patch(`/admin/ciclos/${row.id}/abrir`),
    onSuccess: async (res: any) => {
      setConfirm(null);
      setMsg(res.data?.message || 'Ciclo abierto');
      qc.invalidateQueries({ queryKey: ['ciclos'] });
      refetch();
      // Recalcular automáticamente al reabrir
      try {
        const rc = await api.post(`/etl/recalcular/${row.id}`);
        const d = rc.data;
        if (d?.abortado) {
          setRecalcMsg(`⚠ Recálculo abortado: ${d.motivo}`);
        } else {
          setRecalcMsg(`✓ Recálculo OK — ${d?.filas_kpi_actualizadas ?? 0} KPI, ${d?.rankings_generados ?? 0} rankings`);
        }
      } catch (e: any) {
        setRecalcMsg(`Aviso: recálculo no se pudo disparar (${e.response?.data?.detail || e.message})`);
      }
    },
    onError: (e: any) => { setConfirm(null); setMsg(`Error: ${e.response?.data?.detail || e.message}`); },
  });

  return (
    <>
      {/* Botón Cerrar (solo si está abierto) */}
      {!row.cerrado && (
        <Tooltip title="Cerrar ciclo (snapshot inmutable)">
          <IconButton size="small" color="error" onClick={() => setConfirm('cerrar')}>
            <Lock fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
      {/* Botón Abrir (solo si está cerrado) */}
      {row.cerrado && (
        <Tooltip title="Reabrir ciclo para edición y recálculo">
          <IconButton size="small" color="success" onClick={() => setConfirm('abrir')}>
            <LockOpen fontSize="small" />
          </IconButton>
        </Tooltip>
      )}

      {/* Alertas inline */}
      {(msg || recalcMsg) && (
        <Box sx={{ position: 'fixed', bottom: 24, right: 24, zIndex: 2000, display: 'flex', flexDirection: 'column', gap: 1 }}>
          {msg && (
            <Alert severity={msg.startsWith('Error') ? 'error' : 'success'} onClose={() => setMsg('')}>
              {msg}
            </Alert>
          )}
          {recalcMsg && (
            <Alert severity={recalcMsg.startsWith('⚠') || recalcMsg.startsWith('Aviso') ? 'warning' : 'success'}
              onClose={() => setRecalcMsg('')}>
              {recalcMsg}
            </Alert>
          )}
        </Box>
      )}

      {/* Diálogo de confirmación */}
      <Dialog open={!!confirm} onClose={() => setConfirm(null)} maxWidth="xs">
        <DialogTitle>
          {confirm === 'cerrar' ? '🔒 Cerrar ciclo' : '🔓 Reabrir ciclo'}
        </DialogTitle>
        <DialogContent>
          <Typography>
            {confirm === 'cerrar'
              ? <>¿Cerrar el ciclo <strong>{row.nombre}</strong>? Una vez cerrado quedará como snapshot histórico. Puedes reabrirlo si necesitas corregir datos.</>
              : <>¿Reabrir el ciclo <strong>{row.nombre}</strong>? Se ejecutará el recálculo automáticamente para actualizar puntajes y rankings.</>
            }
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)}>Cancelar</Button>
          <Button
            variant="contained"
            color={confirm === 'cerrar' ? 'error' : 'success'}
            onClick={() => confirm === 'cerrar' ? cerrarMutation.mutate() : abrirMutation.mutate()}
            disabled={cerrarMutation.isPending || abrirMutation.isPending}
          >
            {confirm === 'cerrar' ? 'Cerrar ciclo' : 'Abrir y recalcular'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}


// ── Tab genérico de DIM con filtro de País ────────────────────────────
function DimTabWithPais({ tabConfig }: { tabConfig: (typeof TABS_DIM)[0] }) {
  // El país viene del contexto global (CicloPaisHeader, arriba de todos los módulos) — ya
  // no tiene un selector propio duplicado.
  const paisCodigo = useCicloStore((s) => s.paisCodigo) || '';
  const { data: paises } = usePaises();

  return (
    <Box>
      {/* País activo (informativo — se cambia desde el selector superior) */}
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 2,
                 bgcolor: SUPERFICIE_3, borderRadius: 2, px: 2, py: 1.5 }}>
        <Typography variant="body2" color="primary.main" fontWeight={600}>
          {tabConfig.label} — {paisCodigo
            ? (paises || []).find((p: any) => p.codigo === paisCodigo)
              ? `${(paises as any[]).find((p: any) => p.codigo === paisCodigo).codigo} — ${(paises as any[]).find((p: any) => p.codigo === paisCodigo).nombre}`
              : ''
            : 'Todos los países'}
        </Typography>
      </Box>
      {/* Tabla del catálogo */}
      <CatalogoTab
        key={`${tabConfig.endpoint}-${paisCodigo}`}
        endpoint={tabConfig.endpoint}
        columns={tabConfig.columns as any}
        title={tabConfig.label}
        addFields={(tabConfig as any).addFields}
        editFields={(tabConfig as any).editFields}
        paisFilter={paisCodigo}
        toggleActive
        showWeightTotal={tabConfig.endpoint === 'indicadores'}
      />
    </Box>
  );
}


// ── Tab dedicado: Ciclos por País ──────────────────────────────────────
/** ISO local (YYYY-MM-DD) sin desfase de zona horaria (evita el corrimiento de toISOString). */
function isoLocal(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
/** Días laborables (lun-vie) entre dos fechas ISO, excluyendo los feriados dados. Preview en vivo;
 *  el backend recalcula el valor autoritativo al guardar. */
function contarDiasHabiles(inicioStr: string, finStr: string, feriados: Set<string>): number {
  if (!inicioStr || !finStr) return 0;
  const inicio = new Date(inicioStr + 'T00:00:00');
  const fin = new Date(finStr + 'T00:00:00');
  if (isNaN(inicio.getTime()) || isNaN(fin.getTime()) || fin < inicio) return 0;
  let total = 0;
  const d = new Date(inicio);
  while (d <= fin) {
    const dow = d.getDay();  // 0=domingo, 6=sábado
    if (dow !== 0 && dow !== 6 && !feriados.has(isoLocal(d))) total++;
    d.setDate(d.getDate() + 1);
  }
  return total;
}

/**
 * CiclosPorPaisTab — Mantenimiento de ciclos por país: crear/editar (con días laborables
 * calculados automáticamente de las fechas menos feriados), cerrar/abrir, y gestión de
 * los días no laborables (feriados) que se excluyen del cálculo.
 */
function CiclosPorPaisTab() {
  // El país viene del contexto global (CicloPaisHeader, arriba de todos los módulos) — ya
  // no tiene un selector propio duplicado.
  const paisCodigo = useCicloStore((s) => s.paisCodigo) || '';
  const { data: paises } = usePaises();
  const qc = useQueryClient();

  const { data: ciclos, isLoading, refetch } = useQuery({
    queryKey: ['ciclos', paisCodigo],
    queryFn: () =>
      api.get('/admin/ciclos', { params: { ...(paisCodigo && { pais_codigo: paisCodigo }) } }).then(r => r.data),
  });

  // Feriados / días no laborables del país seleccionado.
  const { data: feriados } = useQuery({
    queryKey: ['feriados', paisCodigo],
    queryFn: () => api.get('/admin/feriados', { params: { pais_codigo: paisCodigo } }).then(r => r.data),
    enabled: !!paisCodigo,
  });
  const feriadosRows: any[] = feriados || [];
  const feriadosSet = new Set<string>(feriadosRows.map((f: any) => f.fecha));

  const rows: any[] = ciclos || [];
  const paisNombre = (codigo: string) => {
    const p = (paises || []).find((x: any) => x.codigo === codigo);
    return p ? `${p.codigo} — ${p.nombre}` : String(codigo);
  };

  // ── Formulario de ciclo (crear / editar) ──
  const vacio = {
    id: null as number | null, pais_codigo: '', anio: new Date().getFullYear(),
    numero: 1, nombre: '', nombre_canonico: '', fecha_inicio: '', fecha_fin: '',
  };
  const [form, setForm] = useState<typeof vacio>(vacio);
  const [abierto, setAbierto] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const setF = (k: keyof typeof vacio, v: any) => setForm((f) => ({ ...f, [k]: v }));
  const errText = (e: any, fb: string) => e?.response?.data?.detail || fb;

  const abrirNuevo = () => { setForm({ ...vacio, pais_codigo: paisCodigo || '' }); setAbierto(true); };
  const abrirEditar = (row: any) => {
    setForm({
      id: row.id, pais_codigo: row.pais_codigo, anio: row.anio, numero: row.numero,
      nombre: row.nombre, nombre_canonico: row.nombre_canonico || '',
      fecha_inicio: row.fecha_inicio, fecha_fin: row.fecha_fin,
    });
    setAbierto(true);
  };

  // Días laborables en vivo (con los feriados del país del formulario).
  const diasPreview = contarDiasHabiles(form.fecha_inicio, form.fecha_fin, feriadosSet);
  const formValido = !!(form.pais_codigo && form.nombre && form.fecha_inicio && form.fecha_fin
    && form.fecha_fin >= form.fecha_inicio);

  const guardarCiclo = useMutation({
    mutationFn: () => {
      const body = {
        pais_codigo: form.pais_codigo, anio: Number(form.anio), numero: Number(form.numero),
        nombre: form.nombre, nombre_canonico: form.nombre_canonico || null,
        fecha_inicio: form.fecha_inicio, fecha_fin: form.fecha_fin,
      };
      return form.id ? api.put(`/admin/ciclos/${form.id}`, body) : api.post('/admin/ciclos', body);
    },
    onSuccess: () => { setAbierto(false); setMsg({ tipo: 'success', texto: 'Ciclo guardado.' }); refetch(); },
    onError: (e: any) => setMsg({ tipo: 'error', texto: errText(e, 'No se pudo guardar el ciclo.') }),
  });

  // ── Feriados (agregar / eliminar) ──
  const [ferFecha, setFerFecha] = useState('');
  const [ferNombre, setFerNombre] = useState('');
  const addFeriado = useMutation({
    mutationFn: () => api.post('/admin/feriados', { pais_codigo: paisCodigo, fecha: ferFecha, nombre: ferNombre || null }),
    onSuccess: () => { setFerFecha(''); setFerNombre(''); qc.invalidateQueries({ queryKey: ['feriados'] }); },
    onError: (e: any) => setMsg({ tipo: 'error', texto: errText(e, 'No se pudo agregar el feriado.') }),
  });
  const delFeriado = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/feriados/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['feriados'] }),
  });

  const findeEnFecha = (iso: string) => { const d = new Date(iso + 'T00:00:00'); return d.getDay() === 0 || d.getDay() === 6; };

  return (
    <Box>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {/* País activo (informativo — se cambia desde el selector superior) + Nuevo ciclo */}
      <Card elevation={1} sx={{ mb: 2, borderRadius: 2 }}>
        <CardContent sx={{ py: '12px !important' }}>
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary">
              {rows.length} ciclo{rows.length !== 1 ? 's' : ''}
              {paisCodigo ? ` — ${paisNombre(String(paisCodigo))}` : ' en todos los países'}
            </Typography>
            <Box sx={{ flexGrow: 1 }} />
            <Button variant="contained" startIcon={<Add />} onClick={abrirNuevo}>Nuevo ciclo</Button>
          </Box>
        </CardContent>
      </Card>

      {/* Días no laborables (feriados) del país — se excluyen de los días laborables */}
      {paisCodigo && (
        <Card variant="outlined" sx={{ mb: 2, bgcolor: SUPERFICIE_2, borderColor: BORDE_FUERTE }}>
          <CardContent sx={{ py: 1.5 }}>
            <Typography variant="subtitle2" fontWeight={700} gutterBottom>
              Días no laborables (feriados) — {paisNombre(String(paisCodigo))}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Fechas entre semana (lun-vie) que NO cuentan como días laborables del ciclo. Los sábados y
              domingos ya se excluyen automáticamente.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mb: feriadosRows.length ? 1.5 : 0 }}>
              <TextField size="small" type="date" label="Fecha" value={ferFecha}
                         InputLabelProps={{ shrink: true }} sx={{ bgcolor: '#fff' }}
                         onChange={(e) => setFerFecha(e.target.value)} />
              <TextField size="small" label="Descripción (opcional)" value={ferNombre} sx={{ bgcolor: '#fff', minWidth: 220 }}
                         onChange={(e) => setFerNombre(e.target.value)} />
              <Button variant="outlined" startIcon={<Add />} disabled={!ferFecha || addFeriado.isPending}
                      onClick={() => addFeriado.mutate()}>Agregar</Button>
              {ferFecha && findeEnFecha(ferFecha) && (
                <Typography variant="caption" color="warning.main">Esa fecha ya es fin de semana.</Typography>
              )}
            </Box>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {feriadosRows.length === 0
                ? <Typography variant="caption" color="text.secondary">Sin feriados configurados.</Typography>
                : feriadosRows.map((f: any) => (
                  <Chip key={f.id} size="small" sx={{ bgcolor: '#fff' }}
                        label={f.nombre ? `${f.fecha} · ${f.nombre}` : f.fecha}
                        onDelete={() => delFeriado.mutate(f.id)} />
                ))}
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Tabla de ciclos */}
      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}><CircularProgress /></Box>
      ) : (
        <TableContainer component={Paper} elevation={2} sx={{ borderRadius: 2 }}>
          <Table size="small">
            <TableHead sx={{ bgcolor: 'primary.main' }}>
              <TableRow>
                {['País', 'N°', 'Nombre', 'Inicio', 'Fin', 'Días lab.', 'Estado', 'Acciones'].map(h => (
                  <TableCell key={h} sx={{ color: 'white', fontWeight: 700 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                    No hay ciclos{paisCodigo ? ' para este país' : ''}
                  </TableCell>
                </TableRow>
              ) : rows.map((row: any) => (
                <TableRow key={row.id} hover sx={{ opacity: row.cerrado ? 0.75 : 1 }}>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{paisNombre(row.pais_codigo)}</TableCell>
                  <TableCell align="center">{row.numero}</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>{row.nombre}</TableCell>
                  <TableCell>{row.fecha_inicio}</TableCell>
                  <TableCell>{row.fecha_fin}</TableCell>
                  <TableCell align="center"><Chip size="small" variant="outlined" label={row.dias_laborables ?? 0} /></TableCell>
                  <TableCell>
                    <Chip
                      label={row.cerrado ? 'Cerrado' : 'Abierto'}
                      color={row.cerrado ? 'error' : 'success'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Tooltip title="Editar ciclo">
                        <IconButton size="small" color="primary" onClick={() => abrirEditar(row)}><Edit fontSize="small" /></IconButton>
                      </Tooltip>
                      <CicloStateButtons row={row} refetch={refetch} />
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Formulario crear / editar ciclo */}
      <Dialog open={abierto} onClose={() => setAbierto(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{form.id ? 'Editar ciclo' : 'Nuevo ciclo'}</DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ mt: 0 }}>
            <Grid item xs={12} sm={6}>
              {form.id ? (
                <TextField fullWidth size="small" label="País" value={paisNombre(form.pais_codigo)} InputProps={{ readOnly: true }} />
              ) : (
                <FormControl fullWidth size="small">
                  <InputLabel>País</InputLabel>
                  <Select label="País" value={form.pais_codigo} onChange={(e) => setF('pais_codigo', e.target.value)}>
                    {(paises || []).map((p: any) => <MenuItem key={p.id} value={p.codigo}>{p.codigo} — {p.nombre}</MenuItem>)}
                  </Select>
                </FormControl>
              )}
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField fullWidth size="small" type="number" label="Año" value={form.anio} onChange={(e) => setF('anio', e.target.value)} />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField fullWidth size="small" type="number" label="N° ciclo" value={form.numero} onChange={(e) => setF('numero', e.target.value)} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Nombre (ej. C03-2026)" value={form.nombre} onChange={(e) => setF('nombre', e.target.value)} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Nombre canónico (opcional)" value={form.nombre_canonico} onChange={(e) => setF('nombre_canonico', e.target.value)} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth size="small" type="date" label="Fecha inicio" InputLabelProps={{ shrink: true }}
                         value={form.fecha_inicio} onChange={(e) => setF('fecha_inicio', e.target.value)} />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth size="small" type="date" label="Fecha fin" InputLabelProps={{ shrink: true }}
                         value={form.fecha_fin} onChange={(e) => setF('fecha_fin', e.target.value)}
                         error={!!(form.fecha_inicio && form.fecha_fin && form.fecha_fin < form.fecha_inicio)}
                         helperText={form.fecha_inicio && form.fecha_fin && form.fecha_fin < form.fecha_inicio ? 'Debe ser posterior al inicio' : ' '} />
            </Grid>
            <Grid item xs={12}>
              <Box sx={{ p: 1.5, bgcolor: 'rgba(46,91,255,0.06)', borderRadius: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box>
                  <Typography variant="body2" fontWeight={700}>Días laborables (calculado)</Typography>
                  <Typography variant="caption" color="text.secondary">Lun-vie entre las fechas, menos los feriados del país</Typography>
                </Box>
                <Typography variant="h5" fontWeight={800} color="primary.main">{diasPreview}</Typography>
              </Box>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAbierto(false)}>Cancelar</Button>
          <Button variant="contained" disabled={!formValido || guardarCiclo.isPending} onClick={() => guardarCiclo.mutate()}>
            {guardarCiclo.isPending ? 'Guardando…' : 'Guardar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}


// ── Pestaña Mantenimiento ─────────────────────────────────────────────
// ── Tabla de resultados de reset ─────────────────────────────────────
function ResetResultTable({ result }: { result: any }) {
  return (
    <Box sx={{ mt: 2, maxHeight: 200, overflowY: 'auto' }}>
      <TableContainer component={Paper} elevation={0}
        sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
        <Table size="small">
          <TableHead sx={{ bgcolor: 'grey.100' }}>
            <TableRow>
              <TableCell><strong>Tabla</strong></TableCell>
              <TableCell align="right"><strong>Filas</strong></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(result.tablas || []).map((t: any) => (
              <TableRow key={t.tabla} hover>
                <TableCell sx={{ fontFamily: 'monospace', fontSize: 11 }}>{t.tabla}</TableCell>
                <TableCell align="right">{t.filas}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

function MantenimientoTab() {
  // ── Estado de los dos pasos ──────────────────────────────────────────
  const [factsBorrados, setFactsBorrados] = useState(false);

  const [confirmFacts, setConfirmFacts] = useState(false);
  const [confirmDims,  setConfirmDims]  = useState(false);

  const [loadingFacts, setLoadingFacts] = useState(false);
  const [loadingDims,  setLoadingDims]  = useState(false);

  const [resultFacts, setResultFacts] = useState<any>(null);
  const [resultDims,  setResultDims]  = useState<any>(null);

  const [msgFacts, setMsgFacts] = useState('');
  const [msgDims,  setMsgDims]  = useState('');

  const qc = useQueryClient();

  // ── Paso 1: borrar FACTs ─────────────────────────────────────────────
  const handleResetFacts = async () => {
    setLoadingFacts(true);
    setConfirmFacts(false);
    setResultFacts(null);
    setMsgFacts('');
    try {
      const res = await api.post('/admin/reset?tipo=facts');
      setResultFacts(res.data);
      setFactsBorrados(true);
      setMsgFacts(`✓ Datos borrados — ${res.data.total_filas_borradas} filas eliminadas`);
    } catch (e: any) {
      setMsgFacts(`Error: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoadingFacts(false);
    }
  };

  // ── Paso 2: borrar DIMs ──────────────────────────────────────────────
  const handleResetDims = async () => {
    setLoadingDims(true);
    setConfirmDims(false);
    setResultDims(null);
    setMsgDims('');
    try {
      const res = await api.post('/admin/reset?tipo=dims');
      setResultDims(res.data);
      setFactsBorrados(false); // reinicia el ciclo
      setMsgDims(`✓ Catálogos borrados — ${res.data.total_filas_borradas} filas eliminadas`);
      // Eliminar cache completamente (no solo invalidar) para que no se vean datos viejos
      ['paises','lineas','gerentes','rms','indicadores','ciclos'].forEach(k =>
        qc.removeQueries({ queryKey: [k] })
      );
    } catch (e: any) {
      setMsgDims(`Error: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoadingDims(false);
    }
  };

  return (
    <Box>
      <Typography variant="h6" fontWeight={600} mb={1}>Mantenimiento de Datos</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Borrado en dos pasos. Los usuarios del sistema siempre se conservan.
      </Typography>

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>

        {/* ── Paso A: Borrar FACTs ─────────────────────────────────── */}
        <Card variant="outlined"
          sx={{ borderRadius: 2, borderColor: factsBorrados ? 'grey.300' : 'error.light' }}>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between',
                       alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle1" fontWeight={700}
                  color={factsBorrados ? 'text.disabled' : 'error.main'}>
                  Paso 1 — Borrar datos de desempeño (FACT)
                </Typography>
                <Typography variant="body2" color="text.secondary" mt={0.5}>
                  Elimina KPIs, ventas, rankings, cargas ETL y auditoría.
                  Los catálogos (países, RMs, etc.) se conservan.
                  {factsBorrados && (
                    <span style={{ color: EXITO, fontWeight: 600 }}>
                      {' '}✓ Completado — listo para el Paso 2.
                    </span>
                  )}
                </Typography>
              </Box>
              <Button
                variant="contained" color="error" size="small"
                disabled={loadingFacts || factsBorrados}
                onClick={() => setConfirmFacts(true)}
              >
                {loadingFacts ? 'Borrando...' : factsBorrados ? 'Ya borrado' : 'Borrar FACTs'}
              </Button>
            </Box>
            {msgFacts && (
              <Alert
                severity={msgFacts.startsWith('Error') ? 'error' : 'success'}
                sx={{ mt: 2 }} onClose={() => setMsgFacts('')}
              >
                {msgFacts}
              </Alert>
            )}
            {resultFacts && <ResetResultTable result={resultFacts} />}
          </CardContent>
        </Card>

        {/* ── Paso B: Borrar DIMs ──────────────────────────────────── */}
        <Card variant="outlined"
          sx={{ borderRadius: 2,
                borderColor: factsBorrados ? 'warning.main' : 'grey.300',
                opacity: factsBorrados ? 1 : 0.55 }}>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between',
                       alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle1" fontWeight={700}
                  color={factsBorrados ? 'warning.dark' : 'text.disabled'}>
                  Paso 2 — Borrar catálogos (DIM)
                </Typography>
                <Typography variant="body2" color="text.secondary" mt={0.5}>
                  Elimina países, líneas, gerentes, RMs, indicadores y ciclos.
                  {!factsBorrados && (
                    <span style={{ color: '#b71c1c' }}>
                      {' '}Disponible solo después de ejecutar el Paso 1.
                    </span>
                  )}
                </Typography>
              </Box>
              <Button
                variant="contained"
                sx={{ bgcolor: 'warning.main', '&:hover': { bgcolor: 'warning.dark' } }}
                size="small"
                disabled={loadingDims || !factsBorrados}
                onClick={() => setConfirmDims(true)}
              >
                {loadingDims ? 'Borrando...' : 'Borrar DIMs'}
              </Button>
            </Box>
            {msgDims && (
              <Alert
                severity={msgDims.startsWith('Error') ? 'error' : 'success'}
                sx={{ mt: 2 }} onClose={() => setMsgDims('')}
              >
                {msgDims}
              </Alert>
            )}
            {resultDims && <ResetResultTable result={resultDims} />}
          </CardContent>
        </Card>

        {/* ── Paso C: Importar DIMs ────────────────────────────────── */}
        <Card variant="outlined" sx={{ borderRadius: 2, borderColor: 'primary.light' }}>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between',
                       alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle1" fontWeight={700} color="primary.main">
                  Paso 3 — Importar catálogos (DIMs)
                </Typography>
                <Typography variant="body2" color="text.secondary" mt={0.5}>
                  Sube <strong>DIM_MIP_FINAL.xlsx</strong> y selecciona todas las hojas para
                  repoblar países, líneas, gerentes, RMs, indicadores y ciclos.
                </Typography>
              </Box>
              <Button
                variant="outlined" color="primary" size="small"
                onClick={() => {
                  const event = new CustomEvent('admin-navigate-tab', { detail: 'import' });
                  window.dispatchEvent(event);
                }}
              >
                Ir a Importar DIMs
              </Button>
            </Box>
          </CardContent>
        </Card>

        {/* ── Paso D: Cargar FACTs ─────────────────────────────────── */}
        <Card variant="outlined" sx={{ borderRadius: 2, borderColor: 'success.light' }}>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between',
                       alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle1" fontWeight={700} color="success.dark">
                  Paso 4 — Cargar datos KPI (FACT)
                </Typography>
                <Typography variant="body2" color="text.secondary" mt={0.5}>
                  Ve a ETL, sube <strong>FACT_MIP_FINAL.xlsx</strong> con{' '}
                  <code>tipo_archivo=KPI_RM</code> y <code>modo=PRODUCCION</code>.
                  El recálculo se dispara automáticamente.
                </Typography>
              </Box>
              <Button
                variant="outlined" color="success" size="small"
                onClick={() => window.location.assign('/etl')}
              >
                Ir a ETL
              </Button>
            </Box>
          </CardContent>
        </Card>

      </Box>

      {/* ── Diálogo confirmar Paso 1 ─────────────────────────────── */}
      <Dialog open={confirmFacts} onClose={() => setConfirmFacts(false)} maxWidth="xs">
        <DialogTitle sx={{ color: 'error.main' }}>⚠ Confirmar — Borrar datos FACT</DialogTitle>
        <DialogContent>
          <Typography>
            Se eliminarán todos los <strong>datos de desempeño</strong>: KPIs, ventas, rankings,
            cargas ETL y registros de auditoría.
          </Typography>
          <Typography mt={1}>Los catálogos (países, RMs, etc.) <strong>no se tocan</strong>.</Typography>
          <Typography mt={1} color="error.main" fontWeight={600}>Esta acción es irreversible.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmFacts(false)}>Cancelar</Button>
          <Button variant="contained" color="error" onClick={handleResetFacts} disabled={loadingFacts}>
            {loadingFacts ? 'Borrando...' : 'Sí, borrar FACTs'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Diálogo confirmar Paso 2 ─────────────────────────────── */}
      <Dialog open={confirmDims} onClose={() => setConfirmDims(false)} maxWidth="xs">
        <DialogTitle sx={{ color: 'warning.dark' }}>⚠ Confirmar — Borrar catálogos DIM</DialogTitle>
        <DialogContent>
          <Typography>
            Se eliminarán todos los <strong>catálogos maestros</strong>: países, líneas, gerentes,
            RMs, indicadores, ciclos, etc.
          </Typography>
          <Typography mt={1}>
            Los datos FACT ya fueron borrados en el Paso 1.
          </Typography>
          <Typography mt={1} color="warning.dark" fontWeight={600}>Esta acción es irreversible.</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDims(false)}>Cancelar</Button>
          <Button variant="contained"
            sx={{ bgcolor: 'warning.main', '&:hover': { bgcolor: 'warning.dark' } }}
            onClick={handleResetDims} disabled={loadingDims}>
            {loadingDims ? 'Borrando...' : 'Sí, borrar DIMs'}
          </Button>
        </DialogActions>
      </Dialog>

    </Box>
  );
}


// ── Configuración de cada pestaña ─────────────────────────────────────

const TABS_DIM = [
  {
    label: 'Países',
    endpoint: 'paises',
    importable: true,
    columns: [
      { key: 'id', label: 'ID' },
      { key: 'codigo', label: 'Código' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'moneda', label: 'Moneda' },
      { key: 'zona_horaria', label: 'Zona Horaria' },
      { key: 'activo', label: 'Estado', render: (v: boolean) => <Chip label={v ? 'Activo' : 'Inactivo'} color={v ? 'success' : 'default'} size="small" /> },
    ],
    addFields: [
      { key: 'codigo', label: 'Código (CR, GT, HN...)' },
      { key: 'nombre', label: 'Nombre del País' },
      { key: 'moneda', label: 'Moneda (CRC, GTQ...)' },
      { key: 'zona_horaria', label: 'Zona Horaria' },
    ],
  },
  {
    label: 'Líneas',
    endpoint: 'lineas',
    importable: true,
    hasPaisFilter: true,
    columns: [
      { key: 'id', label: 'ID' },
      { key: 'pais_codigo', label: 'País' },
      { key: 'codigo', label: 'Código' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'activo', label: 'Estado', render: (v: boolean) => <Chip label={v ? 'Activo' : 'Inactivo'} color={v ? 'success' : 'default'} size="small" /> },
    ],
    addFields: [
      { key: 'pais_codigo', label: 'País', isPais: true },
      { key: 'codigo', label: 'Código (CAR, GAS...)' },
      { key: 'nombre', label: 'Nombre de la Línea' },
    ],
  },
  {
    label: 'Gerentes',
    endpoint: 'gerentes',
    importable: true,
    hasPaisFilter: true,
    columns: [
      { key: 'id', label: 'ID' },
      { key: 'pais_codigo', label: 'País' },
      { key: 'codigo', label: 'Código' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'tipo', label: 'Tipo', render: (v: string) => <Chip label={v} size="small" color="info" variant="outlined" /> },
      { key: 'email', label: 'Email' },
      { key: 'fecha_ingreso', label: 'Fecha Ingreso' },
      { key: 'activo', label: 'Estado', render: (v: boolean) => <Chip label={v ? 'Activo' : 'Inactivo'} color={v ? 'success' : 'default'} size="small" /> },
    ],
    addFields: [
      { key: 'pais_codigo', label: 'País', isPais: true },
      { key: 'linea_id', label: 'Línea', isLinea: true },
      { key: 'codigo', label: 'Código (GD001...)' },
      { key: 'nombre', label: 'Nombre Completo' },
      { key: 'email', label: 'Email' },
      { key: 'tipo', label: 'Tipo', options: ['DISTRITO', 'MARCA', 'REGIONAL'] },
      { key: 'fecha_ingreso', label: 'Fecha Ingreso', type: 'date' },
    ],
    // En Editar, `linea_id` pasa a solo lectura ("línea principal heredada") — la fuente
    // de verdad de las líneas de un gerente es `DIM_GerenteLinea` (selector múltiple propio).
    editFields: [
      { key: 'pais_codigo', label: 'País', isPais: true },
      { key: 'linea_id', label: 'Línea principal (heredada)', isLineaReadOnly: true },
      { key: 'codigo', label: 'Código (GD001...)' },
      { key: 'nombre', label: 'Nombre Completo' },
      { key: 'email', label: 'Email' },
      { key: 'tipo', label: 'Tipo', options: ['DISTRITO', 'MARCA', 'REGIONAL'] },
      { key: 'fecha_ingreso', label: 'Fecha Ingreso', type: 'date' },
      { key: 'lineas_editor', label: 'Líneas asignadas', isLineasGerente: true },
    ],
  },
  {
    label: 'RMs',
    endpoint: 'rms',
    importable: true,
    hasPaisFilter: true,
    columns: [
      { key: 'id', label: 'ID' },
      { key: 'pais_codigo', label: 'País' },
      { key: 'codigo', label: 'Código' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'cedula', label: 'Cédula' },
      { key: 'email', label: 'Email' },
      { key: 'zona', label: 'Zona' },
      { key: 'fecha_ingreso', label: 'Fecha Ingreso' },
      { key: 'activo', label: 'Estado', render: (v: boolean) => <Chip label={v ? 'Activo' : 'Inactivo'} color={v ? 'success' : 'default'} size="small" /> },
    ],
    addFields: [
      { key: 'pais_codigo', label: 'País', isPais: true },
      { key: 'linea_id', label: 'Línea', isLinea: true },
      { key: 'gerente_id', label: 'Gerente', isGerente: true },
      { key: 'codigo', label: 'Código RM' },
      { key: 'nombre', label: 'Nombre Completo' },
      { key: 'cedula', label: 'Cédula' },
      { key: 'email', label: 'Email' },
      { key: 'zona', label: 'Zona' },
      { key: 'fecha_ingreso', label: 'Fecha Ingreso', type: 'date' },
      { key: 'coaching_min_dia', label: 'Mín. Coaching/día (1-9)', type: 'number' },
    ],
  },
  {
    label: 'Productos',
    endpoint: 'productos',
    columns: [
      { key: 'id', label: 'ID' },
      { key: 'codigo', label: 'Código' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'area_terapeutica', label: 'Área' },
      { key: 'descripcion', label: 'Descripción' },
      { key: 'gerente_producto', label: 'Gerente de Producto' },
      { key: 'segmento_target', label: 'Segmento target' },
      { key: 'meta_muestras_visita', label: 'Meta/visita', align: 'center' },
      { key: 'activo', label: 'Estado', render: (v: boolean) => <Chip label={v ? 'Activo' : 'Inactivo'} color={v ? 'success' : 'default'} size="small" /> },
    ],
    addFields: [
      { key: 'codigo', label: 'Código (ONCX-301...)' },
      { key: 'nombre', label: 'Nombre del Producto' },
      { key: 'area_terapeutica', label: 'Área Terapéutica', optionsEspecialidad: true },
      { key: 'descripcion', label: 'Descripción (Inhibidor selectivo...)' },
      { key: 'segmento_target', label: 'Segmento Target', freeSoloFrom: 'segmento_target' },
      { key: 'meta_muestras_visita', label: 'Meta muestras / visita', type: 'number' },
      { key: 'pais_codigo', label: 'País (para elegir línea)', isPais: true },
      { key: 'linea_id', label: 'Línea', isLinea: true },
      { key: 'gerente_producto', label: 'Gerente de Producto (responsable)', isGerenteProducto: true },
    ],
  },
  {
    label: 'Indicadores',
    endpoint: 'indicadores',
    importable: true,
    hasPaisFilter: true,
    columns: [
      { key: 'pais_codigo', label: 'País' },
      { key: 'codigo', label: 'Código' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'modulo', label: 'Módulo', render: (v: string) => <Chip label={v} size="small" color={v === 'GESTION' ? 'primary' : 'warning'} variant="outlined" /> },
      { key: 'tipo_periodo', label: 'Período', render: (v: string) => <Chip label={v} color={v === 'CICLO' ? 'info' : 'secondary'} size="small" variant="outlined" /> },
      { key: 'ponderacion_pct', label: 'Peso (pts)', align: 'center', render: (v: number) => `${v}` },
      { key: 'escala', label: 'Escala', render: (v: number) => v === 1 ? '% (0-100)' : 'Puntos' },
      { key: 'activo', label: 'Estado', render: (v: boolean) => <Chip label={v ? 'Activo' : 'Inactivo'} color={v ? 'success' : 'default'} size="small" /> },
    ],
    addFields: [
      { key: 'pais_codigo', label: 'País', isPais: true },
      { key: 'codigo', label: 'Código (COB_MD_F2...)' },
      { key: 'nombre', label: 'Nombre del Indicador' },
      { key: 'modulo', label: 'Módulo', options: ['GESTION', 'RESULTADOS'] },
      { key: 'tipo_periodo', label: 'Tipo Período', options: ['CICLO', 'MES'] },
      { key: 'ponderacion_pct', label: 'Ponderación %', type: 'number' },
      { key: 'escala', label: 'Escala (1=% / 100=pts)', type: 'number' },
      { key: 'valor_min', label: 'Valor Mínimo', type: 'number' },
      { key: 'valor_max', label: 'Valor Máximo', type: 'number' },
    ],
  },
  {
    label: 'Ciclos',
    endpoint: 'ciclos',
    importable: true,
    isCiclos: true,
    columns: [
      { key: 'id', label: 'ID' },
      { key: 'pais_codigo', label: 'País' },
      { key: 'nombre', label: 'Nombre' },
      { key: 'anio', label: 'Año' },
      { key: 'numero', label: 'Número' },
      { key: 'fecha_inicio', label: 'Inicio' },
      { key: 'fecha_fin', label: 'Fin' },
      { key: 'cerrado', label: 'Cerrado', render: (v: boolean) => <Chip label={v ? 'Sí' : 'No'} color={v ? 'error' : 'success'} size="small" /> },
    ],
    addFields: [
      { key: 'pais_codigo', label: 'País', isPais: true },
      { key: 'anio', label: 'Año', type: 'number' },
      { key: 'numero', label: 'Número de Ciclo', type: 'number' },
      { key: 'nombre', label: 'Nombre (Ciclo 1...)' },
      { key: 'nombre_canonico', label: 'Nombre Canónico (CICLO-01-2026)' },
      { key: 'fecha_inicio', label: 'Fecha Inicio', type: 'date' },
      { key: 'fecha_fin', label: 'Fecha Fin', type: 'date' },
      { key: 'dias_laborables', label: 'Días Laborables', type: 'number' },
    ],
  },
];

const TAB_RANGOS_INDEX     = TABS_DIM.length;
const TAB_IMPORT_INDEX     = TABS_DIM.length + 1;
const TAB_MANT_INDEX       = TABS_DIM.length + 2;
const TAB_LSII_INDEX       = TABS_DIM.length + 3;
const TAB_COBERTURA_INDEX  = TABS_DIM.length + 4;
const TAB_CATEGORIZACION_INDEX = TABS_DIM.length + 5;
const TAB_GEO_INDEX        = TABS_DIM.length + 6;   // Especialidades y Centros
const TAB_GEO2_INDEX       = TABS_DIM.length + 7;   // Provincias y Municipios

// ── Componente principal ──────────────────────────────────────────────
export default function Admin() {
  const [tab, setTab] = useState(0);

  useEffect(() => {
    const handler = (e: CustomEvent) => {
      if (e.detail === 'import') setTab(TAB_IMPORT_INDEX);
    };
    window.addEventListener('admin-navigate-tab', handler as EventListener);
    // Deep-link opcional: /admin?tab=<label DIM> abre esa pestaña (ej. ?tab=productos,
    // usado por el aviso "línea sin productos" de la Parrilla).
    const qtab = new URLSearchParams(window.location.search).get('tab');
    if (qtab) {
      const idx = TABS_DIM.findIndex((t) => t.label.toLowerCase() === qtab.toLowerCase());
      if (idx >= 0) setTab(idx);
    }
    return () => window.removeEventListener('admin-navigate-tab', handler as EventListener);
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700} mb={0.5}>Administración del Sistema</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Gestión de catálogos maestros, importación de datos y mantenimiento
      </Typography>

      <Card elevation={2} sx={{ borderRadius: 2 }}>
        <CardContent>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              mb: 0,
              borderBottom: '3px solid #686158',
              '& .MuiTab-root': {
                bgcolor: BORDE_FUERTE,
                borderTopLeftRadius: 8,
                borderTopRightRadius: 8,
                mr: 0.5,
                mb: 0,
                color: TAUPE,
                fontWeight: 600,
                minHeight: 40,
                fontSize: 13,
                lineHeight: 1.2,
                textTransform: 'none',
                '&.Mui-selected': {
                  bgcolor: TAUPE,
                  color: 'white',
                  fontWeight: 700,
                  // El icono lleva su color de función, que sobre el taupe de la pestaña
                  // seleccionada quedaría ilegible (el verde clínico da 1.4:1 contra él).
                  // Al seleccionar vuelve a blanco: ahí la pastilla ya indica DÓNDE estás,
                  // y el color de función solo hace falta para localizarla entre las demás.
                  '& .MuiSvgIcon-root': { color: 'white !important' },
                },
                '&:hover:not(.Mui-selected)': {
                  bgcolor: BORDE_FUERTE,
                },
              },
              '& .MuiTabs-indicator': { display: 'none' },
            }}
          >
            {TABS_DIM.map((t) => <Tab key={t.label} label={t.label} />)}
            <Tab label="Rangos de Puntuación" icon={<TableChart fontSize="small" sx={{ color: '#B4661E' }} />} iconPosition="start" />
            <Tab label="Importar DIMs" icon={<Upload fontSize="small" sx={{ color: '#7A5C8E' }} />} iconPosition="start" />
            <Tab label="Mantenimiento" icon={<Delete fontSize="small" sx={{ color: ROJO_OSCURO }} />} iconPosition="start" />
            <Tab label="Matriz LSII" icon={<Psychology fontSize="small" sx={{ color: '#4E6E8E' }} />} iconPosition="start" />
            <Tab label="Cobertura Predictiva" icon={<TrendingUp fontSize="small" sx={{ color: ROJO }} />} iconPosition="start" />
            <Tab label="Categorización Médica" icon={<LocalHospital fontSize="small" sx={{ color: '#2F7D6E' }} />} iconPosition="start" />
            <Tab label="Especialidades y Centros" icon={<LocalHospital fontSize="small" sx={{ color: '#2F7D6E' }} />} iconPosition="start" />
            <Tab label="Provincias y Municipios" icon={<LocalHospital fontSize="small" sx={{ color: '#2F7D6E' }} />} iconPosition="start" />
          </Tabs>

          <Box sx={{ mt: 3 }}>
            {tab === TAB_MANT_INDEX ? (
              <MantenimientoTab />
            ) : tab === TAB_IMPORT_INDEX ? (
              <ImportDims />
            ) : tab === TAB_RANGOS_INDEX ? (
              <RangosIndicadorTab />
            ) : tab === TAB_LSII_INDEX ? (
              <LsiiAdmin />
            ) : tab === TAB_COBERTURA_INDEX ? (
              <CoberturaPredictivaAdmin />
            ) : tab === TAB_CATEGORIZACION_INDEX ? (
              <CategorizacionAdmin />
            ) : tab === TAB_GEO_INDEX ? (
              <TabGeo tipos={['especialidad', 'centro']} />
            ) : tab === TAB_GEO2_INDEX ? (
              <TabGeo tipos={['provincia', 'municipio']} />
            ) : (TABS_DIM[tab] as any).isCiclos ? (
              <CiclosPorPaisTab />
            ) : (TABS_DIM[tab] as any).hasPaisFilter ? (
              <DimTabWithPais tabConfig={TABS_DIM[tab]} />
            ) : (
              <CatalogoTab
                key={TABS_DIM[tab].endpoint}
                endpoint={TABS_DIM[tab].endpoint}
                columns={TABS_DIM[tab].columns as any}
                title={TABS_DIM[tab].label}
                addFields={(TABS_DIM[tab] as any).addFields}
                editFields={(TABS_DIM[tab] as any).editFields}
                toggleActive
              />
            )}
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
