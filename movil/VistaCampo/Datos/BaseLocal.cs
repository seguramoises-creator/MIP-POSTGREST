using SQLite;
using VistaCampo.Modelos;

namespace VistaCampo.Datos;

/// <summary>
/// La base local del teléfono.
///
/// NO es una caché: mientras no hay red es la fuente de verdad de lo que el visitador
/// capturó. De ahí que la cola de envíos viva aquí y no en memoria — la app se cierra,
/// el teléfono se queda sin batería, y el trabajo de la mañana tiene que seguir estando.
///
/// Se abre una sola vez y de forma perezosa: abrirla en el constructor obligaría a que
/// cada pantalla espere al disco aunque no vaya a leer nada.
/// </summary>
public class BaseLocal
{
    private SQLiteAsyncConnection? _db;
    private readonly SemaphoreSlim _candado = new(1, 1);

    private async Task<SQLiteAsyncConnection> ConexionAsync()
    {
        if (_db is not null) return _db;
        await _candado.WaitAsync();
        try
        {
            if (_db is null)
            {
                var ruta = Path.Combine(FileSystem.AppDataDirectory, "vistacampo.db3");
                var db = new SQLiteAsyncConnection(ruta,
                    SQLiteOpenFlags.ReadWrite | SQLiteOpenFlags.Create | SQLiteOpenFlags.SharedCache);
                await db.CreateTableAsync<MedicoPanel>();
                await db.CreateTableAsync<FarmaciaPanel>();
                await db.CreateTableAsync<ItemAgenda>();
                await db.CreateTableAsync<ItemPlan>();
                await db.CreateTableAsync<EnvioPendiente>();
                _db = db;
            }
        }
        finally { _candado.Release(); }
        return _db!;
    }

    // ── Catálogos ────────────────────────────────────────────────────────────
    // Se reemplazan enteros al sincronizar: son un espejo del servidor, no algo que el
    // teléfono edite. Mezclar filas viejas con nuevas dejaría médicos dados de baja
    // visibles para siempre.

    public async Task ReemplazarMedicosAsync(IEnumerable<MedicoPanel> medicos)
    {
        var db = await ConexionAsync();
        await db.DeleteAllAsync<MedicoPanel>();
        await db.InsertAllAsync(medicos);
    }

    public async Task<List<MedicoPanel>> MedicosAsync()
        => await (await ConexionAsync()).Table<MedicoPanel>().OrderBy(m => m.Nombre).ToListAsync();

    public async Task ReemplazarFarmaciasAsync(IEnumerable<FarmaciaPanel> farmacias)
    {
        var db = await ConexionAsync();
        await db.DeleteAllAsync<FarmaciaPanel>();
        await db.InsertAllAsync(farmacias);
    }

    public async Task<List<FarmaciaPanel>> FarmaciasAsync()
        => await (await ConexionAsync()).Table<FarmaciaPanel>().OrderBy(f => f.Nombre).ToListAsync();

    public async Task ReemplazarAgendaAsync(IEnumerable<ItemAgenda> items)
    {
        var db = await ConexionAsync();
        await db.DeleteAllAsync<ItemAgenda>();
        await db.InsertAllAsync(items);
    }

    public async Task<List<ItemAgenda>> AgendaAsync()
        => await (await ConexionAsync()).Table<ItemAgenda>().ToListAsync();

    public async Task ReemplazarPlanAsync(IEnumerable<ItemPlan> items)
    {
        var db = await ConexionAsync();
        await db.DeleteAllAsync<ItemPlan>();
        await db.InsertAllAsync(items);
    }

    public async Task<List<ItemPlan>> PlanAsync()
        => await (await ConexionAsync()).Table<ItemPlan>().ToListAsync();

    /// <summary>¿Se han descargado alguna vez los catálogos? Distinto de «están vacíos».</summary>
    public async Task<bool> HayCatalogosAsync()
        => await (await ConexionAsync()).Table<MedicoPanel>().CountAsync() > 0;

    // ── Cola de salida ───────────────────────────────────────────────────────

    public async Task EncolarAsync(EnvioPendiente envio)
        => await (await ConexionAsync()).InsertAsync(envio);

    public async Task ActualizarAsync(EnvioPendiente envio)
        => await (await ConexionAsync()).UpdateAsync(envio);

    public async Task BorrarEnvioAsync(EnvioPendiente envio)
        => await (await ConexionAsync()).DeleteAsync(envio);

    /// <summary>Toda la cola, lo más viejo primero: el orden de captura es el orden de envío.</summary>
    public async Task<List<EnvioPendiente>> ColaAsync()
        => await (await ConexionAsync()).Table<EnvioPendiente>()
                 .OrderBy(e => e.CapturadoUtc).ToListAsync();

    /// <summary>Lo que falta por subir (pendiente o reintentando), en orden de captura.</summary>
    public async Task<List<EnvioPendiente>> PorEnviarAsync()
    {
        var db = await ConexionAsync();
        return await db.Table<EnvioPendiente>()
                       .Where(e => e.Estado == (int)EstadoEnvio.Pendiente
                                || e.Estado == (int)EstadoEnvio.Enviando)
                       .OrderBy(e => e.CapturadoUtc).ToListAsync();
    }

    public async Task<int> ContarAsync(EstadoEnvio estado)
    {
        var db = await ConexionAsync();
        var e = (int)estado;
        return await db.Table<EnvioPendiente>().Where(x => x.Estado == e).CountAsync();
    }

    /// <summary>
    /// Los envíos ya subidos se conservan un día y luego se limpian. Borrarlos al
    /// instante dejaría al visitador sin la prueba de que su trabajo entró, que es lo
    /// primero que va a querer ver cuando alguien le diga que no aparece.
    /// </summary>
    public async Task LimpiarEnviadosAsync()
    {
        var db = await ConexionAsync();
        var corte = DateTime.UtcNow.AddDays(-1);
        var viejos = await db.Table<EnvioPendiente>()
                             .Where(e => e.Estado == (int)EstadoEnvio.Enviado && e.CapturadoUtc < corte)
                             .ToListAsync();
        foreach (var v in viejos) await db.DeleteAsync(v);
    }
}
