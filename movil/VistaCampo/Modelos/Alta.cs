using CommunityToolkit.Mvvm.ComponentModel;

namespace VistaCampo.Modelos;

/// <summary>
/// Uno de los criterios de clasificación del médico, tal como lo describe el servidor.
///
/// El formulario se DIBUJA a partir de esto, no está escrito en la app: cada criterio
/// tiene un vocabulario cerrado y distinto por país (Potencial de Prescripción va
/// «1» / «2 a 3» / «4 a 6» / «6 a 9» / «10 o Mas»; KOL no es un sí/no sino
/// «Ninguno» … «Presidente de Sociedad, Charlista»). Un valor escrito a mano no
/// coincide con ninguna regla y el médico queda SIN clasificar.
///
/// El servidor nunca manda los puntajes de cada opción, y hace bien: si el visitador
/// los viera podría capturar apuntando a la categoría que quiere.
/// </summary>
public partial class CriterioCaptura : ObservableObject
{
    public string Campo { get; set; } = "";        // nombre que espera el endpoint
    public string Etiqueta { get; set; } = "";
    public string Tipo { get; set; } = "TEXTO";     // TEXTO | NUMERICO
    public bool Requerido { get; set; } = true;
    public List<string> Opciones { get; set; } = new();

    [ObservableProperty] private string? _valorTexto;
    [ObservableProperty] private string? _valorNumero;

    public bool EsNumerico => Tipo == "NUMERICO";
    public bool EsTexto => !EsNumerico;

    /// <summary>¿Está capturado y es válido para enviar?</summary>
    public bool Completo => EsNumerico
        ? decimal.TryParse(ValorNumero, out var n) && n >= 0
        : !string.IsNullOrWhiteSpace(ValorTexto);

    public object? Valor => EsNumerico
        ? (decimal.TryParse(ValorNumero, out var n) ? n : null)
        : ValorTexto;

    partial void OnValorTextoChanged(string? value) => Cambio?.Invoke();
    partial void OnValorNumeroChanged(string? value) => Cambio?.Invoke();

    /// <summary>Avisa a la pantalla para que reevalúe si ya se puede guardar.</summary>
    public Action? Cambio { get; set; }
}

/// <summary>
/// Un médico que ya existe en el panel de otro visitador del mismo país.
///
/// Trae la ficha COMPLETA a propósito: copiarlo al panel propio es rellenar el
/// formulario con estos datos, no escribirlos otra vez. Que dos representantes visiten
/// al mismo médico es normal —líneas distintas—, y hacer que el segundo reteclee
/// dirección, teléfono y exequátur es la forma más segura de que acaben distintos.
/// </summary>
public class MedicoExistente
{
    public int Id { get; set; }
    public string Nombre { get; set; } = "";
    public string? Especialidad { get; set; }
    public string? Centro { get; set; }
    public string? Telefono { get; set; }
    public string? Exequatur { get; set; }
    public string? Direccion { get; set; }
    public string? VisitadoPor { get; set; }

    public string Detalle => string.Join(" · ",
        new[] { Especialidad, Centro }.Where(s => !string.IsNullOrWhiteSpace(s))!);

    /// <summary>De quién es el panel donde ya está. Da contexto antes de copiarlo.</summary>
    public string Origen => string.IsNullOrWhiteSpace(VisitadoPor)
        ? "En otro panel" : $"En el panel de {VisitadoPor}";
}

/// <summary>Una farmacia encontrada en el maestro al buscar antes de dar de alta.</summary>
public class FarmaciaMaestro
{
    public int Id { get; set; }
    public string Nombre { get; set; } = "";
    public string? Direccion { get; set; }
    public string? Estado { get; set; }
}
