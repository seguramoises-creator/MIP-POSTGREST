using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class PlanPagina : ContentPage
{
    private readonly PlanVista _vm;

    public PlanPagina(PlanVista vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.AlAparecerAsync();
    }
}
