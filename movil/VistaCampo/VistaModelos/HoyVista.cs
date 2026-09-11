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

    private static readonly string[] DiasSemana =
        { "Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado" };

    private async Task<List<(int id, string nombre, string tipo, string? hora)>> ProgramadosHoyAsync()
    {
        var semana = Preferences.Get("ciclo_semana", 0);
        var hoy = DiasSemana[(int)DateTime.Now.DayOfWeek];
        if (semana > 0)
            return (await _base.PlanAsync())
                .Where(p => p.Semana == semana && p.Dia == hoy)
                .OrderBy(p => p.Hora ?? "99").ThenBy(p => p.Medico)
                .Select(p => (p.MedicoId, p.Medico, p.TipoVisita, p.Hora)).ToList();
        // Sin saber la semana del ciclo, lo que el servidor marcó para hoy.
        return (await _base.AgendaAsync()).Where(a => a.Grupo == "dia")
            .Select(a => (a.MedicoId, a.Nombre, a.TipoVisita, a.HoraEstimada)).ToList();
    }

    /// <summary>`visitasHoy` null = no se pudo consultar el día: la agenda va sin marcas.</summary>
    private async Task ConstruirListasAsync(List<VisitaDelDia>? visitasHoy, List<string>? farmaciasHoy)
    {
        var prog = await ProgramadosHoyAsync();
        AgendaHoy.Clear();
        FueraDeAgenda.Clear();
        var idsProgramados = prog.Select(p => p.id).ToHashSet();
        foreach (var p in prog)
        {
            var suyas = visitasHoy?.Where(v => v.MedicoId == p.id).ToList();
            var hecha = suyas?.FirstOrDefault(v => v.Ejecutada);
            var noVisitado = suyas is { Count: > 0 } && hecha is null;
            var partes = new[] { p.tipo == "R" ? "Revisita" : "Vista", p.hora }
                .Where(s => !string.IsNullOrWhiteSpace(s));
            AgendaHoy.Add(new FilaHoy
            {
                Nombre = p.nombre,
                Detalle = string.Join(" · ", partes) + (hecha is null ? "" : $" · hecha a las {hecha.HoraCorta}"),
                Marca = hecha is not null ? "✓" : noVisitado ? "⊘" : "",
                NoVisitado = noVisitado,
            });
        }
        foreach (var v in visitasHoy?.Where(v => !idsProgramados.Contains(v.MedicoId)) ?? [])
            FueraDeAgenda.Add(new FilaHoy
            {
                Nombre = v.Medico, Detalle = v.Subtitulo,
                Marca = v.Ejecutada ? "✓" : "⊘", NoVisitado = !v.Ejecutada,
            });
        foreach (var f in farmaciasHoy ?? [])
            FueraDeAgenda.Add(new FilaHoy { Icono = "🏥", Nombre = f, Detalle = "Farmacia visitada hoy", Marca = "✓" });

        TituloAgenda = $"📋  Tu agenda de hoy · {AgendaHoy.Count(a => a.Marca == "✓")} de {AgendaHoy.Count} visitados";
        TituloFuera = $"➕  Fuera de tu agenda de hoy · {FueraDeAgenda.Count}";
        OnPropertyChanged(nameof(SinAgendaHoy));
        OnPropertyChanged(nameof(SinFuera));
        OnPropertyChanged(nameof(TextoFueraVacio));
    }

    public bool PuedeCapturar => _instalacion.Config.PuedeCapturar;

    /// <summary>El ciclo que se está trabajando (se guarda al descargar catálogos o abrir Plan).</summary>
    public string CicloTexto => Preferences.Get("ciclo_texto", "");
    public bool HayCiclo => !string.IsNullOrEmpty(CicloTexto);

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
    }

    public void Desactivar() => _sync.Cambio -= AlCambiarLaCola;

    private void AlCambiarLaCola() => MainThread.BeginInvokeOnMainThread(async () =>
    {
        var habia = HayPendientes;
        RefrescarEstadoCola();
        // Si la cola acababa de vaciarse, el día cambió y el error de conexión que se
        // mostraba ya no es cierto: se vuelve a consultar en vez de dejar el cartel viejo.
        if (habia && !HayPendientes) await CargarAsync();
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
            ? $"{_sync.Rechazados} sin subir — revisar"
            : _sync.Pendientes > 0 ? $"{_sync.Pendientes} por enviar" : "Al día";
    }

    [RelayCommand]
    public async Task CargarAsync()
    {
        OnPropertyChanged(nameof(PuedeCapturar));
        OnPropertyChanged(nameof(CicloTexto));
        OnPropertyChanged(nameof(HayCiclo));
        await _sync.RefrescarContadoresAsync();
        RefrescarEstadoCola();
        SinCatalogos = !await _base.HayCatalogosAsync();

        // Primero lo local (sirve sin red); si hay conexión se rehace con lo visitado hoy.
        await ConstruirListasAsync(null, null);

        if (!ServicioSincronizacion.HayRed)
        {
            // Sin red no se pisa lo que ya se mostró con ceros traídos de la nada: se
            // dice que no hay conexión. Un cero afirma; una ausencia no.
            HayDatosDelDia = false;
            Aviso = "Sin conexión: no se pudo consultar tu día. Lo que registres se guarda igual.";
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
                OnPropertyChanged(nameof(CicloTexto));
                OnPropertyChanged(nameof(HayCiclo));
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
    }

    [RelayCommand]
    private async Task SincronizarAsync()
    {
        await EjecutarAsync(async () =>
        {
            await _sync.ProcesarAsync();
            var fallo = await _sync.DescargarCatalogosAsync();
            if (fallo is not null) Aviso = fallo;
            await CargarAsync();
        });
    }
}
