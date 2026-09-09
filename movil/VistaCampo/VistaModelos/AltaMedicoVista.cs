using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Modelos;
using VistaCampo.Servicios;

namespace VistaCampo.VistaModelos;

/// <summary>
/// Alta de un médico en el panel del visitador.
///
/// Dos cosas que conviene tener claras antes de leer el código:
///
/// 1. LA CATEGORÍA NO SE ELIGE. Ni aquí ni en la web. El visitador captura los cinco
///    criterios y la letra la revela el sistema cuando el Gerente de Distrito aprueba.
///    Por eso el servidor no manda los puntajes de cada opción: si se vieran, se podría
///    capturar apuntando a la categoría deseada.
/// 2. EL FORMULARIO SE DIBUJA CON LO QUE MANDA EL SERVIDOR. El vocabulario de cada
///    criterio es cerrado y cambia por país; escrito a mano en la app, un cambio de
///    reglas dejaría a los médicos nuevos sin clasificar y nadie relacionaría una cosa
///    con la otra.
/// </summary>
public partial class AltaMedicoVista : BaseVista
{
    private readonly ServicioAltas _altas;
    private readonly ServicioSincronizacion _sync;

    public AltaMedicoVista(ServicioAltas altas, ServicioSincronizacion sync)
    {
        _altas = altas;
        _sync = sync;
    }

    [ObservableProperty] private string _nombre = "";
    [ObservableProperty] private string _centro = "";
    [ObservableProperty] private string _telefono = "";
    [ObservableProperty] private string _exequatur = "";
    [ObservableProperty] private string _direccion = "";
    [ObservableProperty] private string _busqueda = "";
    [ObservableProperty] private bool _plantillaLista;
    [ObservableProperty] private bool _hayDuplicados;
    [ObservableProperty] private bool _duplicadoBloqueante;
    [ObservableProperty] private bool _listo;
    [ObservableProperty] private bool _copiando;
    [ObservableProperty] private string? _origenCopia;

    public ObservableCollection<CriterioCaptura> Criterios { get; } = new();
    public ObservableCollection<MedicoExistente> Existentes { get; } = new();
    public ObservableCollection<string> Duplicados { get; } = new();

    public bool SinConexion => !ServicioSincronizacion.HayRed;

    /// <summary>
    /// El alta necesita conexión, y se explica en vez de fallar callando: la
    /// comprobación de que ese médico no existe ya vive en la base central, y un alta
    /// guardada para enviar más tarde crearía justo el duplicado que se quiere evitar.
    /// </summary>
    public string AvisoSinConexion =>
        "Para dar de alta un médico hace falta conexión: hay que comprobar antes que no "
        + "esté ya registrado. Registrar visitas sí funciona sin señal.";

    partial void OnNombreChanged(string value) => Revisar();
    partial void OnBusquedaChanged(string value) => _ = FiltrarExistentesAsync();

    private List<MedicoExistente> _todosExistentes = new();

    [RelayCommand]
    public async Task CargarAsync()
    {
        OnPropertyChanged(nameof(SinConexion));
        if (SinConexion) return;

        await EjecutarAsync(async () =>
        {
            Criterios.Clear();
            foreach (var c in await _altas.PlantillaAsync())
            {
                c.Cambio = Revisar;
                Criterios.Add(c);
            }
            PlantillaLista = Criterios.Count > 0;

            _todosExistentes = await _altas.MedicosExistentesAsync();
            await FiltrarExistentesAsync();
            Revisar();
        });
    }

