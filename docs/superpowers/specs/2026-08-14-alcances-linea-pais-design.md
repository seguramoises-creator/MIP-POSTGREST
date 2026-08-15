# Alcances por línea y por país — Diseño

**Fecha:** 2026-08-14
**Sub-proyecto:** 8 de la integración VISTA ↔ Laboratorio Mallén
**Estado:** aprobado, pendiente de plan

## 1. Por qué existe

La gerencia de Laboratorio Mallén definió siete roles para acceder a la solución.
Cuatro caben en lo que el sistema ya sabe expresar; **tres no**, y dos de ellos por
la misma causa.

| Mallén pidió | ¿Cabe hoy? |
|---|---|
| Director M&P — acceso total | Sí |
| Analista comercial — acceso total | Sí |
| Gerencia de Productividad — acceso total | Sí |
| Gerencia de mercadeo — acceso total | Sí |
| Gerencia de marca — sus líneas, todo el país | **No** |
| Gerencia de Distrito/País — sus líneas, todo el país | **No** |
| Coordinador Mercadeo Internacional — Guatemala y Honduras | **No** |

El motor de autorización tiene exactamente tres alcances efectivos —`own` (sus
propios datos), `team` (los representantes de su gerente) y `all` (todo)—, y
**no conoce ni la línea ni el país**.

Hay además un agujero que ya existe y que este sub-proyecto cierra de paso:
`Usuario.pais_codigo` existe pero **el backend nunca lo impone**. Verificado: ningún
endpoint filtra por el país del usuario. Ese "cada quien ve su país" que se observa
en pantalla lo hace el frontend por comodidad; quien conozca la API puede consultar
cualquier país.

## 2. Dos ejes, no uno

La decisión que ordena todo el diseño: **el país no es un alcance más**.

Los alcances responden a *"¿de cuáles representantes?"*. El país responde a *"¿de
cuál operación?"*. Son ortogonales — un Gerente de Marca tiene alcance de línea
**dentro de** su país.

Por eso el país se aplica como **filtro transversal** por encima de la matriz, no
como un cuarto valor de `Alcance`. Meterlo dentro obligaría a multiplicar cada celda
de la matriz por cada país, y cada territorio nuevo exigiría desplegar código.

## 3. Modelo de datos

Dos tablas nuevas. Ninguna columna existente cambia de significado sin que se diga.

| Tabla | Contenido | Regla |
|---|---|---|
| `Security.FACT_UsuarioPais` | `(usuario_id, pais_codigo)` | **Sin filas = todos los países** |
| `Config.DIM_GerenteLinea` | `(gerente_id, linea_id)` | Una o varias líneas por gerente |

**`FACT_UsuarioPais` vacía significa "todos"** a propósito: los 37 usuarios que ya
existen siguen funcionando exactamente igual el día que se active la frontera, sin
tener que asignarle países a cada uno primero. La alternativa —lista explícita
siempre— es más auditable, pero deja a todo el mundo sin ver nada hasta completar
una migración de datos manual, y ese es el tipo de paso que se olvida.

**`DIM_GerenteLinea` migra el `linea_id` actual** de `DIM_Gerente`, que se conserva.
Mallén escribió "sus líneas asignadas" en plural y hoy el modelo guarda una sola;
duplicar el usuario de un gerente con dos líneas sería una solución que se paga
después.

`Usuario.pais_codigo` **no se toca**: pasa a ser el país *preferido* —el que la
pantalla abre por defecto— y deja de ser (de hecho, empieza a no ser) la frontera.

## 4. El motor

- **`Alcance.LINEA`**, valor nuevo. `scope.rm_ids_visibles` lo resuelve como los RM
  cuya línea esté entre las líneas del gerente del usuario.
- **`scope.paises_visibles(db, user) → set[str] | None`** (`None` = todos), y un
  guard que rechaza con 403 cualquier consulta a un país fuera de esa lista.

El orden importa: primero el país, después el alcance. Un Gerente de Marca de RD con
alcance de línea ve los RM de su línea **en RD**, no los de esa línea en Guatemala.

## 5. Los siete roles, sin crear ninguno

