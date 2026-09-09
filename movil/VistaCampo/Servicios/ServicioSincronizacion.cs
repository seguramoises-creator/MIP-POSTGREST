using System.Text.Json;
using VistaCampo.Datos;
using VistaCampo.Modelos;

namespace VistaCampo.Servicios;

/// <summary>
/// La cola de salida: lo que el visitador capturó y todavía no ha subido.
///
/// TODA captura entra aquí primero y la pantalla confirma contra esta escritura, no
/// contra la red. Es la decisión que hace la app usable: el visitador termina la visita
/// en el parqueo del edificio médico, donde no hay señal, y necesita ver que su trabajo
/// quedó guardado.
///
/// El caso que de verdad importa no es «no llegó» sino «llegó y se perdió la respuesta».
/// Por eso cada envío lleva un `uuid_cliente` que viaja al servidor: si el reintento
/// llega dos veces, el servidor devuelve la visita que ya existe en vez de crear otra.
/// </summary>
public class ServicioSincronizacion
{
    private readonly ApiCliente _api;
    private readonly BaseLocal _base;
    private readonly SemaphoreSlim _candado = new(1, 1);

    public ServicioSincronizacion(ApiCliente api, BaseLocal baseLocal)
    {
        _api = api;
        _base = baseLocal;
    }

    /// <summary>Se dispara cuando la cola cambia, para refrescar el indicador de la barra.</summary>
    public event Action? Cambio;

    public int Pendientes { get; private set; }
    public int Rechazados { get; private set; }

    public async Task RefrescarContadoresAsync()
    {
        Pendientes = await _base.ContarAsync(EstadoEnvio.Pendiente);
        Rechazados = await _base.ContarAsync(EstadoEnvio.Rechazado);
        Cambio?.Invoke();
    }

    /// <summary>Encola una captura y trata de subirla enseguida si hay red.</summary>
    public async Task EncolarAsync(EnvioPendiente envio)
    {
        await _base.EncolarAsync(envio);
        await RefrescarContadoresAsync();
        if (HayRed) _ = ProcesarAsync();
    }

    public static bool HayRed => Connectivity.Current.NetworkAccess == NetworkAccess.Internet;

    /// <summary>
    /// Sube lo que haya pendiente, en orden de captura.
    ///
    /// El orden importa: la foto de una visita no puede subir antes que la visita, y dos
    /// visitas al mismo médico se distinguen por su hora. Procesar en paralelo iría más
    /// rápido y rompería ambas cosas.
    /// </summary>
    public async Task ProcesarAsync()
    {
        if (!HayRed) return;
        if (!await _candado.WaitAsync(0)) return;   // ya hay una pasada corriendo
        try
        {
            foreach (var envio in await _base.PorEnviarAsync())
            {
                try
                {
                    await SubirAsync(envio);
                    envio.Estado = (int)EstadoEnvio.Enviado;
                    envio.Motivo = null;
                }
                catch (ErrorApi e) when (e.SinRespuesta)
                {
                    // Sin red: se queda pendiente y se reintenta más tarde. NO es un
                    // rechazo — marcarlo como tal borraría trabajo válido.
                    envio.Intentos++;
                    break;
                }
                catch (ErrorApi e)
                {
                    // El servidor contestó y dijo que no. Se marca RECHAZADO con su
                    // motivo y se deja a la vista: el visitador tiene derecho a saber
                    // que su trabajo no entró. Nunca se borra en silencio.
                    envio.Estado = (int)EstadoEnvio.Rechazado;
                    envio.Motivo = e.Message;
                }
                envio.Intentos++;
                await _base.ActualizarAsync(envio);
            }
            await _base.LimpiarEnviadosAsync();
        }
        finally
        {
            _candado.Release();
            await RefrescarContadoresAsync();
        }
    }

    private async Task SubirAsync(EnvioPendiente envio)
    {
        switch (envio.Tipo)
        {
            case "visita":
            case "no-visita":
            case "farmacia":
                {
                    var cuerpo = ConHaceMinutos(envio);
                    var ruta = envio.Tipo switch
                    {
                        "visita" => "/visita/registrar",
                        "no-visita" => "/visita/no-visita",
                        _ => $"/farmacias/{envio.PanelId}/visita",
                    };
                    var r = await _api.EnviarJsonAsync<JsonElement>(ruta, cuerpo);
                    if (r.TryGetProperty("id", out var id) && id.TryGetInt32(out var n))
                        await EnlazarFotosAsync(envio.UuidCliente, n, envio.Tipo == "farmacia");
                    break;
                }
            case "foto":
                {
                    if (envio.VisitaServidorId is null)
                        throw new ErrorApi("La visita de esta foto todavía no ha subido.",
                                           System.Net.HttpStatusCode.Conflict);
                    var ruta = envio.PanelId is null
                        ? $"/visita/{envio.VisitaServidorId}/foto"
                        : $"/farmacias/{envio.VisitaServidorId}/foto";
                    await _api.SubirArchivoAsync<JsonElement>(ruta, envio.RutaArchivo!, "image/jpeg");
                    if (envio.RutaArchivo is not null && File.Exists(envio.RutaArchivo))
                        File.Delete(envio.RutaArchivo);
                    break;
                }
        }
    }

