using CommunityToolkit.Mvvm.ComponentModel;
using SQLite;

namespace VistaCampo.Modelos;

/// <summary>
/// Configuración de la instalación contra la que corre esta app.
///
/// La misma app sirve a VISTA y a Laboratorios Mallén: lo que las distingue es esto,
/// leído del servidor al arrancar. En particular <see cref="ModoIngesta"/> decide si la
/// app puede CAPTURAR o es un visor de consulta — donde los datos llegan de un SFA
/// externo, registrar aquí duplicaría el hecho.
/// </summary>
public class ConfigInstalacion
{
    public string ModoIngesta { get; set; } = "excel";
    public bool MonitorDia { get; set; }

    /// <summary>¿Puede el visitador registrar su trabajo en esta instalación?</summary>
    public bool PuedeCapturar => !string.Equals(ModoIngesta?.Trim(), "integracion",
                                                StringComparison.OrdinalIgnoreCase);
}

/// <summary>Los dos colores editables de la identidad, tal como los sirve el servidor.</summary>
public class MarcaRemota
{
    public string? Rojo { get; set; }
    public string? Taupe { get; set; }
    public string? Logo { get; set; }
}

/// <summary>Lo que devuelve el login.</summary>
public class RespuestaLogin
{
    public string AccessToken { get; set; } = "";
    public string RefreshToken { get; set; } = "";
    public bool DebeCambiarPassword { get; set; }
}

/// <summary>Un médico del panel del visitador, guardado en el teléfono.</summary>
[Table("medicos")]
public class MedicoPanel
{
    [PrimaryKey] public int Id { get; set; }
    public string Nombre { get; set; } = "";
    public string? Especialidad { get; set; }
    public string? Centro { get; set; }
    public string? Categoria { get; set; }
    /// <summary>APROBADO | PENDIENTE_ALTA | RECHAZADO. Solo un aprobado admite visita.</summary>
    public string EstadoAprobacion { get; set; } = "APROBADO";
    public bool Activo { get; set; } = true;

    public bool SePuedeVisitar => Activo && EstadoAprobacion == "APROBADO";
    public string Subtitulo => string.Join(" · ",
        new[] { Especialidad, Centro }.Where(s => !string.IsNullOrWhiteSpace(s))!);
}

/// <summary>
/// Un producto de la parrilla del ciclo — lo que el visitador puede promocionar.
///
/// Se descarga con el resto de los catálogos para que esté disponible sin conexión: si
/// el producto solo se pudiera elegir con red, la visita registrada en un sótano
/// quedaría sin él, y el producto mencionado es la mitad del valor del registro.
/// </summary>
[Table("productos")]
public partial class ProductoParrilla : ObservableObject
{
    [PrimaryKey] public int Id { get; set; }
    public string Nombre { get; set; } = "";
    /// <summary>El código con el que el servidor identifica el producto al registrar.</summary>
    public string Codigo { get; set; } = "";
    public string? MensajeClave { get; set; }
    public int Prioridad { get; set; }
    /// <summary>Muestras que la parrilla PROPONE para este producto por visita.</summary>
    public int MetaMuestras { get; set; }

    /// <summary>Marcado por el visitador en esta visita. No se guarda en el catálogo.</summary>
    [Ignore] public bool Elegido
    {
        get => _elegido;
        set { if (SetProperty(ref _elegido, value)) OnPropertyChanged(nameof(Editable)); }
    }
    private bool _elegido;

    /// <summary>
    /// Muestras entregadas de ESTE producto en ESTA visita. Arranca en lo propuesto por
    /// la parrilla, que es lo que el visitador lleva encima; se corrige si entregó otra
    /// cosa. Proponer 0 obligaría a teclear en la calle el caso normal.
    /// </summary>
    [Ignore] public int Muestras { get => _muestras; set => SetProperty(ref _muestras, value); }
    private int _muestras;

    /// <summary>1ª, 2ª o 3ª mención — el orden con que se habló del producto.</summary>
    [Ignore] public int Mencion { get => _mencion; set => SetProperty(ref _mencion, value); }
    private int _mencion = 1;

    /// <summary>Los campos de muestras y mención solo se tocan si el producto está marcado.</summary>
    [Ignore] public bool Editable => _elegido;

    [Ignore] public string TextoMencion => $"{Mencion}ª mención";

    /// <summary>
    /// La posición en el desplegable. El desplegable enseña «1ª mención», no «1»: un
    /// número suelto al lado de otro número (las muestras) no dice cuál es cuál.
    /// </summary>
    [Ignore] public int MencionIndice
    {
        get => Math.Clamp(Mencion, 1, 3) - 1;
        set { Mencion = Math.Clamp(value, 0, 2) + 1; OnPropertyChanged(nameof(TextoMencion)); }
    }

    /// <summary>Lo que la parrilla propone, dicho como en la suite: «Propuesto: 3 muestras · 1ª mención».</summary>
    [Ignore] public string Propuesto =>
        $"Propuesto: {MetaMuestras} muestra{(MetaMuestras == 1 ? "" : "s")} · {Prioridad}ª mención";

