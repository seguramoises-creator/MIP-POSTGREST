using System.Collections.ObjectModel;
using System.Text.Json;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using VistaCampo.Datos;
using VistaCampo.Modelos;
using VistaCampo.Servicios;

namespace VistaCampo.VistaModelos;

/// <summary>
/// Un médico del panel dentro de la planeación: en qué semana se le hace la Vista, qué
/// día, y si lleva Revisita.
/// </summary>
public partial class FilaPlan : ObservableObject
{
    public int MedicoId { get; init; }
    public string Nombre { get; init; } = "";
    public string? Categoria { get; init; }
    public string Subtitulo { get; init; } = "";
    public bool EsTop { get; init; }
    /// <summary>Planeado en el servidor sobre un médico que ya no está en el panel local.</summary>
    public bool FueraDePanel { get; init; }
    // La hora estimada y el día de la Revisita no se editan aquí, pero se CONSERVAN: guardar
    // reemplaza la planeación entera, y perderlos al guardar sería borrar lo que se puso en la web.
    public string? HoraV { get; set; }
    public string? HoraR { get; set; }
    public string? DiaR { get; set; }

    [ObservableProperty] private int _semanaV;
    [ObservableProperty] private string? _dia;
    [ObservableProperty] private bool _revisita;
    [ObservableProperty] private int _semanaR;
    [ObservableProperty] private bool _seleccionada;
    /// <summary>Enviada o aprobada: se ve en gris y solo se consulta.</summary>
    [ObservableProperty] private bool _bloqueada;

    public string TextoCategoria => string.IsNullOrWhiteSpace(Categoria) ? "?" : Categoria!;
    public bool Planeada => SemanaV > 0;
    /// <summary>La Revisita va dos semanas después de la Vista (1→3, 2→4), como en la web.</summary>
    public bool PuedeRevisita => SemanaV is 1 or 2;
    public bool V1 => SemanaV == 1;
    public bool V2 => SemanaV == 2;
    public bool V3 => SemanaV == 3;
    public bool V4 => SemanaV == 4;
    // La semana de la Revisita también se marca en los botones de semana (más clara que la
    // de la Vista): solo con el texto del botón de abajo, tocar la semana 4 no enseñaba nada.
    public bool R1 => Revisita && SemanaR == 1;
    public bool R2 => Revisita && SemanaR == 2;
    public bool R3 => Revisita && SemanaR == 3;
    public bool R4 => Revisita && SemanaR == 4;
    public string TextoVistaConsulta => SemanaV == 0 ? "Sin planear"
        : $"Semana {SemanaV}" + (string.IsNullOrEmpty(Dia) ? "" : $" · {Dia}");
    public string TextoRevisitaConsulta => !(Revisita && SemanaR > 0) ? "Sin revisita"
        : $"Semana {SemanaR}" + (string.IsNullOrEmpty(DiaR ?? Dia) ? "" : $" · {DiaR ?? Dia}");
    public bool DL => Dia == "Lunes";
    public bool DM => Dia == "Martes";
    public bool DX => Dia == "Miércoles";
    public bool DJ => Dia == "Jueves";
    public bool DV => Dia == "Viernes";
    public string TextoRevisita => Revisita ? $"🔁 Con revisita · semana {SemanaR}" : "🔁 Sin revisita";

    /// <summary>
    /// La combinación que el servidor rechaza (P02/P03). Solo puede venir de lo ya guardado
    /// —el editor pone la Revisita dos semanas después—, y por eso hay que SEÑALARLA: el
    /// servidor rechaza la planeación entera por una sola fila.
    /// </summary>
    public string? Problema => !(Planeada && Revisita && SemanaR > 0) ? null
        : SemanaR < SemanaV ? $"la revisita (semana {SemanaR}) va antes que la vista (semana {SemanaV})"
        : SemanaR == SemanaV && !string.IsNullOrEmpty(Dia) && (DiaR ?? Dia) == Dia
            ? $"la vista y la revisita caen el mismo día (semana {SemanaV}, {Dia})"
        : null;

