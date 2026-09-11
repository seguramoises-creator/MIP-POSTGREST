using System.Collections.ObjectModel;
using System.Text.Json;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Datos;
using VistaCampo.Modelos;
using VistaCampo.Servicios;

namespace VistaCampo.VistaModelos;

/// <summary>
/// La pantalla que el visitador mira entre visita y visita: qué lleva hoy, qué le falta
/// de la agenda y si su trabajo ya subió.
/// </summary>
/// <summary>Una fila de Hoy: médico o farmacia, con su marca (✓ visitado hoy, ⊘ no visitado).</summary>
public class FilaHoy
{
    public string Icono { get; init; } = "🩺";
    public string Nombre { get; init; } = "";
    public string Detalle { get; init; } = "";
    public string Marca { get; init; } = "";
    public bool NoVisitado { get; init; }
}

public partial class HoyVista : BaseVista
{
    private readonly ApiCliente _api;
    private readonly BaseLocal _base;
    private readonly ServicioSincronizacion _sync;
    private readonly ServicioInstalacion _instalacion;

    public HoyVista(ApiCliente api, BaseLocal baseLocal, ServicioSincronizacion sync,
                    ServicioInstalacion instalacion)
    {
        _api = api;
        _base = baseLocal;
        _sync = sync;
        _instalacion = instalacion;
        // A propósito NO se suscribe al evento de la cola: esta pantalla se construye
        // cada vez que se abre la pestaña, y una suscripción por instancia se acumula
        // sin que nadie la quite — el contador acabaría refrescándose una vez por cada
        // vez que el visitador entró a Hoy en toda la jornada. El estado se lee al
        // aparecer, que es cuando importa.
    }

    [ObservableProperty] private int _vistas;
    [ObservableProperty] private int _revisitas;
    [ObservableProperty] private int _farmacias;
    [ObservableProperty] private int _acompanadas;

    /// <summary>
    /// ¿Se pudo consultar el día? Mientras no, las cifras se muestran como «—».
    ///
    /// Medido en el teléfono: sin conexión la pantalla decía «Vistas 0 · Revisitas 0»
    /// con toda seguridad, y el aviso de «sin conexión» quedaba al final, fuera de la
    /// pantalla. El visitador que ha hecho seis visitas leía que no había hecho ninguna.
    /// Un cero AFIRMA; una ausencia no, y hay que distinguirlas.
    /// </summary>
    [ObservableProperty] private bool _hayDatosDelDia;

    public string TextoVistas => HayDatosDelDia ? Vistas.ToString() : "—";
    public string TextoRevisitas => HayDatosDelDia ? Revisitas.ToString() : "—";
    public string TextoFarmacias => HayDatosDelDia ? Farmacias.ToString() : "—";
    public string TextoAcompanadas => HayDatosDelDia ? Acompanadas.ToString() : "—";

    partial void OnHayDatosDelDiaChanged(bool value) => RefrescarCifras();
    partial void OnVistasChanged(int value) => RefrescarCifras();
    partial void OnRevisitasChanged(int value) => RefrescarCifras();
    partial void OnFarmaciasChanged(int value) => RefrescarCifras();
    partial void OnAcompanadasChanged(int value) => RefrescarCifras();

    private void RefrescarCifras()
    {
        foreach (var p in new[] { nameof(TextoVistas), nameof(TextoRevisitas),
                                  nameof(TextoFarmacias), nameof(TextoAcompanadas) })
            OnPropertyChanged(p);
    }
    [ObservableProperty] private string _estadoCola = "Al día";
    [ObservableProperty] private bool _hayPendientes;
    [ObservableProperty] private bool _hayRechazados;
    [ObservableProperty] private bool _sinCatalogos;

    public ObservableCollection<VisitaDelDia> Registradas { get; } = new();

    /// <summary>
    /// Lo PROGRAMADO PARA HOY (semana del ciclo + día del plan), con ✓ si se visitó HOY.
    ///
    /// Antes esta lista era la agenda del ciclo entero y su ✓ significaba «completado en el
    /// ciclo»: la pantalla enseñaba tres ✓ con «Vistas 1» arriba, y lo visitado fuera de la
    /// agenda no aparecía en ninguna parte.
    /// </summary>
    public ObservableCollection<FilaHoy> AgendaHoy { get; } = new();

