using System.Net;
using System.Text.Json;
using VistaCampo.Modelos;

namespace VistaCampo.Servicios;

/// <summary>Un alta que el servidor frenó porque puede ser un duplicado.</summary>
public class PosibleDuplicado : Exception
{
    public List<string> Coincidencias { get; }

    /// <summary>
    /// `true` cuando el duplicado es DURO y no se puede saltar: mismo exequátur, misma
    /// cédula, o el mismo nombre en el mismo centro. Ahí no hay «continuar de todos
    /// modos» — sería crear a la misma persona dos veces.
    /// </summary>
    public bool Bloqueante { get; }

    public PosibleDuplicado(string mensaje, List<string> coincidencias, bool bloqueante)
        : base(mensaje)
    {
        Coincidencias = coincidencias;
        Bloqueante = bloqueante;
    }
}

/// <summary>
/// Alta de médicos y farmacias.
///
/// ESTO NO SE ENCOLA, y es una decisión, no una limitación. Todo lo demás que captura la
/// app se guarda primero en el teléfono y sube después; un alta no puede: lo primero que
/// hace el servidor es comprobar que esa persona o esa farmacia no existe ya, y esa
/// comprobación vive en la base central. Un alta guardada sin conexión y enviada tres
/// horas después crearía el duplicado que todo el mecanismo antiduplicados existe para
/// evitar — y un duplicado en el maestro lo arrastra el sistema entero: dos fichas del
/// mismo médico, cobertura contada dos veces, categorización partida.
///
/// Así que el alta pide conexión y lo dice con esas palabras. Registrar la visita, que
/// es lo urgente en la calle, sigue funcionando sin señal.
/// </summary>
public class ServicioAltas
{
    private readonly ApiCliente _api;
    private readonly Sesion _sesion;

    public ServicioAltas(ApiCliente api, Sesion sesion)
    {
        _api = api;
        _sesion = sesion;
    }

    /// <summary>Refresca el país del visitador desde el servidor.</summary>
    public async Task<string?> PaisAsync()
    {
        if (!string.IsNullOrEmpty(_sesion.PaisCodigo)) return _sesion.PaisCodigo;
        var yo = await _api.ObtenerAsync<JsonElement>("/auth/me");
        _sesion.PaisCodigo = ServicioSincronizacion.Texto(yo, "pais_codigo");
        return _sesion.PaisCodigo;
    }

    // ── Médicos ──────────────────────────────────────────────────────────────

    /// <summary>
    /// El formulario de clasificación, dibujado con el vocabulario del país.
    ///
    /// Si el país no tiene reglas cargadas el servidor responde 409, y ahí no se puede
    /// dar de alta a nadie: sin reglas el médico quedaría sin clasificar y el alta sería
    /// papel mojado. Se dice tal cual en vez de dejar un formulario vacío.
    /// </summary>
    public async Task<List<CriterioCaptura>> PlantillaAsync()
    {
        var pais = await PaisAsync();
        if (string.IsNullOrEmpty(pais))
            throw new ErrorApi("Tu usuario no tiene país asignado; sin él no se puede clasificar un médico.");

        var crudo = await _api.ObtenerAsync<List<JsonElement>>($"/categorizacion/plantilla?pais_codigo={pais}");
        return crudo.Select(c => new CriterioCaptura
        {
            Campo = ServicioSincronizacion.Texto(c, "campo") ?? "",
            Etiqueta = ServicioSincronizacion.Texto(c, "etiqueta") ?? "",
            Tipo = ServicioSincronizacion.Texto(c, "tipo") ?? "TEXTO",
            Requerido = !c.TryGetProperty("requerido", out var r) || r.ValueKind != JsonValueKind.False,
            Opciones = c.TryGetProperty("opciones", out var o) && o.ValueKind == JsonValueKind.Array
                ? o.EnumerateArray().Select(x => x.GetString() ?? "").Where(s => s.Length > 0).ToList()
                : new List<string>(),
        }).Where(c => c.Campo.Length > 0).ToList();
    }

    /// <summary>Médicos ya registrados en otros paneles del país, para copiar sin reescribir la ficha.</summary>
    public async Task<List<MedicoExistente>> MedicosExistentesAsync()
    {
        var crudo = await _api.ObtenerAsync<List<JsonElement>>("/visita/medicos/existentes");
        return crudo.Select(m => new MedicoExistente
        {
            Id = ServicioSincronizacion.Entero(m, "id"),
            Nombre = ServicioSincronizacion.Texto(m, "nombre_completo")
                     ?? ServicioSincronizacion.Texto(m, "nombre") ?? "(sin nombre)",
            Especialidad = ServicioSincronizacion.Texto(m, "especialidad_nombre")
                           ?? ServicioSincronizacion.Texto(m, "especialidad"),
            Centro = ServicioSincronizacion.Texto(m, "centro_trabajo")
                     ?? ServicioSincronizacion.Texto(m, "centro_medico"),
            Telefono = ServicioSincronizacion.Texto(m, "telefono"),
            Exequatur = ServicioSincronizacion.Texto(m, "exequatur"),
            Direccion = ServicioSincronizacion.Texto(m, "direccion"),
            VisitadoPor = ServicioSincronizacion.Texto(m, "vm_nombre"),
        }).Where(m => m.Id > 0).ToList();
    }

