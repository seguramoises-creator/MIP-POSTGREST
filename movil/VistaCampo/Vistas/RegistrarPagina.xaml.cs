using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class RegistrarPagina : ContentPage
{
    private readonly RegistrarVista _vm;

    public RegistrarPagina(RegistrarVista vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;

        // Guardar CIERRA la ficha y el aviso queda arriba del todo — pero el visitador
        // está a media pantalla, donde estaba el botón. Sin subir la vista, la app
        // parecía no hacer nada: la visita entraba a la base (medido: id 939) y en
        // pantalla no quedaba señal alguna de que hubiera pasado.
        _vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(RegistrarVista.Aviso) or nameof(RegistrarVista.Error)
                && (_vm.HayAviso || _vm.HayError))
                MainThread.BeginInvokeOnMainThread(() => _ = lienzo.ScrollToAsync(0, 0, true));
        };
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.CargarAsync();
    }
}
