using System.Text.Json;
using VistaCampo.Modelos;

namespace VistaCampo.Servicios;

/// <summary>
/// Lo que distingue una instalación de otra: sus colores, su logotipo y por qué puerta
/// entran los datos.
///
/// Se lee del servidor al arrancar y se guarda para el siguiente arranque sin red. La
/// app NO decide nada de esto por su cuenta: la misma compilación sirve a VISTA y a
/// Laboratorios Mallén, y lo que cambia entre ellas vive en el servidor.
/// </summary>
public class ServicioInstalacion
{
    private readonly ApiCliente _api;

    public ServicioInstalacion(ApiCliente api) => _api = api;

    /// <summary>
    /// Configuración vigente. Es un objeto MUTABLE y se actualiza en sitio a propósito:
    /// quien lo tomó al arrancar tiene que ver el cambio. Copiar sus valores a campos
    /// propios los congelaría, y ese error ya costó tres veces en la web que el color
    /// configurado no llegara a las barras mientras el resto de la app sí cambiaba.
    /// </summary>
    public ConfigInstalacion Config { get; } = new();

    public string ColorAccion { get; private set; } = "#0050B4";
    public string ColorEstructura { get; private set; } = "#1A237E";
    public string NombreIdentidad { get; private set; } = "VISTA";

    /// <summary>Se dispara cuando la identidad cambia, para repintar lo que ya está en pantalla.</summary>
    public event Action? Cambio;

    public async Task CargarAsync()
    {
        RestaurarDeDisco();
        try
        {
            var app = await _api.ObtenerAsync<JsonElement>("/admin/config/app");
            Config.ModoIngesta = app.TryGetProperty("modo_ingesta", out var m) ? m.GetString() ?? "excel" : "excel";
            Config.MonitorDia = app.TryGetProperty("monitor_dia", out var d) && d.GetBoolean();

            var marca = await _api.ObtenerAsync<JsonElement>("/admin/config/marca");
            var rojo = marca.TryGetProperty("rojo", out var r) ? r.GetString() : null;
            var taupe = marca.TryGetProperty("taupe", out var t) ? t.GetString() : null;
            var logo = marca.TryGetProperty("logo", out var l) ? l.GetString() : null;

            AplicarIdentidad(logo, rojo, taupe);
            GuardarEnDisco();
        }
        catch (ErrorApi)
        {
            // Sin conexión se queda con lo último conocido. Una app de campo que no
            // arranca porque no pudo preguntar de qué color es sería absurda.
        }
        Cambio?.Invoke();
    }

    /// <summary>
    /// Aplica la identidad: primero la paleta de la marca elegida, y encima los colores
    /// propios si la instalación los cambió.
    ///
    /// Los tonos de VISTA no se calculan: están medidos. El azul de acción sale del
    /// propio logotipo, y el aclarado existe porque el de marca sobre el fondo profundo
    /// da 2.24:1 — por debajo del 3:1 que WCAG 1.4.11 exige a un elemento gráfico.
    /// </summary>
    private void AplicarIdentidad(string? logo, string? rojo, string? taupe)
    {
        NombreIdentidad = (logo ?? "vista").Equals("mallen", StringComparison.OrdinalIgnoreCase)
            ? "Laboratorios Mallén" : "VISTA";
        var (accionBase, estructuraBase) = NombreIdentidad == "VISTA"
            ? ("#0050B4", "#1A237E")
            : ("#F63440", "#686158");
        ColorAccion = EsHex(rojo) ? rojo!.ToUpperInvariant() : accionBase;
        ColorEstructura = EsHex(taupe) ? taupe!.ToUpperInvariant() : estructuraBase;
    }

    private static bool EsHex(string? s)
        => !string.IsNullOrWhiteSpace(s) && s.Length == 7 && s[0] == '#'
           && s[1..].All(Uri.IsHexDigit);

    private const string CLAVE = "instalacion";

    private void GuardarEnDisco() => Preferences.Set(CLAVE, JsonSerializer.Serialize(new
    {
        Config.ModoIngesta, Config.MonitorDia, ColorAccion, ColorEstructura, NombreIdentidad,
    }));

    private void RestaurarDeDisco()
    {
        var crudo = Preferences.Get(CLAVE, "");
        if (string.IsNullOrEmpty(crudo)) return;
        try
        {
            var d = JsonSerializer.Deserialize<JsonElement>(crudo);
            Config.ModoIngesta = d.GetProperty("ModoIngesta").GetString() ?? "excel";
            Config.MonitorDia = d.GetProperty("MonitorDia").GetBoolean();
            ColorAccion = d.GetProperty("ColorAccion").GetString() ?? ColorAccion;
            ColorEstructura = d.GetProperty("ColorEstructura").GetString() ?? ColorEstructura;
            NombreIdentidad = d.GetProperty("NombreIdentidad").GetString() ?? NombreIdentidad;
        }
        catch { /* una preferencia corrupta no debe impedir arrancar */ }
    }
}