    /// <summary>«Vista S1 · Lun · Revisita S3», o «Sin planear».</summary>
    public string Resumen => SemanaV == 0
        ? (EsTop ? "Sin planear · TOP: es obligatorio" : "Sin planear")
        : (Problema is null ? "" : "⚠ ")
          + $"Vista S{SemanaV}{(string.IsNullOrEmpty(Dia) ? "" : " · " + Dia[..3])}"
          + (Revisita ? $" · Revisita S{SemanaR}" : "")
          + (FueraDePanel ? " · ya no está en tu panel" : "");

    partial void OnSemanaVChanged(int value) => Refrescar();
    partial void OnDiaChanged(string? value) => Refrescar();
    partial void OnRevisitaChanged(bool value) => Refrescar();
    partial void OnSemanaRChanged(int value) => Refrescar();

    private void Refrescar()
    {
        foreach (var p in new[] { nameof(Planeada), nameof(PuedeRevisita), nameof(V1), nameof(V2),
                                  nameof(V3), nameof(V4), nameof(DL), nameof(DM), nameof(DX),
                                  nameof(DJ), nameof(DV), nameof(TextoRevisita), nameof(Problema),
                                  nameof(Resumen), nameof(R1), nameof(R2), nameof(R3), nameof(R4),
                                  nameof(TextoVistaConsulta), nameof(TextoRevisitaConsulta) })
            OnPropertyChanged(p);
    }
}

/// <summary>
/// La planeación del ciclo, hecha desde el teléfono: el representante elige para cada
/// médico de su panel la semana de la Vista (y el día, si quiere), marca la Revisita, la
/// guarda y la ENVÍA a su Gerente de Distrito, que la aprueba en la web.
///
/// Planear exige conexión, a diferencia de registrar una visita: la planeación se valida
/// contra el servidor (médicos TOP, ciclo abierto) y la decide otra persona. Guardarla solo
/// en el teléfono daría una planeación que nadie ve y que el gerente no puede aprobar. Sin
/// señal se enseña la última copia descargada, en solo lectura, y se dice por qué.
/// </summary>
public partial class PlanVista : BaseVista
{
    private readonly BaseLocal _base;
    private readonly ApiCliente _api;
    private List<FilaPlan> _todas = new();

    public PlanVista(BaseLocal baseLocal, ApiCliente api)
    {
        _base = baseLocal;
        _api = api;
    }

    public ObservableCollection<FilaPlan> Filas { get; } = new();

    [ObservableProperty] private FilaPlan? _seleccionada;
    [ObservableProperty] private string _estado = "BORRADOR";
    [ObservableProperty] private string? _motivoDevolucion;
    [ObservableProperty] private bool _enLinea;
    [ObservableProperty] private bool _hayCambios;
    [ObservableProperty] private string _filtro = "todos";
    [ObservableProperty] private string _busqueda = "";
    [ObservableProperty] private int _panel;
    [ObservableProperty] private int _medicosPlaneados;
    [ObservableProperty] private int _totalVistas;
    [ObservableProperty] private int _totalRevisitas;
    [ObservableProperty] private int _topSinPlanear;
    /// <summary>«📆 Ciclo 9 2026 · abierto · semana 2 de 4 · del 01/09 al 28/09».</summary>
    [ObservableProperty] private string? _cicloTexto;
    [ObservableProperty] private string? _publicadaEn;

    public bool HaySeleccion => Seleccionada is not null;
    public bool HayCiclo => !string.IsNullOrEmpty(CicloTexto);
    public bool Editable => EnLinea && Estado is "BORRADOR" or "DEVUELTA";
    public bool SoloConsulta => !Editable;
    public string TextoSoloConsulta => Estado switch
    {
        "PUBLICADA" => "🔒 Aprobada por tu gerente: solo consulta",
        "ENVIADA" => "🔒 En revisión de tu gerente: solo consulta",
        _ => "🔒 Solo consulta",
    };

    partial void OnCicloTextoChanged(string? value)
    {
        OnPropertyChanged(nameof(HayCiclo));
        OnPropertyChanged(nameof(Ciclo));
    }