    public async Task<List<(int Id, string Nombre)>> EspecialidadesAsync()
    {
        var crudo = await _api.ObtenerAsync<List<JsonElement>>("/visita/especialidades");
        return crudo.Select(e => (ServicioSincronizacion.Entero(e, "id"),
                                  ServicioSincronizacion.Texto(e, "nombre") ?? ""))
                    .Where(e => e.Item1 > 0).ToList();
    }

    /// <summary>
    /// Da de alta un médico. Queda PENDIENTE hasta que el Gerente de Distrito lo
    /// apruebe, y la categoría no se manda ni se recibe: la calcula el sistema al
    /// aprobar, a partir de la clasificación.
    /// </summary>
    public async Task CrearMedicoAsync(Dictionary<string, object?> cuerpo, bool confirmarDuplicado)
    {
        if (confirmarDuplicado) cuerpo["confirmar_duplicado"] = true;
        try
        {
            await _api.EnviarJsonAsync<JsonElement>("/visita/medicos", cuerpo);
        }
        catch (ErrorApi e) when (e.Codigo == HttpStatusCode.Conflict)
        {
            // El 409 del alta de médico trae `{mensaje, duplicados}` — el cliente debe
            // enseñar las coincidencias y dejar decidir, no tragárselas.
            throw TraducirDuplicado(e);
        }
    }

    // ── Farmacias ────────────────────────────────────────────────────────────

    /// <summary>
    /// Busca en el maestro ANTES de dejar dar de alta (regla F25).
    ///
    /// El formulario de creación solo se habilita si esta búsqueda no encuentra nada. Es
    /// lo que evita la mitad de los duplicados: casi siempre la farmacia ya está y lo
    /// que hace falta es agregarla al panel, no crearla otra vez.
    /// </summary>
    public async Task<List<FarmaciaMaestro>> BuscarFarmaciaAsync(bool esCadena, string? cadena,
                                                                 string? sucursal, string? nombre)
    {
        var q = new List<string> { $"es_cadena={(esCadena ? "true" : "false")}" };
        if (!string.IsNullOrWhiteSpace(cadena)) q.Add($"cadena={Uri.EscapeDataString(cadena)}");
        if (!string.IsNullOrWhiteSpace(sucursal)) q.Add($"sucursal={Uri.EscapeDataString(sucursal)}");
        if (!string.IsNullOrWhiteSpace(nombre)) q.Add($"nombre={Uri.EscapeDataString(nombre)}");

        var r = await _api.ObtenerAsync<JsonElement>("/farmacias/maestro/buscar?" + string.Join("&", q));
        if (!r.TryGetProperty("duros", out var duros) || duros.ValueKind != JsonValueKind.Array)
            return new List<FarmaciaMaestro>();

        return duros.EnumerateArray().Select(f => new FarmaciaMaestro
        {
            Id = ServicioSincronizacion.Entero(f, "id"),
            Nombre = ServicioSincronizacion.Texto(f, "nombre_completo")
                     ?? ServicioSincronizacion.Texto(f, "nombre") ?? "(sin nombre)",
            Direccion = ServicioSincronizacion.Texto(f, "direccion"),
            Estado = ServicioSincronizacion.Texto(f, "estado"),
        }).ToList();
    }

    /// <summary>Acción A: la farmacia ya existe en el maestro — se agrega al panel.</summary>
    public async Task AgregarFarmaciaAlPanelAsync(int maestroId)
        => await _api.EnviarJsonAsync<JsonElement>("/farmacias/panel/agregar",
               new { maestro_farmacia_id = maestroId });

    /// <summary>Acción B: no existe — se crea, y queda pendiente de aprobación.</summary>
    public async Task CrearFarmaciaAsync(Dictionary<string, object?> cuerpo)
        => await _api.EnviarJsonAsync<JsonElement>("/farmacias/panel/crear", cuerpo);

    // ── Duplicados ───────────────────────────────────────────────────────────

    private static PosibleDuplicado TraducirDuplicado(ErrorApi e)
    {
        var coincidencias = new List<string>();
        var bloqueante = false;
        try
        {
            using var doc = JsonDocument.Parse(e.Message);
            var raiz = doc.RootElement;
            if (raiz.TryGetProperty("duplicados", out var lista) && lista.ValueKind == JsonValueKind.Array)
                foreach (var d in lista.EnumerateArray())
                    coincidencias.Add(d.ValueKind == JsonValueKind.String
                        ? d.GetString() ?? ""
                        : ServicioSincronizacion.Texto(d, "nombre_completo")
                          ?? ServicioSincronizacion.Texto(d, "nombre") ?? d.ToString());
            bloqueante = (ServicioSincronizacion.Texto(raiz, "tipo") ?? "") == "duro";
        }
        catch
        {
            // El detalle no siempre es JSON (un duplicado duro llega como texto). Se
            // reconoce por su contenido: es la palabra que usa el servidor.
            coincidencias.Add(e.Message);
            bloqueante = e.Message.Contains("exequ", StringComparison.OrdinalIgnoreCase)
                      || e.Message.Contains("cédula", StringComparison.OrdinalIgnoreCase)
                      || e.Message.Contains("cedula", StringComparison.OrdinalIgnoreCase);
        }
        return new PosibleDuplicado("Puede que este médico ya esté registrado.",
                                    coincidencias.Where(c => c.Length > 0).ToList(), bloqueante);
    }
}
