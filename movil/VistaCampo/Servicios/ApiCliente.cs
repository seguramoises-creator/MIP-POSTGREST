using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace VistaCampo.Servicios;

/// <summary>Un fallo de la API con el motivo que el servidor quiso dar al usuario.</summary>
public class ErrorApi : Exception
{
    public HttpStatusCode? Codigo { get; }

    /// <summary>
    /// `true` cuando la petición ni siquiera salió (sin red, servidor caído, DNS).
    ///
    /// Distinguirlo importa más de lo que parece: sin respuesta del servidor NO se puede
    /// afirmar nada sobre los datos ni sobre las credenciales. La versión web llegó a
    /// decir «Credenciales incorrectas» cuando el problema era el túnel, y costó una
    /// tarde de restablecer claves. Aquí un fallo de red se dice como fallo de red.
    /// </summary>
    public bool SinRespuesta => Codigo is null;

    public ErrorApi(string mensaje, HttpStatusCode? codigo = null) : base(mensaje) => Codigo = codigo;
}

/// <summary>
/// El único sitio por el que la app habla con el servidor.
///
/// Lleva el token, renueva cuando caduca y traduce los errores a algo que se pueda
/// enseñar. Todo lo demás —pantallas, cola, sincronización— asume que si esto no lanzó,
/// la petición entró.
/// </summary>
public class ApiCliente
{
    private readonly HttpClient _http;
    private readonly Sesion _sesion;
    private readonly SemaphoreSlim _renovando = new(1, 1);

    /// <summary>
    /// El servidor ya no acepta la sesión (refresh revocado o caducado): hay que volver a
    /// entrar. Lo escucha la app para llevar al visitador a la pantalla de entrada; antes
    /// seguía trabajando con la sesión muerta y cada envío decía «No se pudo validar las
    /// credenciales», sin decirle nunca qué hacer.
    /// </summary>
    public event Action? SesionVencida;

    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    public ApiCliente(Sesion sesion)
    {
        _sesion = sesion;
        _http = new HttpClient
        {
            // 20 s y no el minuto y medio por defecto: de pie en la calle, esperar más
            // de veinte segundos por una pantalla equivale a que no funcione. Si tarda
            // más, la captura se va a la cola y el visitador sigue con lo suyo.
            Timeout = TimeSpan.FromSeconds(20),
        };
    }

    private Uri Url(string ruta) => new(new Uri(_sesion.UrlServidor), $"/api/v1{ruta}");

    private async Task<HttpRequestMessage> PeticionAsync(HttpMethod metodo, string ruta, HttpContent? cuerpo = null)
    {
        var p = new HttpRequestMessage(metodo, Url(ruta)) { Content = cuerpo };
        var token = await _sesion.AccessTokenAsync();
        if (!string.IsNullOrEmpty(token))
            p.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return p;
    }

    /// <summary>
    /// Envía y, si el token venció, lo renueva UNA vez y reintenta.
    ///
    /// Una sola vez a propósito: si el refresh también falla, insistir solo consigue que
    /// el servidor vea un bucle y que el visitador espere de más para el mismo resultado.
    /// </summary>
    private async Task<HttpResponseMessage> EnviarAsync(HttpMethod metodo, string ruta,
                                                        Func<HttpContent?>? cuerpo = null)
    {
        var tokenUsado = await _sesion.AccessTokenAsync();
        HttpResponseMessage resp;
        try
        {
            resp = await _http.SendAsync(await PeticionAsync(metodo, ruta, cuerpo?.Invoke()));
        }
        catch (Exception)
        {
            throw new ErrorApi("No se pudo contactar el servidor. Revisa tu conexión.");
        }

        if (resp.StatusCode == HttpStatusCode.Unauthorized && await RenovarAsync(tokenUsado))
        {
            resp.Dispose();
            try
            {
                resp = await _http.SendAsync(await PeticionAsync(metodo, ruta, cuerpo?.Invoke()));
            }
            catch (Exception)
            {
                throw new ErrorApi("No se pudo contactar el servidor. Revisa tu conexión.");
            }
        }
        return resp;
    }

