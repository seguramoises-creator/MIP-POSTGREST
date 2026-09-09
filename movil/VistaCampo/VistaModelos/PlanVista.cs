using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Datos;
using VistaCampo.Modelos;

namespace VistaCampo.VistaModelos;

/// <summary>
/// La planeación del ciclo: en qué semana verá a cada médico.
///
/// Las tres reglas del servidor (P01, P02, P03) se comprueban aquí y se señalan sobre la
/// fila concreta. Enviar un plan entero para que el servidor devuelva «P02» sin decir de
/// quién obliga a revisarlo a mano línea por línea.
/// </summary>
public partial class PlanVista : BaseVista
{
    private readonly BaseLocal _base;

    public PlanVista(BaseLocal baseLocal) => _base = baseLocal;

    public ObservableCollection<ItemPlan> Items { get; } = new();
    public ObservableCollection<string> Problemas { get; } = new();

    [ObservableProperty] private int _totalVistas;
    [ObservableProperty] private int _totalRevisitas;

    public bool HayProblemas => Problemas.Count > 0;

    [RelayCommand]
    public async Task CargarAsync()
    {
        Items.Clear();
        foreach (var i in (await _base.PlanAsync()).OrderBy(i => i.Semana).ThenBy(i => i.Medico))
            Items.Add(i);
        TotalVistas = Items.Count(i => i.TipoVisita == "V");
        TotalRevisitas = Items.Count(i => i.TipoVisita == "R");
        Validar();
    }

    /// <summary>
    /// P01 — máximo 2 por médico: una Vista y una Revisita.
    /// P02 — la Revisita en una semana igual o posterior a la de la Vista.
    /// P03 — Vista y Revisita no el mismo día.
    /// </summary>
    public void Validar()
    {
        Problemas.Clear();
        foreach (var grupo in Items.GroupBy(i => i.MedicoId))
        {
            var nombre = grupo.First().Medico;
            var vistas = grupo.Where(i => i.TipoVisita == "V").ToList();
            var revisitas = grupo.Where(i => i.TipoVisita == "R").ToList();

            if (vistas.Count > 1 || revisitas.Count > 1)
                Problemas.Add($"{nombre}: solo puede llevar una Vista y una Revisita en el ciclo.");

            if (vistas.Count == 1 && revisitas.Count == 1)
            {
                if (revisitas[0].Semana < vistas[0].Semana)
                    Problemas.Add($"{nombre}: la Revisita va en la semana {revisitas[0].Semana}, "
                                  + $"antes que la Vista (semana {vistas[0].Semana}).");
                if (!string.IsNullOrEmpty(vistas[0].Dia) && vistas[0].Dia == revisitas[0].Dia)
                    Problemas.Add($"{nombre}: la Vista y la Revisita caen el mismo día ({vistas[0].Dia}).");
            }
        }
        OnPropertyChanged(nameof(HayProblemas));
    }
}
