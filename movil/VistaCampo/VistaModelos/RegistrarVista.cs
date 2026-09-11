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
/// LLEVA LA MISMA INFORMACIÓN QUE LA SUITE, y en el mismo orden: médicos de hoy con su
/// categoría y su día, hora real de la visita, resumen, productos con las muestras que
/// propone la parrilla, comentario y acompañamiento. Antes era una lista de nombres y un
/// formulario suelto: el visitador tenía que reconocer al médico solo por el nombre y
/// decidir muestras de memoria. Los datos ya venían del servidor —`/visita/agenda-hoy`
/// manda especialidad, categoría, centro, día y hora, y `/visita/parrilla` manda la meta
/// de muestras—; se estaban tirando por el camino al guardarlos en el teléfono.
///
/// Todas las reglas del servidor se comprueban AQUÍ antes de dejar guardar. No es
/// desconfianza del servidor —él sigue mandando— sino cuidado con el visitador: perder
/// un comentario escrito de pie en la calle contra un 422 es la clase de cosa que hace
/// que la gente deje de usar una app.
/// </summary>
public partial class RegistrarVista : BaseVista
{
    private readonly ApiCliente _api;
    private readonly BaseLocal _base;
    private readonly ServicioSincronizacion _sync;
    private readonly ServicioInstalacion _instalacion;

    /// <summary>Comentarios que el servidor rechaza por vacíos de contenido.</summary>
    private static readonly HashSet<string> GENERICOS = new(StringComparer.OrdinalIgnoreCase)
    {
        "OK", "VISITA REALIZADA", "SIN NOVEDAD", "NORMAL", "BIEN", "TODO BIEN",
        "SIN COMENTARIOS", "NINGUNO", "N/A", "NA", "VISITA",
    };

    public RegistrarVista(ApiCliente api, BaseLocal baseLocal, ServicioSincronizacion sync,
                          ServicioInstalacion instalacion)
    {
        _api = api;
        _base = baseLocal;
        _sync = sync;
        _instalacion = instalacion;
    }

    // ── Estado de la pantalla ────────────────────────────────────────────────

    [ObservableProperty] private bool _esFarmacia;
    [ObservableProperty] private string _busqueda = "";
    [ObservableProperty] private string _categoria = "Todas";
    [ObservableProperty] private ItemAgenda? _cita;
    [ObservableProperty] private MedicoPanel? _fueraDeAgenda;
    [ObservableProperty] private FarmaciaPanel? _farmacia;
    [ObservableProperty] private string _tipoVisita = "V";
    [ObservableProperty] private string _comentario = "";
    [ObservableProperty] private bool _acompanado;
    [ObservableProperty] private bool _esNoVisita;
    [ObservableProperty] private string? _causa;
    [ObservableProperty] private string? _rutaFoto;
    [ObservableProperty] private double? _latitud;
    [ObservableProperty] private double? _longitud;

    /// <summary>
    /// La hora REAL de la visita, como en la suite: se enseña una hora, no «hace cuántos
    /// minutos». El visitador sabe a qué hora entró a la consulta; traducirlo a minutos
    /// era pedirle una resta.
    ///
    /// Lo que viaja al servidor sigue siendo `hace_minutos`, calculado AL ENVIAR: la hora
    /// del teléfono se puede cambiar a mano, y una visita encolada media hora se
    /// registraría adelantada. La hora es de la pantalla; los minutos son del protocolo.
    /// </summary>
    [ObservableProperty] private TimeSpan _horaReal = DateTime.Now.TimeOfDay;

    public ObservableCollection<ItemAgenda> DelDia { get; } = new();
    public ObservableCollection<ItemAgenda> DelCiclo { get; } = new();
    public ObservableCollection<MedicoPanel> Panel { get; } = new();
    public ObservableCollection<FarmaciaPanel> FarmaciasPendientes { get; } = new();
    public ObservableCollection<FarmaciaPanel> FarmaciasVisitadas { get; } = new();
    private ObservableCollection<ProductoParrilla> _productos = new();