    /// <summary>El ciclo, para la misma tarjeta que en Hoy.</summary>
    public InfoCiclo Ciclo => InfoCiclo.Leer();
    partial void OnPublicadaEnChanged(string? value) => OnPropertyChanged(nameof(EstadoTexto));

    /// <summary>La fecha llega en UTC sin huso: se pasa a la hora del teléfono.</summary>
    private string FechaAprobacion =>
        DateTime.TryParse(PublicadaEn, out var f)
            ? " el " + DateTime.SpecifyKind(f, DateTimeKind.Utc).ToLocalTime().ToString("dd/MM/yyyy")
            : "";
    public bool HayTopSinPlanear => TopSinPlanear > 0;
    public string TextoPlaneados => $"{MedicosPlaneados}/{Panel}";
    public string TextoTop => $"⭐ {TopSinPlanear} médico(s) TOP sin planear: tu gerente no podrá aprobarla sin ellos.";
    public bool FiltroTodos => Filtro == "todos";
    public bool FiltroSin => Filtro == "sin";
    public bool FiltroPlaneados => Filtro == "planeados";

    public string EstadoTexto => Estado switch
    {
        "ENVIADA" => "⏳ Enviada a tu gerente",
        "PUBLICADA" => $"✅ Aprobada por tu gerente{FechaAprobacion}",
        "DEVUELTA" => "↩️ Devuelta por tu gerente",
        _ => "📝 Planeación en borrador",
    };

    public string EstadoDetalle => !EnLinea
        ? "Sin conexión: ves la última copia descargada. Para planear y enviarla necesitas señal."
        : Estado switch
        {
            "ENVIADA" => "Está en revisión: no se puede cambiar hasta que la apruebe o te la devuelva.",
            "PUBLICADA" => "Es tu planeación del ciclo y ya no se modifica. Si hay un error, lo corrige un administrador.",
            "DEVUELTA" => string.IsNullOrWhiteSpace(MotivoDevolucion)
                ? "Corrígela y vuelve a enviarla."
                : $"«{MotivoDevolucion}» — corrígela y vuelve a enviarla.",
            _ => "Toca un médico y elige su semana. Al terminar, envíala a tu gerente para que la apruebe.",
        };

    public Color ColorEstado => Estado switch
    {
        "ENVIADA" => Color.FromArgb("#E3EEFF"),
        // Gris: planeada y validada por el gerente, ya no es terreno de edición.
        "PUBLICADA" => Color.FromArgb("#E6E9EE"),
        "DEVUELTA" => Color.FromArgb("#FFF1DE"),
        _ => Color.FromArgb("#FFFFFF"),
    };

    partial void OnEstadoChanged(string value)
    {
        NotificarEstado();
        AplicarBloqueo();
    }

    private void AplicarBloqueo()
    {
        var b = Estado is "ENVIADA" or "PUBLICADA";
        foreach (var f in _todas) f.Bloqueada = b;
    }
    partial void OnEnLineaChanged(bool value) => NotificarEstado();
    partial void OnMotivoDevolucionChanged(string? value) => NotificarEstado();
    partial void OnBusquedaChanged(string value) => Filtrar();
    partial void OnPanelChanged(int value) => OnPropertyChanged(nameof(TextoPlaneados));
    partial void OnMedicosPlaneadosChanged(int value) => OnPropertyChanged(nameof(TextoPlaneados));

    partial void OnTopSinPlanearChanged(int value)
    {
        OnPropertyChanged(nameof(HayTopSinPlanear));
        OnPropertyChanged(nameof(TextoTop));
    }

    partial void OnFiltroChanged(string value)
    {
        OnPropertyChanged(nameof(FiltroTodos));
        OnPropertyChanged(nameof(FiltroSin));
        OnPropertyChanged(nameof(FiltroPlaneados));
        Filtrar();
    }

    partial void OnSeleccionadaChanged(FilaPlan? oldValue, FilaPlan? newValue)
    {
        if (oldValue is not null) oldValue.Seleccionada = false;
        if (newValue is not null) newValue.Seleccionada = true;
        OnPropertyChanged(nameof(HaySeleccion));
    }

