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
    public string? MensajeClave { get; set; }
    public int Prioridad { get; set; }

    /// <summary>Marcado por el visitador en esta visita. No se guarda en el catálogo.</summary>
    [Ignore] public bool Elegido { get => _elegido; set => SetProperty(ref _elegido, value); }
    private bool _elegido;

    public string Subtitulo => string.IsNullOrWhiteSpace(MensajeClave) ? " " : MensajeClave!;
}

/// <summary>Una farmacia del panel. Solo las aprobadas admiten registro (guarda F22).</summary>
[Table("farmacias")]
public class FarmaciaPanel
{
    [PrimaryKey] public int Id { get; set; }
    public string Nombre { get; set; } = "";
    public string? Direccion { get; set; }
    public string EstadoAprobacion { get; set; } = "APROBADO";
    public bool SePuedeVisitar => EstadoAprobacion == "APROBADO";
}

/// <summary>Un médico programado para hoy, con su estado.</summary>
[Table("agenda")]
public class ItemAgenda
{
    [PrimaryKey] public int MedicoId { get; set; }
    public string Nombre { get; set; } = "";
    public string TipoVisita { get; set; } = "V";
    public bool Registrada { get; set; }
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