    private async Task LanzarSiFalloAsync(HttpResponseMessage r)
    {
        if (r.IsSuccessStatusCode) return;
        string detalle;
        try
        {
            // El backend responde `{"detail": "..."}`; en un 422 de Pydantic, `detail` es
            // una lista de errores por campo. Se prefiere SIEMPRE el texto del servidor:
            // está redactado para el usuario final y dice el motivo real (ciclo cerrado,
            // comentario genérico, médico sin aprobar), cosa que un mensaje nuestro no
            // podría adivinar.
            using var doc = JsonDocument.Parse(await r.Content.ReadAsStringAsync());
            var d = doc.RootElement.GetProperty("detail");
            detalle = d.ValueKind == JsonValueKind.Array
                ? string.Join("\n", d.EnumerateArray().Select(x =>
                      x.TryGetProperty("msg", out var m) ? m.GetString() : x.ToString()))
                : d.GetString() ?? r.ReasonPhrase ?? "Error";
        }
        catch
        {
            detalle = r.StatusCode switch
            {
                HttpStatusCode.Unauthorized => "Tu sesión venció. Vuelve a entrar.",
                HttpStatusCode.Forbidden => "No tienes permiso para esta operación.",
                _ => $"El servidor respondió {(int)r.StatusCode}.",
            };
        }
        throw new ErrorApi(detalle, r.StatusCode);
    }

    /// <summary>
    /// Lee el cuerpo de la respuesta traduciendo un corte de conexión a un mensaje.
    ///
    /// La conexión no solo se cae al ENVIAR: se cae a media lectura. Con el servidor
    /// tumbado la app llegó a mostrar «Algo falló: unexpected end of stream on
    /// com.android.okhttp.Address@34bee068» — el fallo era correcto, el mensaje era una
    /// excepción interna en crudo delante de un visitador en la calle. El `try/catch`
    /// del envío no lo cubría porque esto ocurre después, al leer.
    ///
    /// Se atrapa CUALQUIER excepción y no una lista de tipos: el primer intento filtró
    /// por `HttpRequestException or IOException` y el mensaje en crudo siguió saliendo
    /// igual, porque el que sube desde okhttp es un `Java.IO.IOException`, que NO
    /// hereda de `System.IO.IOException`. Aquí dentro solo se lee una respuesta HTTP;
    /// no hay lógica de negocio que una captura amplia pueda tapar.
    /// </summary>
    private static async Task<T> LeerAsync<T>(HttpResponseMessage r)
    {
        try
        {
            return (await r.Content.ReadFromJsonAsync<T>(Json))!;
        }
        catch (JsonException)
        {
            throw new ErrorApi("El servidor respondió algo que no se pudo leer.");
        }
        catch (Exception)
        {
            throw new ErrorApi("Se cortó la conexión con el servidor. Vuelve a intentar.");
        }
    }

    public async Task<T> ObtenerAsync<T>(string ruta)
    {
        using var r = await EnviarAsync(HttpMethod.Get, ruta);
        await LanzarSiFalloAsync(r);
        return await LeerAsync<T>(r);
    }

    public async Task<T> EnviarJsonAsync<T>(string ruta, object cuerpo)
    {
        using var r = await EnviarAsync(HttpMethod.Post, ruta, () => JsonContent.Create(cuerpo));
        await LanzarSiFalloAsync(r);
        return await LeerAsync<T>(r);
    }

    public async Task<T> SubirArchivoAsync<T>(string ruta, string rutaLocal, string mime)
    {
        using var r = await EnviarAsync(HttpMethod.Post, ruta, () =>
        {
            var contenido = new MultipartFormDataContent();
            var bytes = File.ReadAllBytes(rutaLocal);
            var archivo = new ByteArrayContent(bytes);
            archivo.Headers.ContentType = new MediaTypeHeaderValue(mime);
            contenido.Add(archivo, "archivo", Path.GetFileName(rutaLocal));
            return contenido;
        });
        await LanzarSiFalloAsync(r);
        return await LeerAsync<T>(r);
    }

