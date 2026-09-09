using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class RegistrarPagina : ContentPage
{
    private readonly RegistrarVista _vm;

    public RegistrarPagina(RegistrarVista vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.CargarAsync();
    }

    // Estos dos van en el code-behind y no como comandos porque solo cambian el modo de
    // la propia pantalla: no hay lógica de negocio que probar en ellos.
    private void ElegirMedico(object? sender, EventArgs e) => _vm.EsFarmacia = false;
    private void ElegirFarmacia(object? sender, EventArgs e) => _vm.EsFarmacia = true;
}