| Mallén | Rol existente | Países | Alcance |
|---|---|---|---|
| Director M&P | `DIR_COMERCIAL` | todos | `all` |
| Analista comercial | `ANALISTA_DATOS` | todos | `all` |
| Gerencia de Productividad | `GERENTE_PRODUCTIVIDAD` | todos | `all` |
| Gerencia de mercadeo | `GERENTE_MARKETING` | todos | `all` |
| Gerencia de marca | `GERENTE_MARCA` | el suyo | `línea` |
| Gerencia de Distrito/País | `GERENTE_DISTRITO` | el suyo | `línea` lectura / `team` escritura |
| Coordinador Mercadeo Intl | `GERENTE_MARKETING` | **GT, HN** | `all` |

**El Coordinador Internacional no necesita rol propio: es Gerencia de Mercadeo con
dos países asignados.** Mallén los describió con los mismos permisos y la única
diferencia entre ellos es geográfica. Esto solo es posible porque los dos ejes están
separados (§2).

Costo aceptado: si más adelante quieren que el Coordinador vea *menos* que Mercadeo,
habrá que separarlos en dos roles. Es un cambio barato frente a la alternativa de
tener un rol por combinación de países.

## 6. "Acceso total" es leer, no configurar

Decisión del cliente: los cuatro roles con "acceso total" **leen y exportan** toda la
operación de sus países, pero **cambiar metas, ciclos, parrilla promocional, costos y
la matriz de permisos sigue siendo de Gerencia de Productividad y ADMIN**.

El motivo es que esas configuraciones son la base sobre la que se calcula el ranking.
Con cuatro roles capaces de moverla, la auditoría diría quién lo hizo pero no lo
evitaría.

## 7. La restricción de una celda por recurso

Para el Gerente de Distrito se acordó "lee su línea, actúa sobre su equipo": lee toda
su línea en el país para compararse, pero aprobar médicos y registrar coaching siguen
limitados a sus propios representantes — un GD no opera sobre el equipo de otro.

La matriz guarda **una celda por `(recurso, rol)`**, y una acción de escritura implica
lectura *al mismo alcance*. No se puede pedir `READ/línea` y `APPROVE/team` sobre el
mismo recurso.

**No se cambia el modelo de la matriz.** Los recursos donde el GD lee para comparar
(`ranking.rkt`, `productividad.comercial`, `cobertura.predictiva`) son distintos de
aquellos donde escribe (`medico.panel`, `coaching.hoja`). El alcance `línea` se asigna
solo a recursos de lectura.

Si aparece un recurso que genuinamente necesite ambos, se decide entonces —
probablemente separando la lectura en su propio recurso. No se construye ahora una
generalización para un caso que no existe.

## 8. Fuera de alcance (YAGNI)

- **No se crean roles nuevos** (§5).
- **No se toca el esquema `ext`** ni el motor de cálculo.
- **No se generaliza la matriz** a dos alcances por celda (§7).
- **No se construye una UI de asignación masiva** de países ni líneas: se asignan
  desde la pantalla de Usuarios y desde Gerentes, que ya existen.
- La matriz sigue **editable en caliente** desde Roles y Permisos; nada de esto exige
  desplegar para cambiar un permiso.

## 9. Verificación

**La frontera de país**
1. Un usuario sin filas en `FACT_UsuarioPais` ve todos los países — el comportamiento
   de hoy, intacto.
2. Un usuario con `{GT, HN}` consulta GT y HN con normalidad.
3. Ese mismo usuario recibe **403 al consultar RD**, aunque pase el `pais_codigo` a
   mano en la API. Es el test que convierte el filtro en frontera.
4. Un gerente de RD ya no puede consultar Guatemala. **Hoy sí puede**: este test falla
   antes del cambio, que es lo que demuestra que el agujero era real.

**El alcance por línea**
5. Un Gerente de Marca con una línea ve los RM de esa línea y **no** los de otra.
6. Con dos líneas asignadas ve los de ambas.
7. Ve los RM de su línea **de todos los distritos**, no solo los de un gerente.
8. Un Gerente de Marca de RD **no** ve los RM de su misma línea en Guatemala — el país
   se aplica antes que el alcance (§4).

**El Gerente de Distrito**
9. Lee el ranking de toda su línea en el país, incluidos equipos de sus pares.
10. **No puede aprobar** un médico de un representante que no es suyo (403), aunque
    ese representante sí aparezca en su lectura de línea. Es el test que fija la
    frontera entre leer y actuar.

**Compatibilidad**
11. Los 37 usuarios existentes conservan exactamente el acceso que tienen hoy tras la
    migración, sin intervención manual.
12. El `linea_id` de cada gerente queda migrado a `DIM_GerenteLinea` y sigue
    resolviendo igual.
