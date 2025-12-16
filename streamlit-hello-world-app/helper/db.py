def get_catalogs(conn):
    with conn.cursor() as cursor:
        cursor.execute("SHOW CATALOGS")
        rows = cursor.fetchall()
        return [r[0] for r in rows]

def get_schemas(conn, catalog):
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW SCHEMAS IN {catalog}")
        rows = cursor.fetchall()
        # row[0] is schema name for SHOW SCHEMAS
        return [row[0] for row in rows]

def get_tables(conn, catalog, schema):
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW TABLES IN {catalog}.{schema}")
        rows = cursor.fetchall()
        # row[1] = tableName when using SHOW TABLES
        return [row[1] for row in rows]

def get_columns_list(conn, catalog, schema, table):
    with conn.cursor() as cursor:
        cursor.execute(f"DESCRIBE TABLE {catalog}.{schema}.{table}")
        rows = cursor.fetchall()
        return [row[0] for row in rows if row[0] and not row[0].startswith("#")]
    
def preview_table(conn, catalog, schema, table):
    try : 
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {catalog}.{schema}.{table} LIMIT 10")
            rows = cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            return rows, columns, None
        
    except Exception as e:
        return None,None,str(e)