    /// <summary>
    /// Se REEMPLAZA entera al recargar, nunca se vacía con Clear(). La ficha que la pinta
    /// vive en una plantilla que se monta y desmonta con cada visita: una ficha ya cerrada
    /// seguía escuchando la lista, y al vaciarla MAUI intentaba desmontar vistas de Android
    /// ya destruidas → ObjectDisposedException y la app se cerraba (7 cierres registrados en
    /// el teléfono entre el 10 y el 11 de septiembre, todos en este Clear). Con una lista
    /// nueva, las fichas viejas se quedan con la suya y nadie toca vistas muertas.
    /// </summary>
    public ObservableCollection<ProductoParrilla> Productos
    {
        get => _productos;
        private set => SetProperty(ref _productos, value);
    }
    public ObservableCollection<VisitaDelDia> RegistradasHoy { get; } = new();
    public ObservableCollection<VisitaDelDia> Anteriores { get; } = new();

    public List<string> Categorias { get; } = new() { "Todas", "A", "B", "C", "D" };

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

    public List<string> Menciones { get; } = new() { "1ª mención", "2ª mención", "3ª mención" };

    public bool PuedeCapturar => _instalacion.Config.PuedeCapturar;
    public bool EsVista => TipoVisita == "V";
    public bool EsRevisita => TipoVisita == "R";
    public bool HayProductos => Productos.Count > 0;
    public bool HayDelDia => DelDia.Count > 0;
    public bool HayDelCiclo => DelCiclo.Count > 0;
    public bool HayRegistradas => RegistradasHoy.Count > 0;
    public bool HayFarmaciasPendientes => FarmaciasPendientes.Count > 0;
    public bool HayFarmaciasVisitadas => FarmaciasVisitadas.Count > 0;
    public string TituloFarmaciasPendientes => $"PENDIENTES · {FarmaciasPendientes.Count}";
    public string TituloFarmaciasVisitadas => $"VISITADAS · {FarmaciasVisitadas.Count}";

    /// <summary>«2 activas» — cuántas farmacias aprobadas tiene el visitador en su panel.</summary>
    public string TextoFarmaciasActivas
    {
        get
        {
            var n = FarmaciasPendientes.Count + FarmaciasVisitadas.Count;
            return $"{n} activa{(n == 1 ? "" : "s")}";
        }
    }
    public bool HayAnteriores => Anteriores.Count > 0;
    public bool HaySeleccion => Cita is not null || Farmacia is not null;

    /// <summary>
    /// Qué botón de tipo se puede pulsar. La agenda ya dice cuál es el pendiente: dejar
    /// los dos abiertos invita a registrar una Revisita de un médico cuya Vista no se ha
    /// hecho — que es justo lo que el servidor rechaza DESPUÉS de escribir el comentario.
    /// Fuera de agenda (visita no programada) no hay plan que respetar: se permite elegir.
    /// </summary>
    public bool PuedeElegirVista => Cita is null || Cita.Grupo == "fuera" || Cita.TipoVisita == "V";
    public bool PuedeElegirRevisita => Cita is null || Cita.Grupo == "fuera" || Cita.TipoVisita == "R";

    /// <summary>Titulares de las dos secciones de la agenda, con su contador como la suite.</summary>
    public string TituloDelDia => $"VISITA / REVISITA DEL DÍA · {DelDia.Count}";
    public string TituloDelCiclo => $"VISITA / REVISITA DEL CICLO · {DelCiclo.Count}";

    /// <summary>«3 pendientes» / «Al día» — lo primero que se mira al abrir.</summary>
    public string TextoPendientes
    {
        get
        {
            var n = DelDia.Concat(DelCiclo).Count(a => a.EsPendiente);
            return n == 0 ? "Al día" : $"{n} pendiente{(n == 1 ? "" : "s")}";
        }
    }

    public string TituloRegistradas
    {
        get
        {
            var n = RegistradasHoy.Count;
            return $"{n} visita{(n == 1 ? "" : "s")}";
        }
    }

