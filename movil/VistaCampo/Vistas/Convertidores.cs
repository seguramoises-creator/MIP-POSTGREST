using System.Globalization;

namespace VistaCampo.Vistas;

/// <summary>Invierte un booleano. Lo usa media interfaz: «visible si NO hay error», etc.</summary>
public class Negar : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is bool b && !b;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is bool b && !b;
}

/// <summary>«V» / «R» a la palabra que el visitador reconoce.</summary>
public class TipoVisitaATexto : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => (value as string) == "R" ? "Revisita" : "Vista";

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>
/// El estado de un envío, dicho como lo entiende una persona.
///
/// «Sin enviar» y no «error»: mientras no haya red no ha fallado nada. Y «No entró» para
/// un rechazo, que es lo que de verdad ocurrió — el trabajo existe en el teléfono pero no
/// llegó al sistema.
/// </summary>
public class EstadoATexto : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is int n
            ? n switch { 0 => "Sin enviar", 1 => "Enviando…", 2 => "Enviado", _ => "No entró" }
            : "";

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>Color del estado de un envío.</summary>
public class EstadoAColor : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is int n
            ? n switch
            {
                2 => Color.FromArgb("#1B7F3B"),
                3 => Color.FromArgb("#B3261E"),
                _ => Color.FromArgb("#B25E00"),
            }
            : Colors.Gray;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>
/// Verdadero cuando una lista está vacía, para poder decir «no hay nada» con palabras.
///
/// Existe porque una lista vacía sin mensaje se lee como un fallo de carga, y el
/// visitador no tiene forma de distinguir «hoy no tienes agenda» de «no cargó».
/// </summary>
public class ListaVacia : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is int n && n == 0;

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>
/// Pinta de color la opción elegida en un par de botones (Vista/Revisita,
/// Médico/Farmacia).
///
/// Se marca con FONDO y no solo con un borde porque al sol un borde de un punto
/// desaparece, y el visitador necesita ver de un vistazo qué tiene seleccionado antes
/// de guardar.
/// </summary>
public class ColorSeleccion : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var activo = value is bool b && b;
        var modo = parameter as string;
        if (modo == "inverso") activo = !activo;
        // La FILA abierta se marca en ámbar, como en la suite, y no en el azul de un
        // botón elegido: son dos cosas distintas —«esto es lo que estoy registrando»
        // frente a «este botón está pulsado»— y pintarlas igual las confunde.
        if (modo == "fila")
            return activo ? Color.FromArgb("#FFF3D6") : Colors.Transparent;
        return activo ? Color.FromArgb("#D6E4FA") : Color.FromArgb("#FFFFFF");
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}

/// <summary>Verdadero si el texto no está vacío — para mostrar u ocultar una línea.</summary>
public class HayTexto : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => !string.IsNullOrWhiteSpace(value as string);

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
