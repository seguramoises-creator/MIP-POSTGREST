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
}
