using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Datos;
using VistaCampo.Modelos;

namespace VistaCampo.VistaModelos;

/// <summary>El panel del visitador: sus médicos y sus farmacias.</summary>
public partial class PanelVista : BaseVista
{
    private readonly BaseLocal _base;

    public PanelVista(BaseLocal baseLocal) => _base = baseLocal;

    [ObservableProperty] private string _busqueda = "";
    [ObservableProperty] private bool _verFarmacias;
    [ObservableProperty] private int _pendientesAprobacion;

    public ObservableCollection<MedicoPanel> Medicos { get; } = new();
    public ObservableCollection<FarmaciaPanel> Farmacias { get; } = new();

    public bool HayPendientes => PendientesAprobacion > 0;

    /// <summary>
    /// Se dice con estas palabras porque la confusión es real: un médico pendiente SÍ
    /// existe en el panel; lo que está pendiente es su alta en el maestro, y hasta que
    /// el gerente la apruebe no admite visita.
    /// </summary>
    public string TextoPendientes =>
        $"{PendientesAprobacion} esperando la aprobación de tu Gerente de Distrito. "
        + "Hasta entonces no les puedes registrar visita.";

    partial void OnBusquedaChanged(string value) => _ = CargarAsync();
    partial void OnVerFarmaciasChanged(bool value) => _ = CargarAsync();
    partial void OnPendientesAprobacionChanged(int value)
    {
        OnPropertyChanged(nameof(HayPendientes));
        OnPropertyChanged(nameof(TextoPendientes));
    }

    [RelayCommand]
    public async Task CargarAsync()
    {
        var q = (Busqueda ?? "").Trim();

        var medicos = await _base.MedicosAsync();
        PendientesAprobacion = medicos.Count(m => m.EstadoAprobacion != "APROBADO");
        Medicos.Clear();
        foreach (var m in medicos.Where(m => q.Length == 0 ||
                 m.Nombre.Contains(q, StringComparison.OrdinalIgnoreCase)))
            Medicos.Add(m);

        var farmacias = await _base.FarmaciasAsync();
        Farmacias.Clear();
        foreach (var f in farmacias.Where(f => q.Length == 0 ||
                 f.Nombre.Contains(q, StringComparison.OrdinalIgnoreCase)))
            Farmacias.Add(f);
    }
}
