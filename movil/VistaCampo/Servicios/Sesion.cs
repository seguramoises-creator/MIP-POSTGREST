using System.Text;
using System.Text.Json;

namespace VistaCampo.Servicios;

/// <summary>
/// Quién está usando la app y contra qué servidor.
///
/// Los tokens van en <see cref="SecureStorage"/> y no en `Preferences` ni en la base
/// local: en un teléfono perdido o con acceso físico, `Preferences` es un XML legible.
/// </summary>
public class Sesion
{
    private const string CLAVE_ACCESO = "token_acceso";
    private const string CLAVE_REFRESCO = "token_refresco";
    private const string CLAVE_SERVIDOR = "url_servidor";

    /// <summary>El servidor por defecto. Se puede cambiar desde la pantalla de entrada.</summary>
    public const string SERVIDOR_POR_DEFECTO = "https://vista-mip.com";

    public string UrlServidor
    {
        get => Preferences.Get(CLAVE_SERVIDOR, SERVIDOR_POR_DEFECTO);
        set => Preferences.Set(CLAVE_SERVIDOR, value.TrimEnd('/'));
    }

    public string? Usuario { get; private set; }
    public string? NombreCompleto { get; private set; }
    public string? Rol { get; private set; }

    public async Task<string?> AccessTokenAsync() => await Leer(CLAVE_ACCESO);
    public async Task<string?> RefreshTokenAsync() => await Leer(CLAVE_REFRESCO);

    private static async Task<string?> Leer(string clave)
    {
        // SecureStorage puede lanzar en algunos aparatos (almacén de claves corrupto,
        // perfil de trabajo). Que la app arranque sin sesión es molesto; que reviente al
        // abrir es fatal.
        try { return await SecureStorage.GetAsync(clave); } catch { return null; }
    }

    public async Task GuardarTokensAsync(string acceso, string refresco)
    {
        try
        {
            await SecureStorage.SetAsync(CLAVE_ACCESO, acceso);
            await SecureStorage.SetAsync(CLAVE_REFRESCO, refresco);
        }
        catch { /* sin almacén seguro la sesión dura lo que la app en memoria */ }
        LeerDatosDelToken(acceso);
    }

    public async Task<bool> HaySesionAsync() => !string.IsNullOrEmpty(await RefreshTokenAsync());

    public async Task CerrarAsync()
    {
        try
        {
            SecureStorage.Remove(CLAVE_ACCESO);
            SecureStorage.Remove(CLAVE_REFRESCO);
        }
        catch { }
        Usuario = NombreCompleto = Rol = null;
        await Task.CompletedTask;
    }

    /// <summary>Recupera nombre y rol del token guardado, para pintar el Perfil sin red.</summary>
    public async Task RestaurarAsync()
    {
        var t = await AccessTokenAsync();
        if (!string.IsNullOrEmpty(t)) LeerDatosDelToken(t);
    }

    /// <summary>
    /// Lee el contenido del JWT SIN validar la firma, y es correcto que no la valide: la
    /// firma la comprueba el servidor en cada petición. Aquí solo se usa para saber qué
    /// nombre pintar en el Perfil — confiar en esto para decidir permisos sería el error.
    /// </summary>
    private void LeerDatosDelToken(string jwt)
    {
        try
        {
            var partes = jwt.Split('.');
            if (partes.Length < 2) return;
            var carga = partes[1].Replace('-', '+').Replace('_', '/');
            carga = carga.PadRight(carga.Length + (4 - carga.Length % 4) % 4, '=');
            using var doc = JsonDocument.Parse(Encoding.UTF8.GetString(Convert.FromBase64String(carga)));
            var r = doc.RootElement;
            Usuario = r.TryGetProperty("username", out var u) ? u.GetString() : null;
            NombreCompleto = r.TryGetProperty("nombre_completo", out var n) ? n.GetString() : null;
            Rol = r.TryGetProperty("rol", out var ro) ? ro.GetString() : null;
        }
        catch { /* un token ilegible no debe tumbar el arranque */ }
    }
}
