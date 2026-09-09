using CommunityToolkit.Mvvm.ComponentModel;

namespace VistaCampo.VistaModelos;

/// <summary>Lo común a todas las pantallas: si está trabajando y qué error mostrar.</summary>
public partial class BaseVista : ObservableObject
{
    [ObservableProperty] private bool _ocupado;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private string? _aviso;

    public bool HayError => !string.IsNullOrEmpty(Error);
    public bool HayAviso => !string.IsNullOrEmpty(Aviso);

    partial void OnErrorChanged(string? value) => OnPropertyChanged(nameof(HayError));
    partial void OnAvisoChanged(string? value) => OnPropertyChanged(nameof(HayAviso));

    /// <summary>
    /// Corre algo mostrando el reloj y traduciendo el fallo a un mensaje.
    ///
    /// El texto del servidor se muestra TAL CUAL: está redactado para el usuario final
    /// y dice el motivo real —ciclo cerrado, comentario genérico, médico sin aprobar—,
    /// que ningún mensaje nuestro podría adivinar.
    /// </summary>
    protected async Task EjecutarAsync(Func<Task> accion)
    {
        if (Ocupado) return;
        Ocupado = true;
        Error = null;
        try { await accion(); }
        catch (Servicios.ErrorApi e) { Error = e.Message; }
        catch (Exception e) { Error = $"Algo falló: {e.Message}"; }
        finally { Ocupado = false; }
    }
}