    private void NotificarEstado()
    {
        foreach (var p in new[] { nameof(Editable), nameof(SoloConsulta), nameof(TextoSoloConsulta),
                                  nameof(EstadoTexto), nameof(EstadoDetalle), nameof(ColorEstado) })
            OnPropertyChanged(p);
    }

    /// <summary>
    /// Al volver a la pestaña NO se recarga si hay cambios sin guardar: cambiar de pestaña
    /// para mirar la agenda no puede borrar veinte médicos recién planeados.
    /// </summary>
    public async Task AlAparecerAsync()
    {
        if (!HayCambios) await CargarAsync();
    }

    [RelayCommand]
    public async Task CargarAsync()
    {
        await EjecutarAsync(async () =>
        {
            Aviso = null;
            var panel = (await _base.MedicosAsync()).Where(m => m.SePuedeVisitar).ToList();
            List<ItemPlan> items;
            EnLinea = false;
            if (ServicioSincronizacion.HayRed)
            {
                try
                {
                    var estado = await _api.ObtenerAsync<JsonElement>("/visita/planeacion/estado");
                    var plan = await _api.ObtenerAsync<List<JsonElement>>("/visita/planeacion");
                    Estado = Texto(estado, "estado") ?? "BORRADOR";
                    MotivoDevolucion = Texto(estado, "motivo_devolucion");
                    PublicadaEn = Texto(estado, "publicada_en");
                    CicloTexto = ServicioSincronizacion.GuardarCiclo(estado) ?? CicloTexto;
                    var nombres = panel.ToDictionary(m => m.Id, m => m.Nombre);
                    items = plan.Select(p =>
                    {
                        var id = Entero(p, "medico_id");
                        return new ItemPlan
                        {
                            MedicoId = id,
                            Medico = nombres.TryGetValue(id, out var n) ? n : "(no está en tu panel)",
                            TipoVisita = Texto(p, "tipo_visita") ?? "V",
                            Semana = Entero(p, "semana"),
                            Dia = Texto(p, "dia_semana"),
                            Hora = Texto(p, "hora_estimada"),
                        };
                    }).ToList();
                    // La copia sin conexión queda igual a lo que dice el servidor.
                    await _base.ReemplazarPlanAsync(items);
                    EnLinea = true;
                }
                catch (ErrorApi e)
                {
                    Aviso = e.Message;
                    items = await _base.PlanAsync();
                }
            }
            else
            {
                items = await _base.PlanAsync();
            }

            // Sin red, el ciclo que se guardó la última vez: mejor eso que no decir cuál es.
            CicloTexto ??= Preferences.Get("ciclo_texto", null as string);

            var porMedico = items.GroupBy(i => i.MedicoId).ToDictionary(g => g.Key, g => g.ToList());
            _todas = panel.Select(m => Construir(m.Id, m.Nombre, m.Categoria, m.Subtitulo, m.EsTop, false, porMedico))
                          .ToList();
            // Lo planeado sobre médicos que ya no están en el panel local también se conserva:
            // guardar reemplaza la planeación ENTERA en el servidor.
            foreach (var id in porMedico.Keys.Except(panel.Select(m => m.Id)))
                _todas.Add(Construir(id, porMedico[id][0].Medico, null, "", false, true, porMedico));
            _todas = _todas.OrderBy(f => f.Nombre).ToList();
            AplicarBloqueo();

            Seleccionada = null;
            HayCambios = false;
            Recontar();
            Filtrar();
            OnPropertyChanged(nameof(Ciclo));
        });
    }