    public string Elegido => EsFarmacia ? Farmacia?.Nombre ?? "" : Cita?.Nombre ?? "";
    public string DetalleElegido => EsFarmacia ? Farmacia?.Direccion ?? "Sin datos" : Cita?.Detalle ?? "";

    // ── Hora real y ventana de 60 minutos ────────────────────────────────────

    /// <summary>Minutos entre la hora indicada y ahora. Es lo que viaja como `hace_minutos`.</summary>
    public int MinutosAtras
    {
        get
        {
            var m = (int)Math.Round((DateTime.Now.TimeOfDay - HoraReal).TotalMinutes);
            return Math.Max(0, m);   // una hora futura cuenta como «ahora mismo»
        }
    }

    public bool HoraDentroDeVentana => MinutosAtras <= 60;

    public string TextoAhora =>
        $"Ahora {DateTime.Now:HH:mm} · " + (HoraDentroDeVentana ? "dentro de 60 min ✓" : "fuera de 60 min ✗");

    partial void OnHoraRealChanged(TimeSpan value)
    {
        OnPropertyChanged(nameof(MinutosAtras));
        OnPropertyChanged(nameof(HoraDentroDeVentana));
        OnPropertyChanged(nameof(TextoAhora));
        GuardarCommand.NotifyCanExecuteChanged();
    }

    // ── Resumen de la visita ─────────────────────────────────────────────────

    public string TextoTipoResumen => EsRevisita ? "Revisita" : "Vista";
    public int NumProductos => Productos.Count(p => p.Elegido);
    public int NumMuestras => Productos.Where(p => p.Elegido).Sum(p => p.Muestras);
    public string TextoUbicacion => Latitud is null ? "Sin ubicación" : "Ubicación ✓";
    public string TextoFoto => string.IsNullOrEmpty(RutaFoto) ? "Sin foto" : "Foto ✓";

    private void RefrescarResumen()
    {
        foreach (var p in new[] { nameof(NumProductos), nameof(NumMuestras), nameof(TextoTipoResumen),
                                  nameof(TextoUbicacion), nameof(TextoFoto) })
            OnPropertyChanged(p);
    }

    partial void OnRutaFotoChanged(string? value) => RefrescarResumen();
    partial void OnLatitudChanged(double? value) => RefrescarResumen();

