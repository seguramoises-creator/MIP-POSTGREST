using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class PanelPagina : ContentPage
{
    private readonly PanelVista _vm;

    public PanelPagina(PanelVista vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.CargarAsync();
    }

    private void VerMedicos(object? sender, EventArgs e) => _vm.VerFarmacias = false;
    private void VerFarmacias(object? sender, EventArgs e) => _vm.VerFarmacias = true;

    private async void NuevoMedico(object? sender, EventArgs e)
        => await Shell.Current.GoToAsync("altaMedico");

    private async void NuevaFarmacia(object? sender, EventArgs e)
        => await Shell.Current.GoToAsync("altaFarmacia");
}
