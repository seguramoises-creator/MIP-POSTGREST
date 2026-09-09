using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class PerfilPagina : ContentPage
{
    private readonly PerfilVista _vm;

    public PerfilPagina(PerfilVista vm)
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
