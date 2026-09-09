using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Datos;
using VistaCampo.Modelos;
using VistaCampo.Servicios;

namespace VistaCampo.VistaModelos;

/// <summary>Quién soy, qué me falta por subir, y la salida.</summary>
public partial class PerfilVista : BaseVista
{
    private readonly Sesion _sesion;
    private readonly BaseLocal _base;
    private readonly ServicioSincronizacion _sync;
    private readonly ServicioInstalacion _instalacion;

    public PerfilVista(Sesion sesion, BaseLocal baseLocal, ServicioSincronizacion sync,
                       ServicioInstalacion instalacion)
    {
        _sesion = sesion;
        _base = baseLocal;
        _sync = sync;
        _instalacion = instalacion;
    }

    public ObservableCollection<EnvioPendiente> Cola { get; } = new();

    public string Nombre => _sesion.NombreCompleto ?? _sesion.Usuario ?? "—";
    public string Usuario => _sesion.Usuario ?? "—";
    public string Rol => _sesion.Rol ?? "—";
    public string Servidor => _sesion.UrlServidor;
    public string Identidad => _instalacion.NombreIdentidad;
    public string Modo => _instalacion.Config.PuedeCapturar ? "Captura habilitada" : "Solo consulta";

    public string UltimaSync
    {
        get
        {
            var crudo = Preferences.Get("ultima_sync", "");
            return DateTime.TryParse(crudo, out var t)
                ? t.ToLocalTime().ToString("dd/MM/yyyy HH:mm")
                : "Nunca";
        }
    }

    [RelayCommand]
    public async Task CargarAsync()
    {
        foreach (var p in new[] { nameof(Nombre), nameof(Usuario), nameof(Rol), nameof(Servidor),
                                  nameof(Identidad), nameof(Modo), nameof(UltimaSync) })
            OnPropertyChanged(p);

        Cola.Clear();
        foreach (var e in await _base.ColaAsync()) Cola.Add(e);
        await _sync.RefrescarContadoresAsync();
    }

    [RelayCommand]
    private async Task ReintentarAsync()
    {
        await EjecutarAsync(async () =>
        {
            if (!ServicioSincronizacion.HayRed)
            {
                Aviso = "Sigue sin haber conexión.";
                return;
            }
            // Un rechazado vuelve a pendiente al reintentar a mano: puede haber sido un
            // problema pasajero (el gerente acaba de aprobar al médico, el ciclo se
            // reabrió). Lo que no se hace nunca es borrarlo por su cuenta.
            foreach (var e in await _base.ColaAsync())
            {
                if (e.Estado != (int)EstadoEnvio.Rechazado) continue;
                e.Estado = (int)EstadoEnvio.Pendiente;
                e.Motivo = null;
                await _base.ActualizarAsync(e);
            }
            await _sync.ProcesarAsync();
            await CargarAsync();
        });
    }

    [RelayCommand]
    private async Task DescargarCatalogosAsync()
    {
        await EjecutarAsync(async () =>
        {
            var fallo = await _sync.DescargarCatalogosAsync();
            Aviso = fallo ?? "Catálogos actualizados.";
            await CargarAsync();
        });
    }

    [RelayCommand]
    private async Task SalirAsync()
    {
        // La cola NO se borra al salir: son capturas del visitador, no de la sesión. Si
        // vuelve a entrar —y va a volver— su trabajo tiene que seguir ahí.
        await _sesion.CerrarAsync();
        await Shell.Current.GoToAsync("//entrar");
    }
}
