using VistaCampo.VistaModelos;

namespace VistaCampo.Vistas;

public partial class CambiarClavePagina : ContentPage
{
    public CambiarClavePagina(CambiarClaveVista vm)
    {
        InitializeComponent();
        BindingContext = vm;
    }
}
