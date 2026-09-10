using System.Collections.ObjectModel;
using System.Text.Json;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Datos;
using VistaCampo.Modelos;
using VistaCampo.Servicios;

namespace VistaCampo.VistaModelos;

/// <summary>
/// La pantalla que más se usa. Objetivo: menos de 20 segundos desde que se abre hasta
/// que la visita queda guardada.
///
/// Todas las reglas del servidor se comprueban AQUÍ antes de dejar guardar. No es
/// desconfianza del servidor —él sigue mandando— sino cuidado con el visitador: perder
/// un comentario escrito de pie en la calle contra un 422 es la clase de cosa que hace
/// que la gente deje de usar una app.
/// </summary>
public partial class RegistrarVista : BaseVista
{
    private readonly BaseLocal _base;
    private readonly ServicioSincronizacion _sync;
    private readonly ServicioInstalacion _instalacion;

    /// <summary>Comentarios que el servidor rechaza por vacíos de contenido.</summary>
    private static readonly HashSet<string> GENERICOS = new(StringComparer.OrdinalIgnoreCase)
    {
        "OK", "VISITA REALIZADA", "SIN NOVEDAD", "NORMAL", "BIEN", "TODO BIEN",
        "SIN COMENTARIOS", "NINGUNO", "N/A", "NA", "VISITA",
    };

    public RegistrarVista(BaseLocal baseLocal, ServicioSincronizacion sync, ServicioInstalacion instalacion)
    {
        _base = baseLocal;
        _sync = sync;
        _instalacion = instalacion;
    }

    // ── Estado de la pantalla ────────────────────────────────────────────────

    [ObservableProperty] private bool _esFarmacia;
    [ObservableProperty] private string _busqueda = "";
    [ObservableProperty] private MedicoPanel? _medico;
    [ObservableProperty] private FarmaciaPanel? _farmacia;
    [ObservableProperty] private string _tipoVisita = "V";
    [ObservableProperty] private string _comentario = "";
    [ObservableProperty] private int _haceMinutos;
    [ObservableProperty] private bool _acompanado;
    [ObservableProperty] private bool _esNoVisita;
    [ObservableProperty] private string? _causa;
    [ObservableProperty] private string? _rutaFoto;
    [ObservableProperty] private string? _ubicacion;

    public ObservableCollection<MedicoPanel> Medicos { get; } = new();
    public ObservableCollection<FarmaciaPanel> Farmacias { get; } = new();
    public ObservableCollection<ProductoParrilla> Productos { get; } = new();

    public bool HayProductos => Productos.Count > 0;

    /// <summary>Los productos marcados, para el resumen de la pantalla.</summary>
    public string ResumenProductos
    {
        get
        {
            var marcados = Productos.Where(p => p.Elegido).Select(p => p.Nombre).ToList();
            return marcados.Count == 0
                ? "Ninguno marcado."
                : $"{marcados.Count}: {string.Join(", ", marcados)}";
        }
    }

    /// <summary>El catálogo de causas del servidor, con los mismos textos exactos.</summary>
    public List<string> Causas { get; } = new()
    {
        "Médico en Vacaciones",
        "Médico Enfermo / Incapacitado",
        "Médico en Congreso o Evento Científico",
        "Consultorio Cerrado (sin aviso previo)",
        "Zona Inaccesible (transporte / clima)",
        "Reprogramada por el Médico",
    };

    public List<int> Minutos { get; } = new() { 0, 15, 30, 45, 60 };

    public bool PuedeCapturar => _instalacion.Config.PuedeCapturar;
    public bool EsVista => TipoVisita == "V";
    public bool EsRevisita => TipoVisita == "R";
    public string Elegido => EsFarmacia ? Farmacia?.Nombre ?? "" : Medico?.Nombre ?? "";

    /// <summary>Cuántos caracteres faltan para el mínimo del servidor.</summary>
    public string AyudaComentario
    {
        get
        {
            var n = (Comentario ?? "").Trim().Length;
            if (n == 0) return "Describe algo concreto de la visita (mínimo 10 caracteres).";
            if (n < 10) return $"Faltan {10 - n} caracteres.";
            return GENERICOS.Contains((Comentario ?? "").Trim())
                ? "Ese comentario es demasiado genérico; el servidor lo va a rechazar."
                : " ";
        }
    }

    partial void OnComentarioChanged(string value)
    {
        OnPropertyChanged(nameof(AyudaComentario));
        GuardarCommand.NotifyCanExecuteChanged();
    }

    partial void OnTipoVisitaChanged(string value)
    {
        OnPropertyChanged(nameof(EsVista));
        OnPropertyChanged(nameof(EsRevisita));
    }

