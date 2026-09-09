using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class HoyPagina : ContentPage
{
    private readonly HoyVista _vm;

    public HoyPagina(HoyVista vm)
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