    private static FilaPlan Construir(int id, string nombre, string? categoria, string subtitulo, bool top,
                                      bool fuera, Dictionary<int, List<ItemPlan>> porMedico)
    {
        var f = new FilaPlan
        {
            MedicoId = id, Nombre = nombre, Categoria = categoria, Subtitulo = subtitulo,
            EsTop = top, FueraDePanel = fuera,
        };
        if (!porMedico.TryGetValue(id, out var suyos)) return f;
        var v = suyos.FirstOrDefault(i => i.TipoVisita == "V");
        var r = suyos.FirstOrDefault(i => i.TipoVisita == "R");
        if (v is not null)
        {
            f.SemanaV = v.Semana;
            f.Dia = v.Dia;
            f.HoraV = v.Hora;
        }
        if (r is not null)
        {
            f.Revisita = true;
            f.SemanaR = r.Semana;
            f.DiaR = r.Dia;
            f.HoraR = r.Hora;
        }
        return f;
    }

    private void Recontar()
    {
        Panel = _todas.Count(f => !f.FueraDePanel);
        MedicosPlaneados = _todas.Count(f => f.Planeada && !f.FueraDePanel);
        TotalVistas = _todas.Count(f => f.Planeada);
        TotalRevisitas = _todas.Count(f => f.Planeada && f.Revisita);
        TopSinPlanear = _todas.Count(f => f.EsTop && !f.Planeada);
    }

    private void Filtrar()
    {
        var q = (Busqueda ?? "").Trim().ToUpperInvariant();
        Filas.Clear();
        foreach (var f in _todas)
        {
            if (Filtro == "sin" && f.Planeada) continue;
            if (Filtro == "planeados" && !f.Planeada) continue;
            if (q.Length > 0 && !f.Nombre.ToUpperInvariant().Contains(q)) continue;
            Filas.Add(f);
        }
    }

    // ── Edición ─────────────────────────────────────────────────────────────

    [RelayCommand]
    private void Seleccionar(FilaPlan fila) => Seleccionada = ReferenceEquals(Seleccionada, fila) ? null : fila;

    [RelayCommand]
    private void CerrarEditor() => Seleccionada = null;

    [RelayCommand]
    private void ElegirFiltro(string filtro) => Filtro = filtro;

    /// <summary>
    /// Bloqueada, el médico se abre en modo consulta (la ficha gris ya dice por qué): antes
    /// cada toque repetía el mensaje del estado en el aviso y la tarjeta lo decía dos veces.
    /// </summary>
    private FilaPlan? EditandoA() => Seleccionada is not null && Editable ? Seleccionada : null;

    /// <summary>Tocar la semana que ya tenía la quita: así se deja a un médico sin planear.</summary>
    [RelayCommand]
    private void ElegirSemana(string semana)
    {
        var f = EditandoA();
        if (f is null) return;
        var s = int.Parse(semana);
        if (f.SemanaV == s)
        {
            f.SemanaV = 0;
            f.Dia = null;
            f.Revisita = false;
            f.SemanaR = 0;
            f.DiaR = null;
        }
        else
        {
            f.SemanaV = s;
            if (f.Revisita && f.PuedeRevisita) f.SemanaR = s + 2;
            else if (f.Revisita) { f.Revisita = false; f.SemanaR = 0; f.DiaR = null; }
        }
        Cambio();
    }

    [RelayCommand]
    private void AlternarRevisita()
    {
        var f = EditandoA();
        if (f is null) return;
        if (!f.Revisita && !f.PuedeRevisita)
        {
            Aviso = f.SemanaV == 0
                ? "Primero elige la semana de la vista."
                : "La revisita va dos semanas después de la vista: se puede con la vista en la semana 1 o 2.";
            return;
        }
        f.Revisita = !f.Revisita;
        f.SemanaR = f.Revisita ? f.SemanaV + 2 : 0;
        f.DiaR = f.Revisita ? f.Dia : null;
        Cambio();
    }

    /// <summary>El día es opcional. La Revisita cae el mismo día de la semana que la Vista.</summary>
    [RelayCommand]
    private void ElegirDia(string dia)
    {
        var f = EditandoA();
        if (f is null) return;
        if (f.SemanaV == 0)
        {
            Aviso = "Primero elige la semana de la vista.";
            return;
        }
        f.Dia = f.Dia == dia ? null : dia;
        if (f.Revisita) f.DiaR = f.Dia;
        Cambio();
    }