    partial void OnMedicoChanged(MedicoPanel? value)
    {
        OnPropertyChanged(nameof(Elegido));
        GuardarCommand.NotifyCanExecuteChanged();
        // Un médico pendiente de aprobación no admite visita: el servidor lo rechaza y
        // más vale decirlo al elegirlo que después de escribir el comentario.
        Error = value is not null && !value.SePuedeVisitar
            ? "Este médico está pendiente de aprobación del Gerente de Distrito — todavía no puedes registrarle visita."
            : null;
    }

    partial void OnFarmaciaChanged(FarmaciaPanel? value)
    {
        OnPropertyChanged(nameof(Elegido));
        GuardarCommand.NotifyCanExecuteChanged();
        Error = value is not null && !value.SePuedeVisitar
            ? "Esta farmacia está pendiente de aprobación — todavía no puedes registrarle visita."
            : null;
    }

    partial void OnEsFarmaciaChanged(bool value)
    {
        Medico = null; Farmacia = null; Busqueda = "";
        _ = FiltrarAsync();
    }

    partial void OnEsNoVisitaChanged(bool value) => GuardarCommand.NotifyCanExecuteChanged();
    partial void OnCausaChanged(string? value) => GuardarCommand.NotifyCanExecuteChanged();
    partial void OnBusquedaChanged(string value) => _ = FiltrarAsync();

    // ── Carga y filtrado ─────────────────────────────────────────────────────

    [RelayCommand]
    public async Task CargarAsync()
    {
        // El aviso de la vez anterior NO sobrevive a volver a la pestaña. Shell mantiene
        // viva la página de cada pestaña, así que un «Guardado. Subiendo…» de hace media
        // hora seguía en pantalla sobre un formulario vacío: el visitador vuelve a
        // Registrar, ve el mensaje de éxito y cree que acaba de guardar algo. Lo que sí
        // se respeta es lo que esté a medio escribir — eso es trabajo suyo.
        Aviso = null;
        Error = null;

        OnPropertyChanged(nameof(PuedeCapturar));
        Productos.Clear();
        foreach (var p in await _base.ProductosAsync())
        {
            p.Elegido = false;   // el catálogo se comparte; la marca es de ESTA visita
            p.PropertyChanged += (_, __) => OnPropertyChanged(nameof(ResumenProductos));
            Productos.Add(p);
        }
        OnPropertyChanged(nameof(HayProductos));
        OnPropertyChanged(nameof(ResumenProductos));
        await FiltrarAsync();
    }

    private async Task FiltrarAsync()
    {
        var q = (Busqueda ?? "").Trim();
        if (EsFarmacia)
        {
            var todas = await _base.FarmaciasAsync();
            Farmacias.Clear();
            foreach (var f in todas.Where(f => q.Length == 0 ||
                     f.Nombre.Contains(q, StringComparison.OrdinalIgnoreCase)).Take(50))
                Farmacias.Add(f);
        }
        else
        {
            var todos = await _base.MedicosAsync();
            Medicos.Clear();
            foreach (var m in todos.Where(m => q.Length == 0 ||
                     m.Nombre.Contains(q, StringComparison.OrdinalIgnoreCase)).Take(50))
                Medicos.Add(m);
        }
    }

    // ── Foto y ubicación ─────────────────────────────────────────────────────

    [RelayCommand]
    private async Task TomarFotoAsync()
    {
        try
        {
            if (!MediaPicker.Default.IsCaptureSupported)
            {
                Aviso = "Este teléfono no permite tomar fotos desde la app.";
                return;
            }
            var foto = await MediaPicker.Default.CapturePhotoAsync();
            if (foto is null) return;   // el visitador canceló, no es un error

            var destino = Path.Combine(FileSystem.CacheDirectory, $"{Guid.NewGuid():N}.jpg");
            await using (var origen = await foto.OpenReadAsync())
            await using (var salida = File.Create(destino))
                await origen.CopyToAsync(salida);
            RutaFoto = destino;
        }
        catch (Exception e)
        {
            // La foto es OPCIONAL: si la cámara falla o el permiso se deniega, la visita
            // se registra igual. Bloquearla por una foto sería perder el dato que cuenta.
            Aviso = "No se pudo tomar la foto; la visita se puede registrar sin ella. " + e.Message;
        }
    }

    [RelayCommand]
    private void QuitarFoto()
    {
        if (RutaFoto is not null && File.Exists(RutaFoto)) File.Delete(RutaFoto);
        RutaFoto = null;
    }

