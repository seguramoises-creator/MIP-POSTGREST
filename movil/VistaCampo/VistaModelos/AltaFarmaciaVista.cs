using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Modelos;
using VistaCampo.Servicios;

namespace VistaCampo.VistaModelos;

/// <summary>
/// Alta de una farmacia. Dos caminos, y el orden entre ellos es la regla:
///
///   BUSCAR primero. Casi siempre la farmacia ya existe en el maestro y lo que hace
///   falta es agregarla al panel, no crearla otra vez. El formulario de creación NO se
///   habilita hasta que una búsqueda vuelve vacía — es la regla F25 del sistema, y es
///   lo que evita la mitad de los duplicados.
///
///   Acción A: existe → se agrega al panel.
///   Acción B: no existe → se crea, con dirección y encargado OBLIGATORIOS (F23/F24).
///
/// En ambos casos queda pendiente de la aprobación del Gerente de Distrito.
/// </summary>
public partial class AltaFarmaciaVista : BaseVista
{
    private readonly ServicioAltas _altas;
    private readonly ServicioSincronizacion _sync;

    public AltaFarmaciaVista(ServicioAltas altas, ServicioSincronizacion sync)
    {
        _altas = altas;
        _sync = sync;
    }

    [ObservableProperty] private bool _esCadena;
    [ObservableProperty] private string _cadena = "";
    [ObservableProperty] private string _sucursal = "";
    [ObservableProperty] private string _nombre = "";
    [ObservableProperty] private string _direccion = "";
    [ObservableProperty] private string _encargado = "";
    [ObservableProperty] private string _telefono = "";
    [ObservableProperty] private string _sector = "";
    [ObservableProperty] private bool _buscado;
    [ObservableProperty] private bool _puedeCrear;

    public ObservableCollection<FarmaciaMaestro> Encontradas { get; } = new();

    public bool SinConexion => !ServicioSincronizacion.HayRed;
    public bool HayEncontradas => Encontradas.Count > 0;

    public string AvisoSinConexion =>
        "Para dar de alta una farmacia hace falta conexión: primero hay que comprobar si "
        + "ya está registrada. Registrar visitas sí funciona sin señal.";

    /// <summary>Qué falta para poder crear, dicho antes de que el servidor lo rechace.</summary>
    public string AyudaCreacion
    {
        get
        {
            var faltan = new List<string>();
            if (EsCadena && string.IsNullOrWhiteSpace(Cadena)) faltan.Add("la cadena");
            if (EsCadena && string.IsNullOrWhiteSpace(Sucursal)) faltan.Add("la sucursal");
            if (!EsCadena && string.IsNullOrWhiteSpace(Nombre)) faltan.Add("el nombre");
            if (string.IsNullOrWhiteSpace(Direccion)) faltan.Add("la dirección");
            if (string.IsNullOrWhiteSpace(Encargado)) faltan.Add("el encargado");
            return faltan.Count == 0 ? " " : "Falta " + string.Join(", ", faltan) + ".";
        }
    }

    partial void OnEsCadenaChanged(bool value) => Reiniciar();
    partial void OnCadenaChanged(string value) => Reiniciar();
    partial void OnSucursalChanged(string value) => Reiniciar();
    partial void OnNombreChanged(string value) => Reiniciar();
    partial void OnDireccionChanged(string value) => Revisar();
    partial void OnEncargadoChanged(string value) => Revisar();

    /// <summary>
    /// Cambiar el nombre invalida la búsqueda anterior: si no, se podría buscar «Carol
    /// Naco», no encontrar nada, y crear «Farmacia Los Prados» sin haberla buscado nunca.
    /// </summary>
    private void Reiniciar()
    {
        Buscado = false;
        PuedeCrear = false;
        Encontradas.Clear();
        OnPropertyChanged(nameof(HayEncontradas));
        Revisar();
    }

    private void Revisar()
    {
        OnPropertyChanged(nameof(AyudaCreacion));
        CrearCommand.NotifyCanExecuteChanged();
    }

    [RelayCommand]
    public void Cargar() => OnPropertyChanged(nameof(SinConexion));

    [RelayCommand]
    private async Task BuscarAsync()
    {
        await EjecutarAsync(async () =>
        {
            Aviso = null;
            var r = await _altas.BuscarFarmaciaAsync(
                EsCadena, Vacio(Cadena), Vacio(Sucursal), Vacio(Nombre));
            Encontradas.Clear();
            foreach (var f in r) Encontradas.Add(f);
            OnPropertyChanged(nameof(HayEncontradas));

            Buscado = true;
            PuedeCrear = r.Count == 0;
            Aviso = r.Count == 0
                ? "No está registrada. Ya puedes darla de alta."
                : "Ya existe. Agrégala a tu panel en vez de crearla otra vez.";
            Revisar();
        });
    }

    [RelayCommand]
    private async Task AgregarAsync(FarmaciaMaestro? f)
    {
        if (f is null) return;
        await EjecutarAsync(async () =>
        {
            await _altas.AgregarFarmaciaAlPanelAsync(f.Id);
            Aviso = "Agregada a tu panel. Queda pendiente de la aprobación de tu Gerente de Distrito.";
            await _sync.DescargarCatalogosAsync();
            Limpiar();
        });
    }

    private bool PuedeCrearse()
        => PuedeCrear && !SinConexion
           && !string.IsNullOrWhiteSpace(Direccion) && !string.IsNullOrWhiteSpace(Encargado)
           && (EsCadena
                ? !string.IsNullOrWhiteSpace(Cadena) && !string.IsNullOrWhiteSpace(Sucursal)
                : !string.IsNullOrWhiteSpace(Nombre));

    [RelayCommand(CanExecute = nameof(PuedeCrearse))]
    private async Task CrearAsync()
    {
        await EjecutarAsync(async () =>
        {
            await _altas.CrearFarmaciaAsync(new Dictionary<string, object?>
            {
                ["es_cadena"] = EsCadena,
                ["cadena"] = EsCadena ? Vacio(Cadena) : null,
                ["sucursal"] = EsCadena ? Vacio(Sucursal) : null,
                ["nombre"] = EsCadena ? null : Vacio(Nombre),
                ["direccion"] = Direccion.Trim(),
                ["encargado"] = Encargado.Trim(),
                ["telefono"] = Vacio(Telefono),
                ["sector"] = Vacio(Sector),
            });
            Aviso = "Farmacia enviada. Queda pendiente de la aprobación de tu Gerente de "
                  + "Distrito; hasta entonces no le puedes registrar visita.";
            await _sync.DescargarCatalogosAsync();
            Limpiar();
        });
    }

    private static string? Vacio(string? s) => string.IsNullOrWhiteSpace(s) ? null : s.Trim();

    private void Limpiar()
    {
        Cadena = Sucursal = Nombre = Direccion = Encargado = Telefono = Sector = "";
        Reiniciar();
    }
}