    /// <summary>Cuántos caracteres faltan para el mínimo del servidor.</summary>
    public string AyudaComentario
    {
        get
        {
            var n = (Comentario ?? "").Trim().Length;
            if (n == 0) return "Mínimo 10 caracteres · No escribas solo \"Visita OK\"";
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
        OnPropertyChanged(nameof(TextoTipoResumen));
    }

    /// <summary>
    /// Al elegir una cita se preselecciona el tipo que le TOCA, y se bloquea el otro.
    ///
    /// La agenda ya dice cuál es el próximo pendiente (`tipo_visita`): dejar los dos
    /// botones abiertos invita a registrar una Revisita de un médico cuya Vista no se ha
    /// hecho, que es justo lo que el servidor rechaza después de escribir el comentario.
    /// </summary>
    partial void OnCitaChanged(ItemAgenda? value)
    {
        FueraDeAgenda = null;
        foreach (var a in DelDia.Concat(DelCiclo)) a.Activa = ReferenceEquals(a, value);
        if (value is not null)
        {
            Farmacia = null;
            TipoVisita = value.TipoVisita;
            HoraReal = DateTime.Now.TimeOfDay;
            // Elegir a OTRO médico empieza de cero, igual que en la suite. Arrastrar el
            // comentario del anterior es peor que perderlo: se guarda sobre el médico
            // equivocado y nadie lo nota, porque el texto es plausible en los dos.
            LimpiarCaptura();
            Error = null;
            _ = UbicarEnSegundoPlanoAsync();
        }
        NotificarSeleccion();
    }

    partial void OnFueraDeAgendaChanged(MedicoPanel? value)
    {
        if (value is null) return;
        if (!value.SePuedeVisitar)
        {
            Error = "Este médico está pendiente de aprobación del Gerente de Distrito — todavía no puedes registrarle visita.";
            return;
        }
        // Una visita NO PROGRAMADA entra por el mismo camino que una de la agenda: se
        // arma su ficha con lo que el panel sabe del médico. Así el formulario se ve
        // igual y no hay un segundo modo de registrar que mantener.
        Cita = new ItemAgenda
        {
            MedicoId = value.Id,
            Nombre = value.Nombre,
            Especialidad = value.Especialidad,
            Centro = value.Centro,
            Categoria = value.Categoria,
            TipoVisita = "V",
            Grupo = "fuera",
        };
    }

    partial void OnFarmaciaChanged(FarmaciaPanel? value)
    {
        foreach (var f in FarmaciasPendientes.Concat(FarmaciasVisitadas)) f.Activa = ReferenceEquals(f, value);
        if (value is not null)
        {
            Cita = null;
            LimpiarCaptura();
            _ = UbicarEnSegundoPlanoAsync();
        }
        Error = value is not null && !value.SePuedeVisitar
            ? "Esta farmacia está pendiente de aprobación — todavía no puedes registrarle visita."
            : null;
        NotificarSeleccion();
    }

    private void NotificarSeleccion()
    {
        foreach (var p in new[] { nameof(Elegido), nameof(DetalleElegido), nameof(HaySeleccion),
                                  nameof(PuedeElegirVista), nameof(PuedeElegirRevisita) })
            OnPropertyChanged(p);
        GuardarCommand.NotifyCanExecuteChanged();
    }

    partial void OnEsFarmaciaChanged(bool value)
    {
        Cita = null; Farmacia = null; Busqueda = "";
        _ = FiltrarAsync();
    }

    /// <summary>Con «No pude visitar» no hubo visita: no hay hora, ni productos, ni
    /// acompañamiento que registrar. Se esconden, como en la suite.</summary>
    public bool EsVisitaEfectiva => !EsNoVisita;

    partial void OnEsNoVisitaChanged(bool value)
    {
        OnPropertyChanged(nameof(EsVisitaEfectiva));
        GuardarCommand.NotifyCanExecuteChanged();
    }
    partial void OnCausaChanged(string? value) => GuardarCommand.NotifyCanExecuteChanged();
    partial void OnBusquedaChanged(string value) => _ = FiltrarAsync();
    partial void OnCategoriaChanged(string value) => _ = FiltrarAsync();

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
        var productos = await _base.ProductosAsync();
        foreach (var p in productos)
        {
            p.Reiniciar();   // el catálogo se comparte; lo marcado es de ESTA visita
            p.PropertyChanged += (_, __) => RefrescarResumen();
        }
        Productos = new ObservableCollection<ProductoParrilla>(productos);
        OnPropertyChanged(nameof(HayProductos));
        RefrescarResumen();
        await FiltrarAsync();
        await CargarFeedAsync();
    }

    /// <summary>
    /// Lo ya registrado: hoy y antes. Sin conexión NO se vacían las listas ni se enseña
    /// un cero: no saber qué se registró no es lo mismo que no haber registrado nada.
    /// </summary>
    private async Task CargarFeedAsync()
    {
        if (!ServicioSincronizacion.HayRed) return;
        try
        {
            var hoy = await _api.ObtenerAsync<List<JsonElement>>("/visita/mis-visitas-hoy");
            RegistradasHoy.Clear();
            foreach (var v in hoy) RegistradasHoy.Add(AVisita(v));

            var antes = await _api.ObtenerAsync<List<JsonElement>>("/visita/historial?dias=30");
            Anteriores.Clear();
            foreach (var v in antes.Take(30)) Anteriores.Add(AVisita(v));
        }
        catch (ErrorApi)
        {
            // Consultar lo anterior es un extra: que falle no puede impedir REGISTRAR,
            // que es a lo que se abre esta pantalla.
        }
        foreach (var p in new[] { nameof(HayRegistradas), nameof(HayAnteriores), nameof(TituloRegistradas) })
            OnPropertyChanged(p);
        await MarcarEstadosAsync();
    }

