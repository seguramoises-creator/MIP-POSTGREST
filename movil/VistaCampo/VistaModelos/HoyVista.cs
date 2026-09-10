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

    public ObservableCollection<ItemAgenda> Agenda { get; } = new();
    public ObservableCollection<VisitaDelDia> Registradas { get; } = new();

    public bool PuedeCapturar => _instalacion.Config.PuedeCapturar;

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
        await _sync.RefrescarContadoresAsync();
        RefrescarEstadoCola();
        SinCatalogos = !await _base.HayCatalogosAsync();

        Agenda.Clear();
        foreach (var a in await _base.AgendaAsync()) Agenda.Add(a);

        if (!ServicioSincronizacion.HayRed)
        {
            // Sin red no se pisa lo que ya se mostró con ceros traídos de la nada: se
            // dice que no hay conexión. Un cero afirma; una ausencia no.
            HayDatosDelDia = false;
            Aviso = "Sin conexión: no se pudo consultar tu día. Lo que registres se guarda igual.";
            return;
        }
        Aviso = null;

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
            var farmacias = await _api.ObtenerAsync<List<JsonElement>>("/farmacias/panel");
            Farmacias = farmacias.Count(f => f.TryGetProperty("visitada_hoy", out var h)
                                             && h.ValueKind == JsonValueKind.True);

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