    private void Cambio()
    {
        HayCambios = true;
        Aviso = null;
        Error = null;
        Recontar();
    }

    // ── Guardar y enviar ────────────────────────────────────────────────────

    private List<object> ItemsParaServidor() => _todas.Where(f => f.Planeada).SelectMany(f =>
    {
        var l = new List<object>
        {
            new { medico_id = f.MedicoId, tipo_visita = "V", semana = f.SemanaV,
                  dia_semana = f.Dia, hora_estimada = f.HoraV },
        };
        if (f.Revisita && f.SemanaR > 0)
            l.Add(new { medico_id = f.MedicoId, tipo_visita = "R", semana = f.SemanaR,
                        dia_semana = f.DiaR ?? f.Dia, hora_estimada = f.HoraR });
        return l;
    }).ToList();

    private async Task GuardarEnServidorAsync()
    {
        // Se comprueba ANTES de mandar y se dice QUIÉN: el servidor rechaza la planeación
        // entera por una fila, y su mensaje no dice en qué parte de 200 médicos está.
        var problemas = _todas.Where(f => f.Problema is not null)
                              .Select(f => $"{f.Nombre}: {f.Problema}.").ToList();
        if (problemas.Count > 0)
        {
            Filtro = "planeados";
            throw new ErrorApi(string.Join("\n", problemas.Take(3))
                + (problemas.Count > 3 ? $"\n…y {problemas.Count - 3} más (marcados con ⚠)." : "")
                + "\nToca el médico y vuelve a marcar su revisita.");
        }
        await _api.EnviarJsonAsync<JsonElement>("/visita/planeacion", new { items = ItemsParaServidor() });
        HayCambios = false;
        await _base.ReemplazarPlanAsync(_todas.Where(f => f.Planeada).SelectMany(f =>
        {
            var l = new List<ItemPlan>
            {
                new() { MedicoId = f.MedicoId, Medico = f.Nombre, TipoVisita = "V",
                        Semana = f.SemanaV, Dia = f.Dia, Hora = f.HoraV },
            };
            if (f.Revisita && f.SemanaR > 0)
                l.Add(new() { MedicoId = f.MedicoId, Medico = f.Nombre, TipoVisita = "R",
                              Semana = f.SemanaR, Dia = f.DiaR ?? f.Dia, Hora = f.HoraR });
            return l;
        }));
    }

    [RelayCommand]
    private async Task GuardarAsync()
    {
        if (!Editable) { Aviso = EstadoDetalle; return; }
        await EjecutarAsync(async () =>
        {
            await GuardarEnServidorAsync();
            Aviso = $"💾 Guardada: {TotalVistas} vistas y {TotalRevisitas} revisitas. Aún no se ha enviado.";
        });
    }

    [RelayCommand]
    private async Task EnviarAsync()
    {
        if (!Editable) { Aviso = EstadoDetalle; return; }
        if (MedicosPlaneados == 0)
        {
            Error = "Planea al menos un médico antes de enviarla.";
            return;
        }
        var ok = await Shell.Current.DisplayAlertAsync(
            "Enviar a tu gerente",
            $"Se enviarán {TotalVistas} vistas y {TotalRevisitas} revisitas ({MedicosPlaneados} de {Panel} médicos). "
            + "Mientras tu gerente la revisa no podrás cambiarla.",
            "Enviar", "Cancelar");
        if (!ok) return;
        await EjecutarAsync(async () =>
        {
            // Primero se guarda lo que se ve: enviar sin guardar mandaría la última versión
            // guardada, no la que el representante tiene delante.
            await GuardarEnServidorAsync();
            await _api.EnviarJsonAsync<JsonElement>("/visita/planeacion/enviar", new { });
            Estado = "ENVIADA";
            MotivoDevolucion = null;
            Seleccionada = null;
            Aviso = "📤 Enviada a tu Gerente de Distrito. Si hay algo que corregir, te la devolverá.";
        });
    }

    private static string? Texto(JsonElement e, string clave) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(clave, out var v)
        && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    private static int Entero(JsonElement e, string clave) =>
        e.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetInt32() : 0;
}