    /// <summary>Registrado hoy SIN estar programado para hoy: otro día, fuera del plan, farmacias.</summary>
    public ObservableCollection<FilaHoy> FueraDeAgenda { get; } = new();

    [ObservableProperty] private string _tituloAgenda = "📋  Tu agenda de hoy";
    [ObservableProperty] private string _tituloFuera = "➕  Fuera de tu agenda de hoy";
    public bool SinAgendaHoy => AgendaHoy.Count == 0;
    public bool SinFuera => FueraDeAgenda.Count == 0;
    public string TextoFueraVacio => HayDatosDelDia
        ? "Nada fuera de tu agenda hoy."
        : "Sin conexión: no se sabe qué se registró hoy fuera de la agenda.";

    private async Task<List<(int id, string nombre, string tipo, string? hora, bool visitada)>> ProgramadosHoyAsync()
    {
        // LA MISMA fuente que el grupo «del día» de Registrar (el servidor lo decide por
        // semana del ciclo + día). Cuando cada pantalla lo calculaba a su manera, Registrar
        // decía cinco médicos del día y Hoy uno.
        return (await _base.AgendaAsync()).Where(a => a.Grupo == "dia")
            .OrderBy(a => a.HoraEstimada ?? "99").ThenBy(a => a.Nombre)
            .Select(a => (a.MedicoId, a.Nombre, a.TipoVisita, a.HoraEstimada, a.VisitadaHoy)).ToList();
    }

    /// <summary>`visitasHoy` null = no se pudo consultar el día: la agenda va sin marcas.</summary>
    private async Task ConstruirListasAsync(List<VisitaDelDia>? visitasHoy, List<string>? farmaciasHoy)
    {
        var prog = await ProgramadosHoyAsync();
        AgendaHoy.Clear();
        FueraDeAgenda.Clear();
        var idsProgramados = prog.Select(p => p.id).ToHashSet();
        var cola = await PorEnviarAsync();
        foreach (var p in prog)
        {
            var suyas = visitasHoy?.Where(v => v.MedicoId == p.id).ToList();
            var hecha = suyas?.FirstOrDefault(v => v.Ejecutada);
            var noVisitado = suyas is { Count: > 0 } && hecha is null;
            var enCola = cola.FirstOrDefault(c => c.medicoId == p.id).etiqueta is not null;
            // Sin conexión no se puede preguntar el día, pero la agenda de la última
            // sincronización ya decía si estaba visitado: «0 de 1» con la visita hecha era falso.
            var segunAgenda = visitasHoy is null && p.visitada;
            var partes = new[] { p.tipo == "R" ? "Revisita" : "Vista", p.hora }
                .Where(s => !string.IsNullOrWhiteSpace(s));
            AgendaHoy.Add(new FilaHoy
            {
                Nombre = p.nombre,
                Detalle = string.Join(" · ", partes)
                    + (hecha is not null ? $" · hecha a las {hecha.HoraCorta} · ☁️ en el servidor"
                       : enCola ? " · 📱 guardada, por enviar"
                       : segunAgenda ? " · ☁️ en el servidor (según la última sincronización)" : ""),
                Marca = hecha is not null || segunAgenda ? "✓" : enCola ? "📱" : noVisitado ? "⊘" : "",
                NoVisitado = noVisitado && !enCola,
            });
        }
        foreach (var v in visitasHoy?.Where(v => !idsProgramados.Contains(v.MedicoId)) ?? [])
            FueraDeAgenda.Add(new FilaHoy
            {
                Nombre = v.Medico, Detalle = $"{v.Subtitulo} · ☁️ en el servidor",
                Marca = v.Ejecutada ? "✓" : "⊘", NoVisitado = !v.Ejecutada,
            });
        foreach (var f in farmaciasHoy ?? [])
            FueraDeAgenda.Add(new FilaHoy { Icono = "🏥", Nombre = f, Detalle = "Farmacia · ☁️ en el servidor", Marca = "✓" });
        // Lo capturado que aún no subió también se ve, y dicho: guardado en el teléfono.
        foreach (var c in cola.Where(c => c.medicoId == 0 || !idsProgramados.Contains(c.medicoId)))
            FueraDeAgenda.Add(new FilaHoy
            {
                Icono = c.tipo == "farmacia" ? "🏥" : "🩺",
                Nombre = c.etiqueta!,
                Detalle = (c.tipo == "farmacia" ? "Farmacia" : c.tipo == "no-visita" ? "No visitado" : "Visita")
                          + " · 📱 guardada en el teléfono, por enviar",
                Marca = "📱",
            });

        TituloAgenda = $"📋  Tu agenda de hoy · {AgendaHoy.Count(a => a.Marca == "✓")} de {AgendaHoy.Count} visitados";
        TituloFuera = $"➕  Fuera de tu agenda de hoy · {FueraDeAgenda.Count}";
        OnPropertyChanged(nameof(SinAgendaHoy));
        OnPropertyChanged(nameof(SinFuera));
        OnPropertyChanged(nameof(TextoFueraVacio));
    }