    public string Subtitulo => string.IsNullOrWhiteSpace(MensajeClave) ? " " : MensajeClave!;

    /// <summary>Deja el producto como lo propone la parrilla, sin marcar.</summary>
    public void Reiniciar()
    {
        Elegido = false;
        Muestras = MetaMuestras;
        Mencion = Math.Clamp(Prioridad <= 0 ? 1 : Prioridad, 1, 3);
        OnPropertyChanged(nameof(TextoMencion));
    }
}

/// <summary>
/// Una farmacia del panel, con lo mismo que enseña la suite: cadena o independiente,
/// dirección, encargado y el comentario de la visita anterior.
///
/// El encargado y el último comentario no son adorno: son lo que le permite al visitador
/// retomar la conversación donde la dejó («no hay producto de la línea gastro») en vez de
/// entrar en frío. Solo las aprobadas admiten registro (guarda F22).
/// </summary>
[Table("farmacias")]
public partial class FarmaciaPanel : ObservableObject
{
    [PrimaryKey] public int Id { get; set; }
    public string Nombre { get; set; } = "";
    public string? Direccion { get; set; }
    public string? Encargado { get; set; }
    public bool EsCadena { get; set; }
    public string? UltimoComentario { get; set; }
    public bool VisitadaHoy { get; set; }
    public bool VisitadaCiclo { get; set; }
    public string EstadoAprobacion { get; set; } = "APROBADO";

    public bool SePuedeVisitar => EstadoAprobacion == "APROBADO";

    [Ignore] public string Badge => EsCadena ? "Cadena" : "Independiente";
    [Ignore] public string TextoEstado => VisitadaHoy ? "Visitada hoy" : VisitadaCiclo ? "Visitada" : "Pendiente";
    [Ignore] public bool EsPendiente => !VisitadaHoy && !VisitadaCiclo;

    /// <summary>El comentario anterior, entrecomillado; vacío si no hay.</summary>
    [Ignore] public string ComentarioAnterior =>
        string.IsNullOrWhiteSpace(UltimoComentario) ? "" : $"“{UltimoComentario!.Trim()}”";
    [Ignore] public bool HayComentarioAnterior => !string.IsNullOrWhiteSpace(UltimoComentario);

    /// <summary>Lo que se lee en el encabezado del formulario: dirección y quién atiende.</summary>
    [Ignore] public string Detalle => string.Join(" · ", new[]
    {
        Direccion, string.IsNullOrWhiteSpace(Encargado) ? null : $"Encargado: {Encargado}",
    }.Where(s => !string.IsNullOrWhiteSpace(s))!);

    [Ignore] public string Inicial
    {
        get
        {
            var p = Nombre.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries);
            var a = p.Length > 0 && p[0].Length > 0 ? p[0][0].ToString() : "";
            var b = p.Length > 1 && p[1].Length > 0 ? p[1][0].ToString() : "";
            return (a + b).ToUpperInvariant();
        }
    }

    /// <summary>
    /// Esta fila es la que está abierta. El formulario se despliega DENTRO de la fila,
    /// como en la suite: el visitador no pierde de vista a quién está registrando ni
    /// tiene que buscar el formulario en otro sitio de la pantalla.
    /// </summary>
    [Ignore] public bool Activa { get => _activa; set => SetProperty(ref _activa, value); }
    private bool _activa;
}

/// <summary>
/// Un médico de la agenda del ciclo, con TODO lo que el visitador necesita para
/// reconocerlo sin abrir nada más: especialidad, centro, categoría, qué le toca y cuándo.
///
/// Antes esta tabla guardaba cuatro campos y la pantalla enseñaba una lista de nombres.
/// El servidor ya mandaba el resto —`/visita/agenda-hoy` trae especialidad, categoría,
/// centro, provincia, día y hora—: se estaba tirando por el camino.
/// </summary>
[Table("agenda")]
public partial class ItemAgenda : ObservableObject
{
    [PrimaryKey] public int MedicoId { get; set; }
    public string Nombre { get; set; } = "";
    public string TipoVisita { get; set; } = "V";
    public bool Registrada { get; set; }

    public string? Especialidad { get; set; }
    public string? Centro { get; set; }
    public string? Provincia { get; set; }
    public string? Categoria { get; set; }
    public string? DiaSemana { get; set; }
    public string? HoraEstimada { get; set; }
    /// <summary>«dia» = le toca hoy; «ciclo» = planeado en el ciclo, para otro día.</summary>
    public string Grupo { get; set; } = "ciclo";
    /// <summary>Se registró como NO visitado, con su causa. No es lo mismo que hecho.</summary>
    public bool NoVisita { get; set; }

    /// <summary>Lo que se lee bajo el nombre en la lista: igual que la suite.</summary>
    [Ignore] public string Subtitulo => string.Join(" · ", new[]
    {
        Especialidad, TipoVisita == "R" ? "Revisita" : "Vista", DiaSemana, HoraEstimada,
    }.Where(s => !string.IsNullOrWhiteSpace(s))!);