    private Task FiltrarExistentesAsync()
    {
        var q = (Busqueda ?? "").Trim();
        Existentes.Clear();
        foreach (var m in _todosExistentes
                 .Where(m => q.Length >= 2 && m.Nombre.Contains(q, StringComparison.OrdinalIgnoreCase))
                 .Take(20))
            Existentes.Add(m);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Copia la ficha de un médico que ya está en otro panel.
    ///
    /// Que dos representantes visiten al mismo médico es NORMAL —líneas distintas—, y
    /// hacer que el segundo reteclee dirección, teléfono y exequátur es la forma más
    /// segura de que las dos fichas acaben distintas. Copiar rellena el formulario; la
    /// clasificación sí la captura cada uno, porque el potencial de ese médico para SU
    /// línea no tiene por qué ser el mismo.
    /// </summary>
    [RelayCommand]
    private void Copiar(MedicoExistente? m)
    {
        if (m is null) return;
        Nombre = m.Nombre;
        Centro = m.Centro ?? "";
        Telefono = m.Telefono ?? "";
        Exequatur = m.Exequatur ?? "";
        Direccion = m.Direccion ?? "";
        Copiando = true;
        OrigenCopia = $"Ficha copiada de {m.Origen.ToLowerInvariant()}. "
                    + "Falta la clasificación para TU línea.";
        Busqueda = "";
        Revisar();
    }

    /// <summary>Revisa si ya se puede guardar, sin esperar al servidor.</summary>
    private void Revisar()
    {
        Listo = !string.IsNullOrWhiteSpace(Nombre) && Nombre.Trim().Length >= 3
                && Criterios.Count > 0
                && Criterios.Where(c => c.Requerido).All(c => c.Completo);
        GuardarCommand.NotifyCanExecuteChanged();
    }

    private Dictionary<string, object?> Cuerpo()
    {
        var clasificacion = new Dictionary<string, object?>();
        foreach (var c in Criterios) clasificacion[c.Campo] = c.Valor;

        return new Dictionary<string, object?>
        {
            // `vm_id` va en 0 a propósito: el servidor lo IGNORA y lo fuerza al del
            // visitador que llama. Mandar otro daría 403, y está bien que así sea.
            ["vm_id"] = 0,
            ["nombre_completo"] = Nombre.Trim(),
            ["centro_trabajo"] = Vacio(Centro),
            ["telefono"] = Vacio(Telefono),
            ["exequatur"] = Vacio(Exequatur),
            ["direccion"] = Vacio(Direccion),
            ["clasificacion"] = clasificacion,
        };
    }

    private static string? Vacio(string? s) => string.IsNullOrWhiteSpace(s) ? null : s.Trim();

    /// <summary>
    /// Al COPIAR se confirma el parecido de entrada: el visitador ya vio la ficha y
    /// eligió esa. Preguntarle «puede que ya exista» justo después de haber pulsado
    /// «copiar» sería preguntarle por algo que acaba de decidir.
    /// </summary>
    [RelayCommand(CanExecute = nameof(PuedeGuardar))]
    private async Task GuardarAsync() => await IntentarAsync(confirmar: Copiando);

    private bool PuedeGuardar() => Listo && !SinConexion;

    /// <summary>
    /// «Es otro médico, continuar»: solo aparece cuando el parecido es BLANDO (mismo
    /// nombre en otra provincia, por ejemplo). Un duplicado duro —exequátur o cédula
    /// repetidos, o el mismo nombre en el mismo centro— no se puede saltar, y el
    /// servidor tampoco lo permitiría.
    /// </summary>
    [RelayCommand]
    private async Task ConfirmarDistintoAsync() => await IntentarAsync(confirmar: true);

    private async Task IntentarAsync(bool confirmar)
    {
        await EjecutarAsync(async () =>
        {
            Duplicados.Clear();
            HayDuplicados = false;
            try
            {
                await _altas.CrearMedicoAsync(Cuerpo(), confirmar);
                Aviso = "Médico enviado. Queda pendiente de la aprobación de tu Gerente "
                      + "de Distrito; hasta entonces no le puedes registrar visita.";
                Limpiar();
                await _sync.DescargarCatalogosAsync();
            }
            catch (PosibleDuplicado d)
            {
                foreach (var c in d.Coincidencias) Duplicados.Add(c);
                DuplicadoBloqueante = d.Bloqueante;
                HayDuplicados = true;
                Error = d.Bloqueante
                    ? "Ese médico ya está registrado. Búscalo arriba y cópialo a tu panel."
                    : "Puede que ya esté registrado. Revísalo antes de continuar.";
            }
        });
    }

    private void Limpiar()
    {
        Nombre = Centro = Telefono = Exequatur = Direccion = "";
        foreach (var c in Criterios) { c.ValorTexto = null; c.ValorNumero = null; }
        Duplicados.Clear();
        HayDuplicados = false;
        Copiando = false;
        OrigenCopia = null;
    }
}
