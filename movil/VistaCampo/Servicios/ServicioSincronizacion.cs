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
        Aviso = null;   // cada pasada parte de cero: un aviso viejo miente sobre el estado
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
                catch (ErrorApi e) when (EsReintentable(e))
                {
                    // El servidor contestó, pero lo que dijo NO es «tu dato está mal».
                    //
                    // Medido en el teléfono: una no-visita perfectamente válida quedó
                    // como «No entró — No se pudo validar las credenciales». Era un 401:
                    // el token había caducado y el refresco tampoco valía. La captura no
                    // tenía ningún problema, y la app la dio por perdida y siguió — con
                    // un «Guardado. Subiendo…» en pantalla que ya no era verdad.
                    //
                    // Un fallo de sesión o del servidor se reintenta; solo se marca como
                    // rechazado lo que el servidor rechaza POR SU CONTENIDO.
                    envio.Intentos++;
                    Aviso = e.Codigo == System.Net.HttpStatusCode.Unauthorized
                        ? "Tu sesión venció. Vuelve a entrar y tu trabajo subirá solo."
                        : "El servidor no está respondiendo bien; se reintentará solo.";
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

    /// <summary>
    /// Lo que el visitador ve cuando la cola no puede seguir por algo que no es su dato.
    /// Vacío mientras todo va bien.
    /// </summary>
    public string? Aviso { get; private set; }

    /// <summary>
    /// ¿Este fallo dice «tu dato está mal» o «ahora no puedo»?
    ///
    /// Solo lo primero justifica marcar la captura como rechazada, que es una decisión
    /// que el visitador tiene que ir a deshacer a mano. Sesión vencida (401), permiso
    /// momentáneo (403), límite de peticiones (429) y cualquier 5xx son del servidor o
    /// del momento, no del trabajo hecho en la calle: se reintentan.
    /// </summary>
    private static bool EsReintentable(ErrorApi e)
    {
        if (e.Codigo is null) return true;                    // sin respuesta
        var n = (int)e.Codigo.Value;
        return n == 401 || n == 403 || n == 429 || n >= 500;
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
            case "muestras":
                {
                    // Van en su PROPIO envío, después de la visita y como la suite: el
                    // servidor las registra por médico (`/visita/muestras`), no dentro de
                    // la visita. Separadas, un fallo aquí no arrastra a la visita —que es
                    // el dato que no se puede perder— y la cola las reintenta sola.
                    // No llevan `hace_minutos`: no son un hecho con hora, son un conteo.
                    await _api.EnviarJsonAsync<JsonElement>("/visita/muestras",
                        JsonSerializer.Deserialize<Dictionary<string, object?>>(envio.Cuerpo)!);
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
                Provincia = Texto(m, "provincia"),
                // `especialidad_nombre` y `centro_trabajo`, que es lo que manda el
                // servidor. Se leia "especialidad" y "centro_medico" —dos claves que no
                // existen— asi que el subtitulo salia VACIO en las 199 fichas y el Panel
                // era una lista de nombres con un hueco debajo. Tercera vez que un nombre
                // de campo equivocado se ve como «ese medico no tiene esos datos».
                Especialidad = Texto(m, "especialidad_nombre") ?? Texto(m, "especialidad"),
                Centro = Texto(m, "centro_trabajo") ?? Texto(m, "centro_medico"),
                Categoria = Texto(m, "categoria"),
                EstadoAprobacion = Texto(m, "estado_aprobacion") ?? "APROBADO",
                Activo = !m.TryGetProperty("activo", out var a) || a.GetBoolean(),
                EsTop = m.TryGetProperty("es_top", out var t) && t.ValueKind == JsonValueKind.True,
            }).Where(m => m.Id > 0));

            var agenda = await _api.ObtenerAsync<List<JsonElement>>("/visita/agenda-hoy");
            await _base.ReemplazarAgendaAsync(agenda.Select(a => new ItemAgenda
            {
                MedicoId = Entero(a, "medico_id"),
                Nombre = Texto(a, "nombre") ?? "(sin nombre)",
                TipoVisita = Texto(a, "tipo_visita") ?? "V",
                // El servidor manda `estado` ("pendiente"|"registrada"), NO un booleano
                // `registrada`. Preguntando por la clave que no existe, TODAS las citas
                // quedaban en pendiente y el ✓ de la agenda no aparecía nunca — sin un
                // solo error: una agenda entera de pendientes es perfectamente creíble.
                Registrada = (Texto(a, "estado") ?? "pendiente") == "registrada",
                NoVisita = a.TryGetProperty("no_visita", out var nv) && nv.ValueKind == JsonValueKind.True,
                Especialidad = Texto(a, "especialidad"),
                Centro = Texto(a, "centro_trabajo"),
                Provincia = Texto(a, "provincia"),
                Categoria = Texto(a, "categoria"),
                DiaSemana = Texto(a, "dia_semana"),
                HoraEstimada = Texto(a, "hora_estimada"),
                Grupo = Texto(a, "grupo") ?? "ciclo",
            }).Where(a => a.MedicoId > 0));

            var plan = await _api.ObtenerAsync<List<JsonElement>>("/visita/planeacion");
            // La planeación viene por `medico_id` SIN el nombre: el nombre se resuelve
            // contra el panel que se acaba de descargar. Antes se leía una clave `medico`
            // que el servidor nunca manda, y el `??` la convertía en «(sin nombre)» —
            // las 25 filas del plan decían lo mismo, sin un solo error, y eso se lee como
            // «mi planeación está sin médicos» y no como «la app buscó donde no era».
            var nombres = (await _base.MedicosAsync()).ToDictionary(m => m.Id, m => m.Nombre);
            await _base.ReemplazarPlanAsync(plan.Select(p =>
            {
                var id = Entero(p, "medico_id");
                return new ItemPlan
                {
                    MedicoId = id,
                    Medico = nombres.TryGetValue(id, out var n) ? n : "(no está en tu panel)",
                    TipoVisita = Texto(p, "tipo_visita") ?? "V",
                    Semana = Entero(p, "semana"),
                    Dia = Texto(p, "dia_semana"),
                    Hora = Texto(p, "hora_estimada"),
                };
            }));

            // La parrilla del ciclo: qué productos puede promocionar el visitador. Sin
            // línea explícita el servidor usa la del propio VM, que es justo lo que hace
            // falta aquí. El VM solo ve las parrillas PUBLICADAS.
            var productos = await _api.ObtenerAsync<List<JsonElement>>("/visita/parrilla");
            await _base.ReemplazarProductosAsync(productos.Select(p => new ProductoParrilla
            {
                Id = Entero(p, "id"),
                Nombre = Texto(p, "nombre") ?? Texto(p, "producto") ?? "(sin nombre)",
                // El CÓDIGO, que es con lo que el servidor cruza el registro contra la
                // parrilla y contra las muestras. Hoy coincide con el nombre en los datos
                // que hay, pero solo por casualidad: `nombre` cae al código únicamente
                // cuando no hay ficha de producto. Mandar el nombre funcionaría hasta el
                // día en que dejaran de coincidir, y entonces el cruce daría cero sin avisar.
                Codigo = Texto(p, "producto") ?? Texto(p, "nombre") ?? "",
                MensajeClave = Texto(p, "mensaje_clave"),
                Prioridad = Entero(p, "prioridad"),
                MetaMuestras = Entero(p, "meta_muestras"),
            }).Where(p => p.Id > 0));

            var farmacias = await _api.ObtenerAsync<List<JsonElement>>("/farmacias/panel");
            await _base.ReemplazarFarmaciasAsync(farmacias.Select(f => new FarmaciaPanel
            {
                // `panel_id`, NO `id`: el servidor manda la fila del PANEL, y es ese
                // número el que después identifica la farmacia al registrar la visita
                // (`POST /farmacias/{panel_id}/visita`). Leer `id` devolvía 0 en todas,
                // el filtro de abajo las descartaba y el panel salía VACÍO sin un solo
                // error — la lista simplemente no tenía nada, que es indistinguible de
                // «este visitador no tiene farmacias».
                Id = Entero(f, "panel_id"),
                Nombre = Texto(f, "nombre_completo") ?? Texto(f, "nombre") ?? "(sin nombre)",
                Direccion = Texto(f, "direccion"),
                Encargado = Texto(f, "encargado"),
                EsCadena = f.TryGetProperty("es_cadena", out var ec) && ec.ValueKind == JsonValueKind.True,
                UltimoComentario = Texto(f, "ultimo_comentario"),
                VisitadaHoy = f.TryGetProperty("visitada_hoy", out var vh) && vh.ValueKind == JsonValueKind.True,
                VisitadaCiclo = f.TryGetProperty("visitada_ciclo", out var vc) && vc.ValueKind == JsonValueKind.True,
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
