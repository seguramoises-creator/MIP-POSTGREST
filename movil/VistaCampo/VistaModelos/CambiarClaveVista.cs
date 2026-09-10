using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Servicios;

namespace VistaCampo.VistaModelos;

/// <summary>
/// Cambiar la contraseña desde el propio teléfono, la primera vez que se entra.
///
/// Antes la app decía «Debes cambiar tu contraseña antes de entrar. Hazlo desde la web»
/// y cerraba la sesión. Para un visitador recién dado de alta eso es un callejón: está
/// en la calle, con el teléfono, y lo único que la app le ofrece es un sitio al que no
/// puede ir. La cuenta existe, la contraseña que le dieron es correcta y aun así no
/// entra — y el mensaje ni siquiera dice que su clave estaba bien.
///
/// El servidor SÍ devuelve tokens junto a `debe_cambiar_password`, así que se puede
/// cambiar desde aquí sin ningún permiso especial: se entra, se cambia y se sigue.
/// </summary>
public partial class CambiarClaveVista : BaseVista
{
    private readonly ApiCliente _api;
    private readonly Sesion _sesion;
    private readonly ServicioSincronizacion _sync;

    public CambiarClaveVista(ApiCliente api, Sesion sesion, ServicioSincronizacion sync)
    {
        _api = api;
        _sesion = sesion;
        _sync = sync;
    }

    /// <summary>
    /// El suelo de longitud lo decide el servidor por rol y por configuración, así que
    /// aquí se usa el de un visitador (8). No se copia la regla entera: lo que la app
    /// comprueba es para no hacerle escribir dos veces algo que va a rechazar; la
    /// palabra final —incluida la de no reutilizar una anterior— la tiene el servidor,
    /// y su mensaje se enseña tal cual.
    /// </summary>
    private const int MINIMO = 8;

    [ObservableProperty] private string _actual = "";
    [ObservableProperty] private string _nueva = "";
    [ObservableProperty] private string _repetida = "";

    /// <summary>Por qué la contraseña no vale todavía; vacío cuando ya vale.</summary>
    public string Ayuda
    {
        get
        {
            var n = Nueva ?? "";
            if (n.Length == 0) return $"Mínimo {MINIMO} caracteres, con mayúscula, minúscula, número y un símbolo.";
            if (n.Length < MINIMO) return $"Te faltan {MINIMO - n.Length} caracteres.";
            if (!n.Any(char.IsUpper)) return "Falta una MAYÚSCULA.";
            if (!n.Any(char.IsLower)) return "Falta una minúscula.";
            if (!n.Any(char.IsDigit)) return "Falta un número.";
            if (!n.Any(EsEspecial)) return "Falta un símbolo (por ejemplo ! @ # $ ¿).";
            if (n == Actual) return "La nueva no puede ser igual a la actual.";
            if (Repetida.Length > 0 && n != Repetida) return "Las dos no coinciden.";
            return " ";
        }
    }

    /// <summary>Igual que el servidor: especial es todo lo que no es letra, dígito ni espacio.</summary>
    private static bool EsEspecial(char c) => !char.IsLetterOrDigit(c) && !char.IsWhiteSpace(c);

    partial void OnActualChanged(string value) => Revisar();
    partial void OnNuevaChanged(string value) => Revisar();
    partial void OnRepetidaChanged(string value) => Revisar();

    private void Revisar()
    {
        OnPropertyChanged(nameof(Ayuda));
        GuardarCommand.NotifyCanExecuteChanged();
    }

    private bool PuedeGuardar()
    {
        var n = Nueva ?? "";
        return Actual.Length > 0 && n.Length >= MINIMO && n == Repetida && n != Actual
               && n.Any(char.IsUpper) && n.Any(char.IsLower) && n.Any(char.IsDigit) && n.Any(EsEspecial);
    }

    [RelayCommand(CanExecute = nameof(PuedeGuardar))]
    private async Task GuardarAsync()
    {
        await EjecutarAsync(async () =>
        {
            await _api.CambiarClaveAsync(Actual, Nueva);

            // La sesión sigue siendo válida: el servidor no revoca el acceso al cambiar,
            // solo baja la marca. Se entra directo, que es lo que el visitador espera
            // después de haber escrito tres veces su contraseña de pie en la calle.
            Aviso = "Contraseña actualizada. Entrando…";
            Actual = Nueva = Repetida = "";

            var fallo = await _sync.DescargarCatalogosAsync();
            if (fallo is not null)
                Aviso = "Contraseña actualizada, pero no se pudieron descargar los catálogos: " + fallo;

            if (Shell.Current is not null) await Shell.Current.GoToAsync("//hoy");
        });
    }

    /// <summary>
    /// Salir sin cambiarla deja la sesión cerrada, no a medias.
    ///
    /// Con la marca puesta el servidor no la considera una sesión de trabajo; dejar los
    /// tokens guardados haría que el siguiente arranque entrara directo a Hoy saltándose
    /// el cambio, que es justo lo que esta pantalla existe para impedir.
    /// </summary>
    [RelayCommand]
    private async Task CancelarAsync()
    {
        await _sesion.CerrarAsync();
        if (Shell.Current is not null) await Shell.Current.GoToAsync("//entrar");
    }
}