    // ── Sesión ───────────────────────────────────────────────────────────────

    /// <summary>Login. Va como formulario, no como JSON: así lo espera el backend.</summary>
    public async Task<(string acceso, string refresco, bool debeCambiar)> EntrarAsync(string usuario, string clave)
    {
        var form = new FormUrlEncodedContent(new Dictionary<string, string>
        {
            ["username"] = usuario,
            ["password"] = clave,
        });
        HttpResponseMessage r;
        try
        {
            r = await _http.PostAsync(Url("/auth/login"), form);
        }
        catch (Exception)
        {
            throw new ErrorApi("No se pudo contactar el servidor. Revisa tu conexión.");
        }
        using (r)
        {
            await LanzarSiFalloAsync(r);
            using var doc = JsonDocument.Parse(await r.Content.ReadAsStringAsync());
            var raiz = doc.RootElement;
            return (raiz.GetProperty("access_token").GetString()!,
                    raiz.GetProperty("refresh_token").GetString()!,
                    raiz.TryGetProperty("debe_cambiar_password", out var d) && d.GetBoolean());
        }
    }

    /// <summary>
    /// Cambia la contraseña del usuario que tiene la sesión abierta.
    ///
    /// Se puede llamar con la marca de «debe cambiar» puesta: el login devuelve tokens
    /// válidos junto a esa marca, que es lo que permite hacer el cambio desde el propio
    /// teléfono en vez de mandar al visitador a la web.
    /// </summary>
    public async Task CambiarClaveAsync(string actual, string nueva)
    {
        using var r = await EnviarAsync(HttpMethod.Post, "/auth/change-password",
            () => JsonContent.Create(new { password_actual = actual, password_nuevo = nueva }));
        await LanzarSiFalloAsync(r);
    }

    /// <summary>
    /// Renueva el token de acceso con el refresh. UNA renovación a la vez.
    ///
    /// EL SERVIDOR ROTA EL REFRESH: al renovar, revoca el que se usó y entrega uno nuevo.
    /// Aquí se guardaba el viejo, así que la primera renovación funcionaba y la segunda
    /// —dos horas después de entrar— recibía «revocado»: desde ahí nada subía. Por eso se
    /// guarda el que devuelve el servidor, y por eso va con cerrojo: dos peticiones que
    /// caducan a la vez gastarían el mismo refresh y la segunda perdería la sesión.
    /// </summary>
    private async Task<bool> RenovarAsync(string? tokenUsado)
    {
        await _renovando.WaitAsync();
        try
        {
            // Otra petición ya renovó mientras esta esperaba: basta reintentar con el nuevo.
            var actual = await _sesion.AccessTokenAsync();
            if (!string.IsNullOrEmpty(actual) && actual != tokenUsado) return true;

            var refresco = await _sesion.RefreshTokenAsync();
            if (string.IsNullOrEmpty(refresco)) return false;

            HttpResponseMessage r;
            try
            {
                r = await _http.PostAsJsonAsync(Url("/auth/refresh"), new { refresh_token = refresco });
            }
            catch
            {
                return false;   // sin red la sesión NO se da por perdida: se reintentará
            }
            using (r)
            {
                if (r.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
                {
                    // El servidor contestó y dijo que no: esto sí es sesión vencida.
                    SesionVencida?.Invoke();
                    return false;
                }
                if (!r.IsSuccessStatusCode) return false;
                using var doc = JsonDocument.Parse(await r.Content.ReadAsStringAsync());
                var raiz = doc.RootElement;
                var nuevo = raiz.TryGetProperty("refresh_token", out var nr) && nr.ValueKind == JsonValueKind.String
                    ? nr.GetString()!
                    : refresco;
                await _sesion.GuardarTokensAsync(raiz.GetProperty("access_token").GetString()!, nuevo);
                return true;
            }
        }
        catch { return false; }
        finally { _renovando.Release(); }
    }
}
