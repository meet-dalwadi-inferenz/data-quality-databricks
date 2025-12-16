from databricks import sql
from databricks.sdk.core import Config

cfg = Config()

def create_connection(http_path = '/sql/1.0/warehouses/9be5cedc3ba71d9d'):
    return sql.connect(
        server_hostname=cfg.host,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate,
    )