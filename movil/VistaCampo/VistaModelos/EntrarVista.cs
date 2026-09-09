using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Servicios;

namespace VistaCampo.VistaModelos;

public partial class EntrarVista : BaseVista
{
    private readonly ApiCliente _api;
    private readonly Sesion _sesion;
    private readonly ServicioInstalacion _instalacion;
    private readonly ServicioSincronizacion _sync;

    public EntrarVista(ApiCliente api, Sesion sesion, ServicioInstalacion instalacion, ServicioSincronizacion sync)
    {
        _api = api;
        _sesion = sesion;
        _instalacion = instalacion;
        _sync = sync;
        _servidor = sesion.UrlServidor;
    }

    [ObservableProperty] private string _usuario = "";
    [ObservableProperty] private string _clave = "";
    [ObservableProperty] private string _servidor;
    [ObservableProperty] private bool _mostrarClave;
    [ObservableProperty] private bool _mostrarServidor;

    public string Bienvenida => $"Bienvenido a {_instalacion.NombreIdentidad}";

    public void RefrescarIdentidad() => OnPropertyChanged(nameof(Bienvenida));

    [RelayCommand]
    private void AlternarClave() => MostrarClave = !MostrarClave;

    [RelayCommand]
    private void AlternarServidor() => MostrarServidor = !MostrarServidor;

    [RelayCommand]
    private async Task EntrarAsync()
    {
        if (string.IsNullOrWhiteSpace(Usuario) || string.IsNullOrEmpty(Clave))
        {
            Error = "Escribe tu usuario y tu contraseña.";
            return;
        }

        await EjecutarAsync(async () =>
        {
            _sesion.UrlServidor = Servidor.Trim();
            // Se recorta el usuario: en el móvil es fácil que entre un espacio al final
            // del autocompletado, y el servidor lo tomaría como parte del nombre.
            var (acceso, refresco, debeCambiar) = await _api.EntrarAsync(Usuario.Trim(), Clave);
            await _sesion.GuardarTokensAsync(acceso, refresco);
            await _instalacion.CargarAsync();

            if (debeCambiar)
            {
                // No se deja pasar: la web obliga a cambiarla y aquí también, o el
                // visitador quedaría con una clave que el sistema ya dio por vencida.
                Error = "Debes cambiar tu contraseña antes de entrar. Hazlo desde la web.";
                await _sesion.CerrarAsync();
                return;
            }

            var fallo = await _sync.DescargarCatalogosAsync();
            if (fallo is not null)
                Aviso = "Entraste, pero no se pudieron descargar los catálogos: " + fallo;

            if (Shell.Current is not null) await Shell.Current.GoToAsync("//hoy");
        });
    }
}