    /// <summary>
    /// Recalcula `hace_minutos` EN EL MOMENTO DEL ENVÍO, no al capturar.
    ///
    /// El servidor no acepta una hora del teléfono —se puede cambiar a mano— sino
    /// «hace cuántos minutos», que resta a su propio reloj. Mandar el valor calculado al
    /// capturar haría que una visita encolada media hora se registrara con media hora de
    /// adelanto. El servidor tope es 60: pasado eso rechazará, y por eso la cola avisa
    /// desde los 45.
    /// </summary>
    private static Dictionary<string, object?> ConHaceMinutos(EnvioPendiente envio)
    {
        var cuerpo = JsonSerializer.Deserialize<Dictionary<string, object?>>(envio.Cuerpo)
                     ?? new Dictionary<string, object?>();
        cuerpo["hace_minutos"] = Math.Min(60, envio.MinutosDesdeCaptura);
        cuerpo["uuid_cliente"] = envio.UuidCliente;
        return cuerpo;
    }

    /// <summary>
    /// Las fotos se encolan ANTES de que la visita tenga id de servidor (no existe aún).
    /// Cuando la visita sube, sus fotos reciben el id que les tocaba.
    ///
    /// Van separadas a propósito: una foto que falla —3 MB, señal débil— no debe tumbar
    /// la visita, que es el dato que de verdad cuenta.
    /// </summary>
    private async Task EnlazarFotosAsync(string uuidVisita, int idServidor, bool esFarmacia)
    {
        foreach (var f in await _base.ColaAsync())
        {
            if (f.Tipo != "foto" || f.VisitaServidorId is not null) continue;
            if (f.Cuerpo != uuidVisita) continue;
            f.VisitaServidorId = idServidor;
            f.PanelId = esFarmacia ? idServidor : null;
            await _base.ActualizarAsync(f);
        }
    }

    // ── Descarga de catálogos ────────────────────────────────────────────────

    /// <summary>
    /// Trae del servidor lo que la app necesita para capturar sin red. Si algo falla se
    /// conserva lo que ya había: unos catálogos viejos sirven; ninguno, no.
    /// </summary>
    public async Task<string?> DescargarCatalogosAsync()
    {
        try
        {
            var medicos = await _api.ObtenerAsync<List<JsonElement>>("/visita/medicos");
            await _base.ReemplazarMedicosAsync(medicos.Select(m => new MedicoPanel
            {
                Id = Entero(m, "id"),
                Nombre = Texto(m, "nombre_completo") ?? Texto(m, "nombre") ?? "(sin nombre)",
                Especialidad = Texto(m, "especialidad"),
                Centro = Texto(m, "centro_medico") ?? Texto(m, "centro"),
                Categoria = Texto(m, "categoria"),
                EstadoAprobacion = Texto(m, "estado_aprobacion") ?? "APROBADO",
                Activo = !m.TryGetProperty("activo", out var a) || a.GetBoolean(),
            }).Where(m => m.Id > 0));

            var agenda = await _api.ObtenerAsync<List<JsonElement>>("/visita/agenda-hoy");
            await _base.ReemplazarAgendaAsync(agenda.Select(a => new ItemAgenda
            {
                MedicoId = Entero(a, "medico_id"),
                Nombre = Texto(a, "medico") ?? Texto(a, "nombre") ?? "(sin nombre)",
                TipoVisita = Texto(a, "tipo_visita") ?? "V",
                Registrada = a.TryGetProperty("registrada", out var r) && r.ValueKind == JsonValueKind.True,
            }).Where(a => a.MedicoId > 0));

            var plan = await _api.ObtenerAsync<List<JsonElement>>("/visita/planeacion");
            await _base.ReemplazarPlanAsync(plan.Select(p => new ItemPlan
            {
                MedicoId = Entero(p, "medico_id"),
                Medico = Texto(p, "medico") ?? "(sin nombre)",
                TipoVisita = Texto(p, "tipo_visita") ?? "V",
                Semana = Entero(p, "semana"),
                Dia = Texto(p, "dia"),
            }));

            var farmacias = await _api.ObtenerAsync<List<JsonElement>>("/farmacias/panel");
            await _base.ReemplazarFarmaciasAsync(farmacias.Select(f => new FarmaciaPanel
            {
                Id = Entero(f, "id"),
                Nombre = Texto(f, "nombre_completo") ?? Texto(f, "nombre") ?? "(sin nombre)",
                Direccion = Texto(f, "direccion"),
                EstadoAprobacion = Texto(f, "estado_aprobacion") ?? "APROBADO",
            }).Where(f => f.Id > 0));

            Preferences.Set("ultima_sync", DateTime.UtcNow.ToString("o"));
            return null;
        }
        catch (ErrorApi e) { return e.Message; }
    }

    public static string? Texto(JsonElement e, string campo)
        => e.TryGetProperty(campo, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    public static int Entero(JsonElement e, string campo)
        => e.TryGetProperty(campo, out var v) && v.TryGetInt32(out var n) ? n : 0;
}
