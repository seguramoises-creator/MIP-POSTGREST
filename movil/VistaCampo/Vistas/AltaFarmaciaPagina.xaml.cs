using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class AltaFarmaciaPagina : ContentPage
{
    private readonly AltaFarmaciaVista _vm;

    public AltaFarmaciaPagina(AltaFarmaciaVista vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        _vm.Cargar();
    }
}
