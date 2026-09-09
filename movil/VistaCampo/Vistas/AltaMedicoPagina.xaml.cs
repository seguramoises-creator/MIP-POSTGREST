using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class AltaMedicoPagina : ContentPage
{
    private readonly AltaMedicoVista _vm;

    public AltaMedicoPagina(AltaMedicoVista vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.CargarAsync();
    }
}
