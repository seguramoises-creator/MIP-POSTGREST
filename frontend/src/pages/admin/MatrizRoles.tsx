/**
 * MatrizRoles.tsx — Matriz de Roles y Permisos (RBAC/ABAC), solo lectura.
 * Pestaña dentro de Administración, después de Usuarios. Solo ADMIN (heredado de la ruta).
 *
 * Consume GET /authz/matriz (fuente de verdad = backend/app/core/authz/matrix.py).
 * Muestra 32 recursos × 13 roles, con color por acción y alcance (propio/equipo/todo).
 * No edita: para cambiar un permiso se toca la matriz en el backend y se re-siembra.
 */
import { Fragment, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Chip, Stack, TextField, InputAdornment, CircularProgress,
  Alert, Tooltip, Button,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import SecurityIcon from '@mui/icons-material/Security';
import { api } from '../../services/api';

// Orden y etiqueta corta de cada rol (columnas). Coincide con el orden del backend.
const ROLES: { key: string; label: string; desc: string }[] = [
  { key: 'REPRESENTANTE_MEDICO', label: 'Representante', desc: 'Solo sus propios datos.' },
  { key: 'GERENTE_DISTRITO', label: 'Ger. Distrito', desc: 'Su equipo; agregados sin nombres ajenos.' },
  { key: 'GERENTE_MARCA', label: 'Ger. Producto', desc: 'Configura parrilla, categorización detalle e inteligencia.' },
  { key: 'GERENTE_MARKETING', label: 'Ger. Marketing', desc: 'Mercado y producto a nivel empresa.' },
  { key: 'GERENTE_PRODUCTIVIDAD', label: 'Capac./Product.', desc: 'ETL, exámenes, LSII, reconocimientos.' },
  { key: 'GERENTE_MEDICO', label: 'Ger. Médico', desc: 'Área médica; fuera del muro comercial.' },
  { key: 'PRESIDENCIA', label: 'Dir. General', desc: 'Lectura total + aprueba Costo/ROI.' },
  { key: 'ANALISTA_DATOS', label: 'Analista Datos', desc: 'Lectura total + exportación, sin escritura.' },
  { key: 'FINANZAS', label: 'Finanzas', desc: 'Configura costos/pool/presupuesto de Costo/ROI.' },
  { key: 'ADMIN', label: 'Superadmin', desc: 'Acceso total, incluido administración de sistema.' },
  { key: 'CAPACITACION', label: 'Capacitación', desc: 'Coordina exámenes. Perfil mínimo.' },
  { key: 'DIR_COMERCIAL', label: 'Dir. Comercial', desc: 'Como Analista de Datos.' },
  { key: 'CONSULTA', label: 'Consulta', desc: 'Solo lectura total, sin exportar.' },
];

// Acción → etiqueta + colores (texto/fondo). Semántica independiente del acento de marca.
const ACC: Record<string, { label: string; fg: string; bg: string }> = {
  read:      { label: 'Ver',        fg: '#1e5fd4', bg: '#eaf1fe' },
  register:  { label: 'Registrar',  fg: '#0e8a6e', bg: '#e5f6f0' },
  configure: { label: 'Configurar', fg: '#b56a09', bg: '#fbf0dd' },
  approve:   { label: 'Aprobar',    fg: '#7a34e0', bg: '#f2eafe' },
  export:    { label: 'Exportar',   fg: '#0c7397', bg: '#e2f4fb' },
  admin:     { label: 'Admin',      fg: '#3d3a7a', bg: '#e6e4f4' },
};
const SCOPE: Record<string, string> = { own: 'propio', team: 'equipo', all: 'todo', none: '' };

type Celda = { accion: string; alcance: string } | null;
type Recurso = { recurso: string; nombre: string; modulo: string; roles: Record<string, Celda> };

function Cell({ celda }: { celda: Celda }) {
  if (!celda) return <Box sx={{ color: 'text.disabled', fontSize: 13 }}>—</Box>;
  const a = ACC[celda.accion] ?? { label: celda.accion, fg: '#555', bg: '#eee' };
  const scp = SCOPE[celda.alcance] ?? '';
  const esAdmin = celda.accion === 'admin';
  return (
    <Box sx={{
      display: 'inline-flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      minWidth: 60, px: 1, py: 0.4, borderRadius: 1.2, lineHeight: 1.2,
      color: a.fg, bgcolor: a.bg,
    }}>
      <Box sx={{ fontWeight: esAdmin ? 800 : 700, fontSize: 12 }}>{a.label}</Box>
      {scp && <Box sx={{ fontSize: 10, opacity: 0.85 }}>{scp}</Box>}
    </Box>
  );
}

export default function MatrizRoles() {
  const [q, setQ] = useState('');
  const [colActiva, setColActiva] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['authz-matriz'],
    queryFn: () => api.get('/authz/matriz').then((r) => r.data),
    retry: 1,
  });

  const recursos: Recurso[] = Array.isArray(data?.recursos) ? data.recursos : [];

  // Filtro por texto (nombre o slug del recurso).
  const filtrados = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return recursos;
    return recursos.filter((r) => (`${r.nombre} ${r.recurso}`).toLowerCase().includes(t));
  }, [recursos, q]);

  // Agrupar por módulo conservando el orden de aparición.
  const grupos = useMemo(() => {
    const out: { modulo: string; filas: Recurso[] }[] = [];
    for (const r of filtrados) {
      const g = out[out.length - 1];
      if (g && g.modulo === r.modulo) g.filas.push(r);
      else out.push({ modulo: r.modulo, filas: [r] });
    }
    return out;
  }, [filtrados]);

  const stickyLeft = {
    position: 'sticky', left: 0, zIndex: 2, bgcolor: 'background.paper',
    borderRight: '2px solid', borderColor: 'divider',
  } as const;

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
        <SecurityIcon color="primary" />
        <Typography variant="h5" fontWeight={700}>Roles y Permisos</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Quién puede hacer qué, y sobre qué datos. Control por rol (RBAC) con alcance de datos (ABAC),
        denegación por defecto. Vista de solo lectura — la fuente de verdad vive en el backend.
      </Typography>

      {/* Leyenda */}
      <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
        {Object.entries(ACC).map(([k, v]) => (
          <Chip key={k} size="small" label={v.label}
                sx={{ fontWeight: 700, color: v.fg, bgcolor: v.bg, border: '1px solid', borderColor: 'divider' }} />
        ))}
        <Chip size="small" label="— sin acceso" variant="outlined" sx={{ color: 'text.disabled' }} />
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
        Alcance: <b>propio</b> = solo sus datos · <b>equipo</b> = su equipo (gerente) · <b>todo</b> = toda la empresa.
      </Typography>

      {/* Controles */}
      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" sx={{ mb: 2 }}>
        <TextField
          size="small" placeholder="Buscar recurso… (costo, examen, ranking)"
          value={q} onChange={(e) => setQ(e.target.value)} sx={{ minWidth: 260, flex: '1 1 260px' }}
          InputProps={{ startAdornment: (<InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>) }}
        />
        {colActiva && (
          <Button size="small" variant="outlined" onClick={() => setColActiva(null)}>
            Quitar resaltado: {ROLES.find((r) => r.key === colActiva)?.label} ✕
          </Button>
        )}
        <Typography variant="caption" color="text.secondary">
          {q ? `${filtrados.length} de ${recursos.length}` : `${recursos.length}`} recursos · {ROLES.length} roles
        </Typography>
      </Stack>

      {isLoading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}><CircularProgress /></Box>
      )}
      {isError && (
        <Alert severity="error" action={<Button size="small" onClick={() => refetch()}>Reintentar</Button>}>
          No se pudo cargar la matriz de permisos.
        </Alert>
      )}

      {!isLoading && !isError && (
        <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
          <CardContent sx={{ p: 0 }}>
            <TableContainer component={Paper} elevation={0} sx={{ maxHeight: '72vh', borderRadius: 2 }}>
              <Table stickyHeader size="small" sx={{ '& td, & th': { borderColor: 'divider' } }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ ...stickyLeft, zIndex: 4, minWidth: 230, fontWeight: 700, top: 0 }}>
                      Recurso / Funcionalidad
                    </TableCell>
                    {ROLES.map((r) => (
                      <TableCell key={r.key} align="center"
                        onClick={() => setColActiva((c) => (c === r.key ? null : r.key))}
                        sx={{
                          cursor: 'pointer', whiteSpace: 'nowrap', fontWeight: 700, top: 0,
                          bgcolor: colActiva === r.key ? 'primary.main' : 'background.paper',
                          color: colActiva === r.key ? 'primary.contrastText' : 'text.primary',
                          '&:hover': { color: colActiva === r.key ? 'primary.contrastText' : 'primary.main' },
                        }}>
                        <Tooltip title={`${r.key} — ${r.desc}`} arrow>
                          <span>{r.label}</span>
                        </Tooltip>
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {grupos.map((g) => (
                    <Fragment key={`g-${g.modulo}`}>
                      <TableRow>
                        <TableCell sx={{ ...stickyLeft, zIndex: 3, bgcolor: 'action.hover',
                          fontWeight: 700, textTransform: 'uppercase', fontSize: 11, letterSpacing: '.06em',
                          color: 'primary.main' }}>
                          {g.modulo}
                        </TableCell>
                        <TableCell colSpan={ROLES.length} sx={{ bgcolor: 'action.hover' }} />
                      </TableRow>
                      {g.filas.map((row) => (
                        <TableRow key={row.recurso} hover>
                          <TableCell sx={{ ...stickyLeft, fontWeight: 600 }}>
                            {row.nombre}
                            <Box sx={{ fontSize: 11, color: 'text.disabled' }}>{row.recurso}</Box>
                          </TableCell>
                          {ROLES.map((r) => {
                            const activa = colActiva === r.key;
                            const atenuada = colActiva && !activa;
                            return (
                              <TableCell key={r.key} align="center"
                                sx={{
                                  opacity: atenuada ? 0.3 : 1,
                                  boxShadow: activa ? (theme) => `inset 0 0 0 2px ${theme.palette.primary.main}` : 'none',
                                }}>
                                <Cell celda={row.roles?.[r.key] ?? null} />
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      ))}
                    </Fragment>
                  ))}
                  {filtrados.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={ROLES.length + 1} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                        Ningún recurso coincide con “{q}”.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
        Tip: haz clic en el nombre de un rol (cabecera) para aislar su columna.
      </Typography>
    </Box>
  );
}
