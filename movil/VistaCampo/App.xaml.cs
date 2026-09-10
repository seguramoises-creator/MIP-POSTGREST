using VistaCampo.Servicios;

namespace VistaCampo;

public partial class App : Application
{
    private readonly Sesion _sesion;
    private readonly ServicioInstalacion _instalacion;
    private readonly ServicioSincronizacion _sync;

    public App(Sesion sesion, ServicioInstalacion instalacion, ServicioSincronizacion sync)
    {
        InitializeComponent();
        _sesion = sesion;
        _instalacion = instalacion;
        _sync = sync;

        // La identidad puede cambiar en el servidor: cuando llega, se repinta.
        _instalacion.Cambio += AplicarIdentidad;

        // Al recuperar la red se vacía la cola sola. El visitador no debería tener que
        // acordarse de pulsar nada: sale del sótano y su trabajo sube.
        Connectivity.Current.ConnectivityChanged += async (_, e) =>
        {
            if (e.NetworkAccess == NetworkAccess.Internet) await _sync.ProcesarAsync();
        };
    }

    /// <summary>
    /// Al volver a primer plano se reintenta la cola. Medido en el teléfono: con un
    /// pendiente en cola y el servidor caído, al volver el servidor NADA subía — pasaron
    /// 25 segundos con la app abierta y el envío seguía ahí, esperando a que alguien
    /// pulsara Sincronizar.
    ///
    /// El evento de red no basta, y por eso hacen falta los dos: Android solo lo dispara
    /// cuando cambia el estado de la CONEXIÓN, no cuando el servidor del otro lado vuelve
    /// a responder. En la calle pasa constantemente — el teléfono marca wifi o datos todo
    /// el rato mientras la petición no llega a ninguna parte—, y volver a abrir la app es
    /// justo lo que hace el visitador entre una visita y la siguiente.
    /// </summary>
    protected override void OnResume()
    {
        base.OnResume();
        _ = _sync.ProcesarAsync();
    }

    protected override Window CreateWindow(IActivationState? activationState)
    {
        var ventana = new Window(new AppShell());
        _ = ArrancarAsync();
        return ventana;
    }

    /// <summary>
    /// Decide dónde entra la app: al trabajo si hay sesión, a la entrada si no.
    ///
    /// La sesión se da por buena mientras el refresh siga guardado, AUNQUE no haya red:
    /// echar al visitador a la pantalla de entrada porque no se pudo comprobar nada lo
    /// dejaría sin acceso a sus propios datos justo donde más falta hacen.
    /// </summary>
    private async Task ArrancarAsync()
    {
        await _sesion.RestaurarAsync();
        await _instalacion.CargarAsync();
        AplicarIdentidad();
        await _sync.RefrescarContadoresAsync();

        if (!await _sesion.HaySesionAsync()) return;   // ya se arranca en «entrar»

        // `Shell.Current` no existe hasta que la ventana termina de montarse, y esto
        // corre en paralelo a ese montaje. Sin la espera, un arranque rápido daría una
        // referencia nula DENTRO de una tarea sin dueño: nadie vería la excepción y la
        // app se quedaría en la pantalla de entrada con la sesión válida en el bolsillo.
        for (var i = 0; i < 40 && Shell.Current is null; i++)
            await Task.Delay(50);
        if (Shell.Current is null) return;

        await Shell.Current.GoToAsync("//hoy");
        await _sync.ProcesarAsync();
    }

    /// <summary>
    /// Vuelca los colores de la instalación en el diccionario de recursos.
    ///
    /// Se REEMPLAZAN las claves que la interfaz consume con DynamicResource: por eso los
    /// estilos usan DynamicResource y no StaticResource. Un StaticResource se resuelve
    /// una vez al cargar el XAML y se quedaría con el color de fábrica para siempre —
    /// el mismo error que en la versión web hizo que el color configurado no llegara a
    /// las barras mientras el resto de la aplicación sí cambiaba, sin que nada avisara.
    /// </summary>
    private void AplicarIdentidad()
    {
        MainThread.BeginInvokeOnMainThread(() =>
        {
            if (Resources is null) return;
            Resources["Accion"] = Color.FromArgb(_instalacion.ColorAccion);
            Resources["Estructura"] = Color.FromArgb(_instalacion.ColorEstructura);
        });
    }
}
