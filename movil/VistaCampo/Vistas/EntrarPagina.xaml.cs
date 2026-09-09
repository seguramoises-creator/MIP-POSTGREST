using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class EntrarPagina : ContentPage
{
    private readonly EntrarVista _vm;

    public EntrarPagina(EntrarVista vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        // La identidad puede haber llegado del servidor después de construir la página.
        _vm.RefrescarIdentidad();
    }
}
