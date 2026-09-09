using Microsoft.Extensions.Logging;
using VistaCampo.Datos;
using VistaCampo.Servicios;
using VistaCampo.VistaModelos;
using VistaCampo.Vistas;

namespace VistaCampo;

public static class MauiProgram
{
    public static MauiApp CreateMauiApp()
    {
        // Arranca el motor de SQLite. Con `sqlite-net-base` esto NO es automático: sin
        // esta línea la app compila, instala, abre… y revienta la primera vez que toca
        // la base local, que es exactamente al guardar la primera visita.
        SQLitePCL.Batteries_V2.Init();

        var builder = MauiApp.CreateBuilder();
        builder
            .UseMauiApp<App>()
            .ConfigureFonts(fonts =>
            {
                fonts.AddFont("OpenSans-Regular.ttf", "OpenSansRegular");
                fonts.AddFont("OpenSans-Semibold.ttf", "OpenSansSemibold");
            });

        // ── Servicios: uno solo de cada, vivos toda la sesión ────────────────
        // `Sesion` e `Instalacion` guardan estado compartido, y `ServicioSincronizacion`
        // tiene la cola: dos instancias procesarían la misma cola a la vez y subirían
        // duplicados.
        builder.Services.AddSingleton<Sesion>();
        builder.Services.AddSingleton<ApiCliente>();
        builder.Services.AddSingleton<BaseLocal>();
        builder.Services.AddSingleton<ServicioInstalacion>();
        builder.Services.AddSingleton<ServicioSincronizacion>();
        builder.Services.AddSingleton<ServicioAltas>();

        // ── Pantallas ────────────────────────────────────────────────────────
        // Transitorias: cada vez que se abre una pestaña se arma limpia, sin arrastrar
        // el texto a medio escribir de la vez anterior.
        builder.Services.AddTransient<EntrarVista>();
        builder.Services.AddTransient<HoyVista>();
        builder.Services.AddTransient<RegistrarVista>();
        builder.Services.AddTransient<PanelVista>();
        builder.Services.AddTransient<PlanVista>();
        builder.Services.AddTransient<PerfilVista>();
        builder.Services.AddTransient<AltaMedicoVista>();
        builder.Services.AddTransient<AltaFarmaciaVista>();

        builder.Services.AddTransient<EntrarPagina>();
        builder.Services.AddTransient<HoyPagina>();
        builder.Services.AddTransient<RegistrarPagina>();
        builder.Services.AddTransient<PanelPagina>();
        builder.Services.AddTransient<PlanPagina>();
        builder.Services.AddTransient<PerfilPagina>();
        builder.Services.AddTransient<AltaMedicoPagina>();
        builder.Services.AddTransient<AltaFarmaciaPagina>();

#if DEBUG
        builder.Logging.AddDebug();
#endif

        return builder.Build();
    }
}
