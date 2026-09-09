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
            Aviso = "Sin conexión. Se muestra lo último descargado.";
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
                var tipo = ServicioSincronizacion.Texto(v, "tipo") ?? "V";
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
