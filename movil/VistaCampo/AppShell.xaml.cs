namespace VistaCampo;

public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();

        // Las altas NO son pestañas: se abren desde el Panel y se cierran al terminar.
        // Ponerlas en la barra les daría el mismo peso que registrar una visita, y no lo
        // tienen — un visitador registra veinte visitas al día y da de alta un médico al
        // mes.
        Routing.RegisterRoute("altaMedico", typeof(Vistas.AltaMedicoPagina));
        Routing.RegisterRoute("altaFarmacia", typeof(Vistas.AltaFarmaciaPagina));
    }
}