    /// <summary>
    /// Marca en la agenda qué está YA en el servidor (feed de hoy) y qué sigue en la cola del
    /// teléfono. Antes todo decía «Registrada ✓», subido o no, y el visitador no podía
    /// saber qué había llegado.
    /// </summary>
    private async Task MarcarEstadosAsync()
    {
        var enCola = new HashSet<int>();
        foreach (var e in await _base.ColaAsync())
        {
            if (e.Estado == (int)EstadoEnvio.Enviado || e.Tipo is not ("visita" or "no-visita")) continue;
            try
            {
                using var d = JsonDocument.Parse(e.Cuerpo);
                enCola.Add(ServicioSincronizacion.Entero(d.RootElement, "medico_id"));
            }
            catch (JsonException) { }
        }
        var hoyServidor = RegistradasHoy.Where(v => v.Ejecutada).Select(v => v.MedicoId).ToHashSet();
        foreach (var a in DelDia.Concat(DelCiclo))
        {
            a.PorEnviar = enCola.Contains(a.MedicoId);
            a.EnServidorHoy = hoyServidor.Contains(a.MedicoId);
        }
    }

    private static VisitaDelDia AVisita(JsonElement v) => new()
    {
        Id = ServicioSincronizacion.Entero(v, "id"),
        MedicoId = ServicioSincronizacion.Entero(v, "medico_id"),
        Medico = ServicioSincronizacion.Texto(v, "medico") ?? "(sin nombre)",
        Tipo = ServicioSincronizacion.Texto(v, "tipo_visita") ?? "V",
        Hora = (ServicioSincronizacion.Texto(v, "hora") ?? "").Replace('T', ' '),
        Ejecutada = !v.TryGetProperty("ejecutada", out var e) || e.ValueKind != JsonValueKind.False,
        TieneGps = v.TryGetProperty("tiene_gps", out var g) && g.ValueKind == JsonValueKind.True,
        TieneFoto = v.TryGetProperty("tiene_foto", out var f) && f.ValueKind == JsonValueKind.True,
    };