    public bool PuedeCapturar => _instalacion.Config.PuedeCapturar;

    /// <summary>El ciclo que se está trabajando, para la tarjeta de arriba.</summary>
    public InfoCiclo Ciclo => InfoCiclo.Leer();

    /// <summary>Qué pasa con lo capturado: subido, guardado en el teléfono o rechazado.</summary>
    [ObservableProperty] private string _detalleCola = "";

    /// <summary>
    /// Solo el gesto de deslizar para refrescar. Va separado de `Ocupado` a propósito: con el
    /// RefreshView atado a `Ocupado`, cada carga lo ponía en true y el RefreshView relanzaba
    /// el comando — la carga se volvía a disparar a sí misma.
    /// </summary>
    [ObservableProperty] private bool _refrescando;
    private bool _recargarAlTerminar;

    [RelayCommand]
    private async Task RefrescarAsync()
    {
        try { await CargarAsync(); }
        finally { Refrescando = false; }
    }

    private static string UltimoEnvio()
    {
        var crudo = Preferences.Get("ultimo_envio_ok", "");
        if (!DateTime.TryParse(crudo, null, System.Globalization.DateTimeStyles.RoundtripKind, out var t))
            return "Nada guardado en el teléfono sin enviar.";
        var l = t.ToLocalTime();
        return l.Date == DateTime.Today
            ? $"Última sincronización: hoy a las {l:HH:mm}"
            : $"Última sincronización: el {l:dd/MM} a las {l:HH:mm}";
    }

    /// <summary>Capturas que siguen en el teléfono (pendientes o rechazadas), con su médico.</summary>
    private async Task<List<(int medicoId, string? etiqueta, string tipo)>> PorEnviarAsync()
    {
        var l = new List<(int, string?, string)>();
        foreach (var e in await _base.ColaAsync())
        {
            if (e.Estado == (int)EstadoEnvio.Enviado || e.Tipo is not ("visita" or "no-visita" or "farmacia"))
                continue;
            var id = 0;
            if (e.Tipo != "farmacia")
                try
                {
                    using var d = JsonDocument.Parse(e.Cuerpo);
                    id = ServicioSincronizacion.Entero(d.RootElement, "medico_id");
                }
                catch (JsonException) { }
            l.Add((id, string.IsNullOrWhiteSpace(e.Etiqueta) ? "(sin nombre)" : e.Etiqueta, e.Tipo));
        }
        return l;
    }

    /// <summary>
    /// Lo que se dice cuando la instalación no captura. Se explica en vez de esconder:
    /// un visitador que no ve el botón de registrar necesita saber por qué.
    /// </summary>
    public string AvisoSoloConsulta =>
        "Esta instalación no registra visitas desde la app: llegan del sistema de tu "
        + "compañía y aquí solo se consultan.";

    /// <summary>
    /// Escucha los cambios de la cola mientras la pantalla está a la vista.
    ///
    /// Hace falta porque `OnAppearing` NO se dispara al volver de segundo plano: Shell
    /// mantiene la pestaña «aparecida». Medido en el teléfono: con el servidor caído se
    /// capturó una visita, se levantó el servidor y al volver a la app la cola SÍ se
    /// vació sola (la visita entró a la base con id 934), pero la pantalla seguía
    /// diciendo «1 por enviar» y mostrando el error de conexión anterior. El trabajo
    /// había subido y el visitador leía lo contrario.
    ///
    /// Se suscribe aquí y no en el constructor a propósito: esta vista se construye cada
    /// vez que se abre la pestaña, y una suscripción por instancia se acumularía toda la
    /// jornada. Emparejado con <see cref="Desactivar"/>, hay como mucho una viva.
    /// </summary>
    public void Activar()
    {
        _sync.Cambio -= AlCambiarLaCola;
        _sync.Cambio += AlCambiarLaCola;
        Connectivity.Current.ConnectivityChanged -= AlCambiarLaRed;
        Connectivity.Current.ConnectivityChanged += AlCambiarLaRed;
    }

