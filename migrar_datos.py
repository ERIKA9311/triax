from sqlalchemy import create_engine, text

# MySQL LOCAL
mysql_local = create_engine(
    "mysql+pymysql://root:@localhost/triax"
)

# TiDB CLOUD
tidb = create_engine(
    "mysql+pymysql://29wQt75pUDVon3E.root:JX0BtogYH4TxlzJH@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/triax?ssl_verify_cert=true&ssl_verify_identity=true"
)

tablas = [
    "usuarios",
    "recovery_codes",
    "user_activities",
    "password_reset_tokens"
]

for tabla in tablas:
    print(f"Migrando {tabla}...")

    with mysql_local.connect() as origen:
        registros = origen.execute(
            text(f"SELECT * FROM {tabla}")
        ).mappings().all()

    if not registros:
        print(f"  {tabla}: sin registros")
        continue

    with tidb.begin() as destino:
        for fila in registros:
            columnas = ", ".join(fila.keys())
            valores = ", ".join([f":{k}" for k in fila.keys()])

            sql = text(
                f"INSERT INTO {tabla} ({columnas}) "
                f"VALUES ({valores})"
            )

            destino.execute(sql, fila)

    print(f"  {len(registros)} registros migrados")

print("Migración finalizada")