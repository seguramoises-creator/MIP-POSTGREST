"""Seed de las 32 provincias de República Dominicana y sus municipios.

Idempotente y defensivo:
- Busca el país por nombre (LIKE '%ominic%') para obtener su `codigo` real
  (en esta BD es "RD"); si no existe, no hace nada (no rompe la migración).
- Inserta cada provincia/municipio solo si no existe ya (por sus claves únicas),
  así puede re-ejecutarse y correr sobre datos previos sin duplicar.

Portable PG / SQL Server: usa SELECT/INSERT con parámetros nombrados, sin
sintaxis específica de motor.

Revision ID: 0004_seed_provincias_rd
Revises: c5a7881c944b
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_seed_provincias_rd"
down_revision = "c5a7881c944b"
branch_labels = None
depends_on = None


# (provincia, [municipios]) — división oficial de RD (32 provincias, 158 municipios).
DATA: list[tuple[str, list[str]]] = [
    ("Distrito Nacional", ["Santo Domingo de Guzmán"]),
    ("Azua", ["Azua de Compostela", "Estebanía", "Guayabal", "Las Charcas",
              "Las Yayas de Viajama", "Padre Las Casas", "Peralta", "Pueblo Viejo",
              "Sabana Yegua", "Tábara Arriba"]),
    ("Baoruco", ["Neiba", "Galván", "Los Ríos", "Tamayo", "Villa Jaragua"]),
    ("Barahona", ["Santa Cruz de Barahona", "Cabral", "El Peñón", "Enriquillo",
                  "Fundación", "Jaquimeyes", "La Ciénaga", "Las Salinas", "Paraíso",
                  "Polo", "Vicente Noble"]),
    ("Dajabón", ["Dajabón", "El Pino", "Loma de Cabrera", "Partido", "Restauración"]),
    ("Duarte", ["San Francisco de Macorís", "Arenoso", "Castillo",
                "Eugenio María de Hostos", "Las Guáranas", "Pimentel", "Villa Riva"]),
    ("Elías Piña", ["Comendador", "Bánica", "El Llano", "Hondo Valle",
                    "Juan Santiago", "Pedro Santana"]),
    ("El Seibo", ["Santa Cruz de El Seibo", "Miches"]),
    ("Espaillat", ["Moca", "Cayetano Germosén", "Gaspar Hernández", "Jamao al Norte"]),
    ("Hato Mayor", ["Hato Mayor del Rey", "El Valle", "Sabana de la Mar"]),
    ("Hermanas Mirabal", ["Salcedo", "Tenares", "Villa Tapia"]),
    ("Independencia", ["Jimaní", "Cristóbal", "Duvergé", "La Descubierta", "Mella",
                       "Postrer Río"]),
    ("La Altagracia", ["Salvaleón de Higüey", "San Rafael del Yuma"]),
    ("La Romana", ["La Romana", "Guaymate", "Villa Hermosa"]),
    ("La Vega", ["Concepción de La Vega", "Constanza", "Jarabacoa", "Jima Abajo"]),
    ("María Trinidad Sánchez", ["Nagua", "Cabrera", "El Factor", "Río San Juan"]),
    ("Monseñor Nouel", ["Bonao", "Maimón", "Piedra Blanca"]),
    ("Monte Cristi", ["San Fernando de Monte Cristi", "Castañuelas", "Guayubín",
                      "Las Matas de Santa Cruz", "Pepillo Salcedo", "Villa Vásquez"]),
    ("Monte Plata", ["Monte Plata", "Bayaguana", "Peralvillo",
                     "Sabana Grande de Boyá", "Yamasá"]),
    ("Pedernales", ["Pedernales", "Oviedo"]),
    ("Peravia", ["Baní", "Nizao", "Matanzas"]),
    ("Puerto Plata", ["San Felipe de Puerto Plata", "Altamira", "Guananico",
                      "Imbert", "Los Hidalgos", "Luperón", "Sosúa", "Villa Isabela",
                      "Villa Montellano"]),
    ("Samaná", ["Santa Bárbara de Samaná", "Las Terrenas", "Sánchez"]),
    ("San Cristóbal", ["San Cristóbal", "Bajos de Haina", "Cambita Garabitos",
                       "Los Cacaos", "Sabana Grande de Palenque", "San Gregorio de Nigua",
                       "Villa Altagracia", "Yaguate"]),
    ("San José de Ocoa", ["San José de Ocoa", "Rancho Arriba", "Sabana Larga"]),
    ("San Juan", ["San Juan de la Maguana", "Bohechío", "El Cercado", "Juan de Herrera",
                  "Las Matas de Farfán", "Vallejuelo"]),
    ("San Pedro de Macorís", ["San Pedro de Macorís", "Consuelo", "Guayacanes",
                              "Quisqueya", "Ramón Santana", "Los Llanos"]),
    ("Sánchez Ramírez", ["Cotuí", "Cevicos", "Fantino", "La Mata"]),
    ("Santiago", ["Santiago de los Caballeros", "Villa Bisonó", "Jánico",
                  "Licey al Medio", "Puñal", "Sabana Iglesia", "San José de las Matas",
                  "Tamboril", "Villa González"]),
    ("Santiago Rodríguez", ["San Ignacio de Sabaneta", "Los Almácigos", "Monción"]),
    ("Santo Domingo", ["Santo Domingo Este", "Boca Chica", "Los Alcarrizos",
                       "Pedro Brand", "San Antonio de Guerra", "Santo Domingo Norte",
                       "Santo Domingo Oeste"]),
    ("Valverde", ["Mao", "Esperanza", "Laguna Salada"]),
]


_SQL_PAIS = (
    'SELECT codigo FROM "Config"."DIM_Pais" '
    "WHERE UPPER(nombre) LIKE '%DOMINIC%' OR UPPER(codigo) IN ('RD','DO') "
    'ORDER BY id'
)
_SQL_PROV_SEL = 'SELECT id FROM "Config"."DIM_Provincia" WHERE pais_codigo = :pc AND nombre = :n'
_SQL_PROV_INS = 'INSERT INTO "Config"."DIM_Provincia" (pais_codigo, nombre, activo) VALUES (:pc, :n, :a)'
_SQL_MUNI_SEL = 'SELECT id FROM "Config"."DIM_Municipio" WHERE provincia_id = :p AND nombre = :n'
_SQL_MUNI_INS = 'INSERT INTO "Config"."DIM_Municipio" (provincia_id, nombre, activo) VALUES (:p, :n, :a)'
_SQL_MUNI_DEL = 'DELETE FROM "Config"."DIM_Municipio" WHERE provincia_id = :p AND nombre = :n'
_SQL_PROV_DEL = 'DELETE FROM "Config"."DIM_Provincia" WHERE id = :p'


def upgrade() -> None:
    conn = op.get_bind()

    # Resolver el código de país de República Dominicana (defensivo).
    codigo = conn.execute(sa.text(_SQL_PAIS)).scalar()
    if not codigo:
        return  # No hay país RD en esta BD → no sembrar nada.

    for provincia, municipios in DATA:
        prov_id = conn.execute(sa.text(_SQL_PROV_SEL), {"pc": codigo, "n": provincia}).scalar()
        if prov_id is None:
            conn.execute(sa.text(_SQL_PROV_INS), {"pc": codigo, "n": provincia, "a": True})
            prov_id = conn.execute(sa.text(_SQL_PROV_SEL), {"pc": codigo, "n": provincia}).scalar()

        for muni in municipios:
            exists = conn.execute(sa.text(_SQL_MUNI_SEL), {"p": prov_id, "n": muni}).scalar()
            if exists is None:
                conn.execute(sa.text(_SQL_MUNI_INS), {"p": prov_id, "n": muni, "a": True})


def downgrade() -> None:
    # Borra únicamente los municipios/provincias sembrados por esta migración,
    # y solo si no tienen dependencias (baja segura para el catálogo semilla).
    conn = op.get_bind()
    codigo = conn.execute(sa.text(_SQL_PAIS)).scalar()
    if not codigo:
        return
    for provincia, municipios in DATA:
        prov_id = conn.execute(sa.text(_SQL_PROV_SEL), {"pc": codigo, "n": provincia}).scalar()
        if prov_id is None:
            continue
        for muni in municipios:
            conn.execute(sa.text(_SQL_MUNI_DEL), {"p": prov_id, "n": muni})
        conn.execute(sa.text(_SQL_PROV_DEL), {"p": prov_id})