    /// <summary>Lo que se lee bajo el nombre en el encabezado del formulario.</summary>
    [Ignore] public string Detalle
    {
        get
        {
            var t = string.Join(" · ", new[] { Especialidad, Centro, Provincia }
                .Where(s => !string.IsNullOrWhiteSpace(s))!);
            return string.IsNullOrWhiteSpace(t) ? "Sin datos" : t;
        }
    }

    [Ignore] public string TextoEstado =>
        !Registrada ? "Pendiente" : NoVisita ? "No visitado" : "Registrada ✓";

    [Ignore] public string Inicial
    {
        get
        {
            var p = Nombre.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries);
            var a = p.Length > 0 && p[0].Length > 0 ? p[0][0].ToString() : "";
            var b = p.Length > 1 && p[1].Length > 0 ? p[1][0].ToString() : "";
            return (a + b).ToUpperInvariant();
        }
    }

    [Ignore] public string TextoCategoria => string.IsNullOrWhiteSpace(Categoria) ? "?" : Categoria!;
    [Ignore] public bool EsPendiente => !Registrada;

    /// <summary>
    /// Esta fila es la que está abierta. El formulario se despliega DENTRO de la fila,
    /// como en la suite: el visitador no pierde de vista a quién está registrando ni
    /// tiene que buscar el formulario en otro sitio de la pantalla.
    /// </summary>
    [Ignore] public bool Activa { get => _activa; set => SetProperty(ref _activa, value); }
    private bool _activa;
}

/// <summary>Una línea de la planeación del ciclo.</summary>
[Table("plan")]
public class ItemPlan
{
    [PrimaryKey, AutoIncrement] public int Id { get; set; }
    public int MedicoId { get; set; }
    public string Medico { get; set; } = "";
    public string TipoVisita { get; set; } = "V";   // V | R
    public int Semana { get; set; }
    public string? Dia { get; set; }
    public string? Hora { get; set; }

    /// <summary>«Vista · Lunes · 08:00» — lo mismo que se lee en la agenda.</summary>
    [Ignore] public string Subtitulo => string.Join(" · ", new[]
    {
        TipoVisita == "R" ? "Revisita" : "Vista", Dia, Hora,
    }.Where(s => !string.IsNullOrWhiteSpace(s))!);
}

/// <summary>Estado de un envío en la cola.</summary>
public enum EstadoEnvio { Pendiente = 0, Enviando = 1, Enviado = 2, Rechazado = 3 }

/// <summary>
/// Una captura hecha en el teléfono, esperando su turno para subir.
///
/// La app SIEMPRE escribe aquí primero y confirma contra esta escritura, no contra la
/// red: el visitador termina la visita en el parqueo del edificio médico, donde no hay
/// señal, y necesita ver que su trabajo quedó guardado.
/// </summary>
[Table("cola")]
public class EnvioPendiente
{
    [PrimaryKey, AutoIncrement] public int Id { get; set; }

    /// <summary>La huella que viaja al servidor para que un reintento no duplique.</summary>
    [Indexed] public string UuidCliente { get; set; } = Guid.NewGuid().ToString();

    /// <summary>visita | no-visita | farmacia | foto</summary>
    public string Tipo { get; set; } = "visita";

    /// <summary>Cuerpo JSON tal como se mandará. Se arma al capturar, no al enviar.</summary>
    public string Cuerpo { get; set; } = "{}";

    /// <summary>Para las fotos: ruta del archivo local y la captura a la que pertenece.</summary>
    public string? RutaArchivo { get; set; }
    public int? VisitaServidorId { get; set; }
    public int? PanelId { get; set; }

    /// <summary>Nombre legible, para que la cola no sea una lista de números.</summary>
    public string Etiqueta { get; set; } = "";

    public DateTime CapturadoUtc { get; set; } = DateTime.UtcNow;
    public int Estado { get; set; } = (int)EstadoEnvio.Pendiente;
    public int Intentos { get; set; }
    public string? Motivo { get; set; }

    /// <summary>
    /// Minutos transcurridos desde la captura. La app los manda como `hace_minutos`, y
    /// el servidor los resta a SU reloj — nunca se manda una hora del teléfono, que se
    /// puede cambiar a mano.
    /// </summary>
    public int MinutosDesdeCaptura => (int)Math.Max(0, (DateTime.UtcNow - CapturadoUtc).TotalMinutes);

    /// <summary>
    /// La ventana del servidor es de 60 minutos: pasados esos, la visita YA NO se puede
    /// registrar. Por eso la cola avisa antes de que sea tarde en vez de descubrirlo con
    /// un rechazo.
    /// </summary>
    public bool PorVencer => Estado == (int)EstadoEnvio.Pendiente && MinutosDesdeCaptura >= 45;
    public bool Vencido => Estado == (int)EstadoEnvio.Pendiente && MinutosDesdeCaptura > 60;
}

/// <summary>Una visita ya registrada, para el feed del día.</summary>
public class VisitaDelDia
{
    public int Id { get; set; }
    public string Medico { get; set; } = "";
    public string Tipo { get; set; } = "V";
    public string Hora { get; set; } = "";
    public bool Ejecutada { get; set; } = true;
}