    /// <summary>
    /// Pide la ubicación con un tope de 8 segundos y sigue sin ella si no llega.
    ///
    /// Dentro de un edificio médico el GPS a menudo no fija. Bloquear el registro por
    /// eso haría la app inservible justo donde se usa; las coordenadas son opcionales
    /// en el servidor por la misma razón.
    /// </summary>
    private async Task<Location?> UbicacionAsync()
    {
        try
        {
            var permiso = await Permissions.CheckStatusAsync<Permissions.LocationWhenInUse>();
            if (permiso != PermissionStatus.Granted)
                permiso = await Permissions.RequestAsync<Permissions.LocationWhenInUse>();
            if (permiso != PermissionStatus.Granted) return null;

            return await Geolocation.Default.GetLocationAsync(new GeolocationRequest(
                GeolocationAccuracy.Medium, TimeSpan.FromSeconds(8)));
        }
        catch { return null; }
    }

    // ── Guardar ──────────────────────────────────────────────────────────────

    private bool PuedeGuardar()
    {
        if (!PuedeCapturar) return false;
        if (EsFarmacia) return Farmacia?.SePuedeVisitar == true;
        if (Medico?.SePuedeVisitar != true) return false;
        if (EsNoVisita) return !string.IsNullOrWhiteSpace(Causa);
        var c = (Comentario ?? "").Trim();
        return c.Length >= 10 && !GENERICOS.Contains(c);
    }

    [RelayCommand(CanExecute = nameof(PuedeGuardar))]
    private async Task GuardarAsync()
    {
        await EjecutarAsync(async () =>
        {
            var ubic = await UbicacionAsync();
            Ubicacion = ubic is null ? "Sin señal de GPS" : $"{ubic.Latitude:F5}, {ubic.Longitude:F5}";

            var envio = new EnvioPendiente
            {
                // La hora de captura es la que manda: `hace_minutos` se calcula al
                // ENVIAR, contra este momento, no ahora.
                CapturadoUtc = DateTime.UtcNow.AddMinutes(-HaceMinutos),
                Etiqueta = Elegido,
            };

            if (EsFarmacia)
            {
                envio.Tipo = "farmacia";
                envio.PanelId = Farmacia!.Id;
                envio.Cuerpo = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["comentario"] = string.IsNullOrWhiteSpace(Comentario) ? null : Comentario.Trim(),
                    ["ejecutada"] = !EsNoVisita,
                    ["causa_no_visita"] = EsNoVisita ? Causa : null,
                    ["latitud"] = ubic?.Latitude,
                    ["longitud"] = ubic?.Longitude,
                });
            }
            else if (EsNoVisita)
            {
                envio.Tipo = "no-visita";
                envio.Cuerpo = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["medico_id"] = Medico!.Id,
                    ["causa"] = Causa,
                    ["comentario"] = string.IsNullOrWhiteSpace(Comentario) ? null : Comentario.Trim(),
                });
            }
            else
            {
                envio.Tipo = "visita";
                envio.Cuerpo = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["medico_id"] = Medico!.Id,
                    ["tipo_visita"] = TipoVisita,
                    ["comentario"] = Comentario.Trim(),
                    ["acompanado"] = Acompanado,
                    ["latitud"] = ubic?.Latitude,
                    ["longitud"] = ubic?.Longitude,
                    // El servidor espera producto + número de mención (1ª, 2ª, 3ª…). El
                    // orden en que se marcan ES la mención: la primera que se menciona
                    // es la que se llevó la visita.
                    ["productos"] = Productos.Where(p => p.Elegido)
                        .Select((p, i) => new { producto = p.Nombre, mencion = i + 1 })
                        .ToList(),
                });
            }

            await _sync.EncolarAsync(envio);

            if (RutaFoto is not null)
            {
                // La foto va como envío APARTE, apuntando a la visita por su huella: la
                // visita todavía no tiene id de servidor. Separarlas evita que una foto
                // de 3 MB con mala señal se lleve por delante el registro.
                await _sync.EncolarAsync(new EnvioPendiente
                {
                    Tipo = "foto",
                    Cuerpo = envio.UuidCliente,
                    RutaArchivo = RutaFoto,
                    Etiqueta = $"Foto · {Elegido}",
                    CapturadoUtc = envio.CapturadoUtc,
                });
            }

            Aviso = ServicioSincronizacion.HayRed
                ? "Guardado. Subiendo…"
                : "Guardado en tu teléfono. Se enviará solo cuando haya señal.";
            Limpiar();
        });
    }

    private void Limpiar()
    {
        Medico = null; Farmacia = null; Busqueda = "";
        Comentario = ""; TipoVisita = "V"; HaceMinutos = 0;
        Acompanado = false; EsNoVisita = false; Causa = null;
        RutaFoto = null;
        foreach (var p in Productos) p.Elegido = false;
        OnPropertyChanged(nameof(ResumenProductos));
    }

    [RelayCommand] private void ElegirVista() => TipoVisita = "V";
    [RelayCommand] private void ElegirRevisita() => TipoVisita = "R";
}