    public void Desactivar()
    {
        _sync.Cambio -= AlCambiarLaCola;
        Connectivity.Current.ConnectivityChanged -= AlCambiarLaRed;
    }

    /// <summary>
    /// Al volver la señal, «Sin conexión» deja de ser verdad: se vuelve a consultar el día.
    /// Unos segundos de espera porque Android avisa de la red antes de que resuelva nombres.
    /// </summary>
    private void AlCambiarLaRed(object? sender, ConnectivityChangedEventArgs e) =>
        MainThread.BeginInvokeOnMainThread(async () =>
        {
            if (e.NetworkAccess == NetworkAccess.Internet) await Task.Delay(3000);
            await CargarAsync();
        });

    private void AlCambiarLaCola() => MainThread.BeginInvokeOnMainThread(async () =>
    {
        var habia = HayPendientes;
        RefrescarEstadoCola();
        // Si la cola cambió (se guardó algo, o subió), las listas ya no dicen la verdad: la
        // tarjeta no puede decir «Todo en el servidor» con una fila «📱 por enviar» debajo.
        if (habia != HayPendientes) await CargarAsync();
    });

    private void RefrescarEstadoCola()
    {
        // Si la cola se paró por algo que NO es el dato del visitador (sesión vencida,
        // servidor caído), tiene que decirlo aquí: si no, la pantalla enseña «N por
        // enviar» sin explicar por qué no bajan, que se lee como que la app no hace nada.
        if (!string.IsNullOrWhiteSpace(_sync.Aviso)) Aviso = _sync.Aviso;
        HayPendientes = _sync.Pendientes > 0;
        HayRechazados = _sync.Rechazados > 0;
        EstadoCola = _sync.Rechazados > 0
            ? $"⚠️ {_sync.Rechazados} sin subir — revisar"
            : _sync.Pendientes > 0 ? $"📱 {_sync.Pendientes} por enviar" : "☁️ Todo en el servidor";
        DetalleCola = _sync.Rechazados > 0
            ? "El servidor no los aceptó: el motivo está en Perfil › Tu cola de envío."
            : _sync.Pendientes > 0
                ? "Guardado en el teléfono: sube solo cuando hay señal, o toca Sincronizar."
                : UltimoEnvio();
    }