    private async Task FiltrarAsync()
    {
        var q = (Busqueda ?? "").Trim();
        var cat = Categoria == "Todas" ? null : Categoria;

        if (EsFarmacia)
        {
            // Solo las APROBADAS: una farmacia pendiente de aprobación no admite registro
            // (regla F22), y ofrecerla solo sirve para que el servidor la rechace después.
            var todas = await _base.FarmaciasAsync();
            FarmaciasPendientes.Clear();
            FarmaciasVisitadas.Clear();
            foreach (var f in todas.Where(f => f.SePuedeVisitar && (q.Length == 0 ||
                     f.Nombre.Contains(q, StringComparison.OrdinalIgnoreCase))).Take(60))
                (f.EsPendiente ? FarmaciasPendientes : FarmaciasVisitadas).Add(f);
            foreach (var n in new[] { nameof(HayFarmaciasPendientes), nameof(HayFarmaciasVisitadas),
                                      nameof(TituloFarmaciasPendientes), nameof(TituloFarmaciasVisitadas),
                                      nameof(TextoFarmaciasActivas) })
                OnPropertyChanged(n);
            return;
        }

        bool Coincide(ItemAgenda a) =>
            (q.Length == 0 || a.Nombre.Contains(q, StringComparison.OrdinalIgnoreCase))
            && (cat is null || string.Equals(a.Categoria, cat, StringComparison.OrdinalIgnoreCase));

        var agenda = await _base.AgendaAsync();
        DelDia.Clear();
        DelCiclo.Clear();
        foreach (var a in agenda.Where(Coincide))
            (a.Grupo == "dia" ? DelDia : DelCiclo).Add(a);

        // El panel MENOS lo que ya está en la agenda: los que quedan son los que se
        // pueden visitar sin estar programados (visita no programada).
        var enAgenda = agenda.Select(a => a.MedicoId).ToHashSet();
        var panel = await _base.MedicosAsync();
        Panel.Clear();
        foreach (var m in panel.Where(m => !enAgenda.Contains(m.Id) && m.SePuedeVisitar
                          && (q.Length == 0 || m.Nombre.Contains(q, StringComparison.OrdinalIgnoreCase))
                          && (cat is null || string.Equals(m.Categoria, cat, StringComparison.OrdinalIgnoreCase)))
                          .Take(60))
            Panel.Add(m);

        await MarcarEstadosAsync();

        foreach (var p in new[] { nameof(HayDelDia), nameof(HayDelCiclo), nameof(TituloDelDia),
                                  nameof(TituloDelCiclo), nameof(TextoPendientes) })
            OnPropertyChanged(p);
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

    /// <summary>
    /// Pide la ubicación en cuanto se abre la ficha, sin bloquear nada.
    ///
    /// El GPS de un edificio médico tarda; hacerlo aquí le da esos segundos mientras el
    /// visitador escribe, y para cuando guarda ya está. Si no llega, se vuelve a
    /// intentar al guardar y, si tampoco, la visita se registra igual: la coordenada es
    /// opcional en el servidor justo porque dentro de una consulta a menudo no fija.
    /// </summary>
    private async Task UbicarEnSegundoPlanoAsync()
    {
        var u = await UbicacionAsync();
        if (u is null) return;
        Latitud = u.Latitude;
        Longitud = u.Longitude;
    }

    [RelayCommand]
    private async Task CapturarUbicacionAsync()
    {
        var u = await UbicacionAsync();
        if (u is null) { Aviso = "No se pudo obtener la ubicación (permiso denegado o sin señal)."; return; }
        Latitud = u.Latitude;
        Longitud = u.Longitude;
    }

    // ── Guardar ──────────────────────────────────────────────────────────────

    private bool PuedeGuardar()
    {
        if (!PuedeCapturar) return false;
        if (EsFarmacia) return Farmacia?.SePuedeVisitar == true;
        if (Cita is null) return false;
        if (EsNoVisita) return !string.IsNullOrWhiteSpace(Causa);
        var c = (Comentario ?? "").Trim();
        return c.Length >= 10 && !GENERICOS.Contains(c);
    }

    [RelayCommand(CanExecute = nameof(PuedeGuardar))]
    private async Task GuardarAsync()
    {
        await EjecutarAsync(async () =>
        {
            // Si el visitador no pulsó «Capturar ubicación», se intenta igual al guardar:
            // la coordenada vale y pedirla explícitamente sería un paso más en la calle.
            if (Latitud is null)
            {
                var u = await UbicacionAsync();
                if (u is not null) { Latitud = u.Latitude; Longitud = u.Longitude; }
            }

            var envio = new EnvioPendiente
            {
                // La hora de captura es la que manda: `hace_minutos` se calcula al
                // ENVIAR, contra este momento, no ahora.
                CapturadoUtc = DateTime.UtcNow.AddMinutes(-MinutosAtras),
                Etiqueta = Elegido,
            };

            var elegidos = Productos.Where(p => p.Elegido).OrderBy(p => p.Mencion).ToList();

            if (EsFarmacia)
            {
                envio.Tipo = "farmacia";
                envio.PanelId = Farmacia!.Id;
                envio.Cuerpo = JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["comentario"] = string.IsNullOrWhiteSpace(Comentario) ? null : Comentario.Trim(),
                    ["ejecutada"] = !EsNoVisita,
                    ["causa_no_visita"] = EsNoVisita ? Causa : null,
                    ["latitud"] = Latitud,
                    ["longitud"] = Longitud,
                });
            }
            else if (EsNoVisita)
            {
                envio.Tipo = "no-visita";
                envio.Cuerpo = JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["medico_id"] = Cita!.MedicoId,
                    ["causa"] = Causa,
                    ["comentario"] = string.IsNullOrWhiteSpace(Comentario) ? null : Comentario.Trim(),
                });
            }
            else
            {
                envio.Tipo = "visita";
                envio.Cuerpo = JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["medico_id"] = Cita!.MedicoId,
                    ["tipo_visita"] = TipoVisita,
                    ["comentario"] = Comentario.Trim(),
                    ["acompanado"] = Acompanado,
                    ["latitud"] = Latitud,
                    ["longitud"] = Longitud,
                    // Producto + número de mención, con el CÓDIGO del producto: es con lo
                    // que el servidor cruza el registro contra la parrilla.
                    ["productos"] = elegidos
                        .Select(p => new { producto = Codigo(p), mencion = p.Mencion })
                        .ToList(),
                });
            }

            await _sync.EncolarAsync(envio);

            // Las muestras van en su PROPIO envío, como en la suite: el servidor las
            // registra por médico, no dentro de la visita.
            var entregas = elegidos.Where(p => p.Muestras > 0)
                .Select(p => new { producto = Codigo(p), cantidad = p.Muestras }).ToList();
            if (!EsFarmacia && !EsNoVisita && entregas.Count > 0)
            {
                await _sync.EncolarAsync(new EnvioPendiente
                {
                    Tipo = "muestras",
                    Etiqueta = $"Muestras · {Elegido}",
                    CapturadoUtc = envio.CapturadoUtc,
                    Cuerpo = JsonSerializer.Serialize(new Dictionary<string, object?>
                    {
                        ["medico_id"] = Cita!.MedicoId,
                        ["entregas"] = entregas,
                    }),
                });
            }

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
            await CargarFeedAsync();
        });
    }

    /// <summary>El código del producto; si el catálogo es viejo y no lo trae, el nombre.</summary>
    private static string Codigo(ProductoParrilla p) =>
        string.IsNullOrWhiteSpace(p.Codigo) ? p.Nombre : p.Codigo;

    /// <summary>Lo capturado para ESTA visita: se borra al cambiar de destinatario.</summary>
    private void LimpiarCaptura()
    {
        Comentario = "";
        Acompanado = false; EsNoVisita = false; Causa = null;
        RutaFoto = null; Latitud = null; Longitud = null;
        foreach (var p in Productos) p.Reiniciar();
        RefrescarResumen();
    }

    private void Limpiar()
    {
        Cita = null; Farmacia = null; FueraDeAgenda = null; Busqueda = "";
        TipoVisita = "V";
        HoraReal = DateTime.Now.TimeOfDay;
        LimpiarCaptura();
        _ = FiltrarAsync();
    }

    /// <summary>
    /// Abrir la ficha de una cita. Vuelve a pulsarse y se cierra: en una pantalla de
    /// teléfono, con la ficha abierta ocupando el alto entero, cerrarla es la única forma
    /// de volver a ver la lista.
    /// </summary>
    [RelayCommand]
    private void SeleccionarCita(ItemAgenda? item)
    {
        if (item is null) return;
        if (item.Registrada)
        {
            // Ni se abre: el servidor la rechazaría por duplicada, y abrir un formulario
            // que no puede guardar solo sirve para que alguien escriba y lo pierda.
            Aviso = $"{item.Nombre} ya está registrada en este ciclo.";
            return;
        }
        if (item.PorEnviar || item.EnServidorHoy)
        {
            // Registrarlo otra vez duplicaría la visita de hoy.
            Aviso = item.PorEnviar
                ? $"{item.Nombre} ya está guardada en tu teléfono y se enviará sola."
                : $"{item.Nombre} ya la registraste hoy.";
            return;
        }
        Cita = ReferenceEquals(Cita, item) ? null : item;
    }

    [RelayCommand]
    private void SeleccionarFarmacia(FarmaciaPanel? item)
    {
        if (item is null) return;
        Farmacia = ReferenceEquals(Farmacia, item) ? null : item;
    }

    [RelayCommand] private void ElegirVista() => TipoVisita = "V";
    [RelayCommand] private void ElegirRevisita() => TipoVisita = "R";
    [RelayCommand] private void ElegirMedico() => EsFarmacia = false;
    [RelayCommand] private void ElegirFarmacia() => EsFarmacia = true;
}