    [RelayCommand]
    public async Task CargarAsync()
    {
        // Ya hay una carga en curso: no se pisa, pero TAMPOCO se pierde — se vuelve a cargar
        // al terminar. Descartarla dejaba la pantalla vieja: al volver la señal la cola se
        // vaciaba sola, la tarjeta decía «Todo en el servidor» y la lista seguía con
        // «📱 por enviar» y «Sin conexión» (medido en el teléfono, modo avión).
        if (Ocupado) { _recargarAlTerminar = true; return; }
        OnPropertyChanged(nameof(PuedeCapturar));
        OnPropertyChanged(nameof(Ciclo));
        await _sync.RefrescarContadoresAsync();
        RefrescarEstadoCola();
        SinCatalogos = !await _base.HayCatalogosAsync();


        if (!ServicioSincronizacion.HayRed)
        {
            // Sin red no se pisa lo que ya se mostró con ceros traídos de la nada: se
            // dice que no hay conexión. Un cero afirma; una ausencia no.
            HayDatosDelDia = false;
            Aviso = "Sin conexión: no se pudo consultar tu día. Lo que registres se guarda igual.";
            await ConstruirListasAsync(null, null);   // agenda local + lo que está en la cola
            return;
        }
        // Se limpia lo que puso la carga ANTERIOR, pero NUNCA el aviso de la cola: es el
        // que dice por qué no sube nada (sesión vencida, servidor mal). Borrarlo aquí lo
        // hacía invisible — se ponía y se quitaba en la misma pasada, y la pantalla se
        // quedaba con «1 por enviar» y las cifras en «—» sin decir de qué se trataba.
        if (string.IsNullOrWhiteSpace(_sync.Aviso)) Aviso = null;

        await EjecutarAsync(async () =>
        {
            var hoy = await _api.ObtenerAsync<List<JsonElement>>("/visita/mis-visitas-hoy");
            Registradas.Clear();
            Vistas = Revisitas = Acompanadas = 0;
            foreach (var v in hoy)
            {
                // El feed manda `tipo_visita`, no `tipo`. Leerlo mal no dio ningún error:
                // el `?? "V"` convertía TODAS las revisitas en vistas, y la pantalla
                // enseñaba «Vistas 9 · Revisitas 0» con tres revisitas en la base. Un
                // nombre de campo equivocado no se ve como un fallo: se ve como un dato.
                var tipo = ServicioSincronizacion.Texto(v, "tipo_visita") ?? "V";
                var ejecutada = !v.TryGetProperty("ejecutada", out var e) || e.ValueKind != JsonValueKind.False;
                if (ejecutada)
                {
                    if (tipo == "R") Revisitas++; else Vistas++;
                }
                if (v.TryGetProperty("acompanado", out var ac) && ac.ValueKind == JsonValueKind.True)
                    Acompanadas++;
                Registradas.Add(new VisitaDelDia
                {
                    Id = ServicioSincronizacion.Entero(v, "id"),
                    MedicoId = ServicioSincronizacion.Entero(v, "medico_id"),
                    Medico = ServicioSincronizacion.Texto(v, "medico") ?? "(sin nombre)",
                    Tipo = tipo,
                    Hora = (ServicioSincronizacion.Texto(v, "hora") ?? "").Replace('T', ' '),
                    Ejecutada = ejecutada,
                });
            }
            // Las farmacias van por su propio camino: no salen del feed de médicos.
            // La tarjeta existía desde el principio y NADIE la alimentaba, así que
            // enseñaba «0» todos los días, con visitas a farmacia registradas y todo.
            // Un contador que nunca se escribe no se ve vacío: se ve como un cero.
            // El ciclo que se trabaja se pide aquí también: si solo se leyera lo guardado,
            // Hoy no lo diría hasta abrir Plan o sincronizar (medido tras instalar la app).
            try
            {
                ServicioSincronizacion.GuardarCiclo(await _api.ObtenerAsync<JsonElement>("/visita/planeacion/estado"));
                OnPropertyChanged(nameof(Ciclo));
            }
            catch (ErrorApi) { /* informativo: no tumba la carga del día */ }

            var farmacias = await _api.ObtenerAsync<List<JsonElement>>("/farmacias/panel");
            var farmaciasHoy = farmacias
                .Where(f => f.TryGetProperty("visitada_hoy", out var h) && h.ValueKind == JsonValueKind.True)
                .Select(f => ServicioSincronizacion.Texto(f, "nombre_completo")
                             ?? ServicioSincronizacion.Texto(f, "nombre") ?? "Farmacia")
                .ToList();
            Farmacias = farmaciasHoy.Count;
            HayDatosDelDia = true;
            await ConstruirListasAsync(Registradas.ToList(), farmaciasHoy);

            // Solo aquí: las consultas llegaron y respondieron. Si fallan, `EjecutarAsync`
            // pone el error y las cifras se quedan en «—» — nunca en un cero inventado.
            HayDatosDelDia = true;
        });
        // Si la consulta falló, al menos la agenda local y lo que está en la cola.
        if (Error is not null) await ConstruirListasAsync(null, null);
        if (_recargarAlTerminar)
        {
            _recargarAlTerminar = false;
            await CargarAsync();
        }
    }

    [RelayCommand]
    private async Task SincronizarAsync()
    {
        string? fallo = null;
        await EjecutarAsync(async () =>
        {
            await _sync.ProcesarAsync();
            fallo = await _sync.DescargarCatalogosAsync();
        });
        // Fuera de EjecutarAsync: CargarAsync no entra mientras la pantalla está ocupada.
        await CargarAsync();
        if (fallo is not null) Aviso = fallo;
    }
}
