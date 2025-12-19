from databricks.connect import DatabricksSession
from databricks.sdk.core import Config
from databricks.labs.dqx.profiler.generator import DQGenerator
from databricks.labs.dqx.config import LLMModelConfig, InputConfig
from databricks.labs.dqx.engine import DQEngine
from databricks.sdk import WorkspaceClient
from databricks.labs.dqx.profiler.profiler import DQProfiler
import pyspark.sql.functions as F
import uuid
from pyspark.errors import PySparkException
from databricks.sdk import WorkspaceClient
import json
import pandas as pd
from datetime import datetime
from pyspark.sql import Row
from pyspark.sql.functions import lit, current_timestamp,current_user,md5
from pyspark.sql.types import *

dq_schema = StructType([
    StructField("dq_checks_id", StringType(), False),
    StructField("input_catalog_name", StringType(), True),
    StructField("input_schema_name", StringType(), True),
    StructField("input_table_name", StringType(), True),
    StructField("output_catalog_name", StringType(), True),
    StructField("output_schema_name", StringType(), True),
    StructField("output_table_name", StringType(), True),
    StructField("quarantine_catalog_name", StringType(), True),
    StructField("quarantine_schema_name", StringType(), True),
    StructField("quarantine_table_name", StringType(), True),
    StructField("input_table_column_list", ArrayType(StringType()), True),
    StructField("selected_column_list", ArrayType(StringType()), True),
    StructField("validation_rules", StringType(), True),
    StructField("inserted_at", TimestampType(), True),
    StructField("inserted_by", StringType(), True),
    StructField("updated_at", TimestampType(), True),
    StructField("updated_by", StringType(), True)
])


cfg = Config(
    # host="adb-123456.34.azuredatabricks.net",   
    # token="dap-xxxxx...",                       
    cluster_id="0725-150441-orw4idc0"
)

spark = DatabricksSession.builder.sdkConfig(cfg).getOrCreate()
w = WorkspaceClient()
dbutils_sdk = w.dbutils

def apply_safe_column_mapping(df, rename_map):
    """Rename flattened columns using the mapping but only if column exists."""
    actual_map = {old: new for old, new in rename_map.items() if old in df.columns}
    return df.rename(columns=actual_map)

def unflatten_df_to_json(df,col_name_sep):
    def assign_nested(d, keys, value):
        
        key = keys[0]
        
        if key not in d:
            d[key] = {} if not keys[1:] or not keys[1].isdigit() else []
            
        if len(keys) == 1:
            d[key] = value
            
        else:
            assign_nested(d[key], keys[1:], value)
           

    records = []
    for _, row in df.iterrows():
        root = {}

        for col, value in row.items():
            if value == 'NOT TO BE INCLUDED' :
                continue
            keys = col.split(col_name_sep)
            assign_nested(root, keys, value)

        records.append(root)
    
    return records

def get_idx_json(ai_checks):
    if not isinstance(ai_checks, list):
        raise ValueError("Input must be a list of rules")

    indexed_rules = {}

    for idx, rule in enumerate(ai_checks):
        indexed_rules[idx] = rule

    # match your required structure: list with one dict
    return [indexed_rules]

def check_metadata_for_table(ip_catalog,ip_schema,ip_table, column_list_ui):
    result = {}

    df_current = spark.sql(f"describe table {ip_catalog}.{ip_schema}.{ip_table}").select("col_name")
    current_cols = [row.col_name for row in df_current.collect()]

    result["current_columns"] = current_cols
    result["current_selected_columns"] = column_list_ui
    
    metadata_fetch_query = f"""
        SELECT *
        FROM data_quality.admin.dq_table_metadata_temp
        WHERE input_catalog_name = '{ip_catalog}'
        AND input_schema_name = '{ip_schema}'
        AND input_table_name = '{ip_table}'
        ORDER BY updated_at DESC, inserted_at DESC
        LIMIT 1
    """

    df_meta = spark.sql(metadata_fetch_query)
    pdf_meta = df_meta.toPandas()

    if pdf_meta.empty:
        result["meta_found"] = False
        result["message"] = "No metadata found for the table"
        return result
    
    else:
        meta_cols= pdf_meta.iloc[0]["input_table_column_list"]
        added_cols = list(set(current_cols) - set(meta_cols))
        deleted_cols = list(set(meta_cols) - set(current_cols))

        result['meta_found'] = True
        if not added_cols and not deleted_cols:
            result['isChanged'] = False
        else:
            if added_cols:
                result['isChanged'] = True
                result['added_columns'] = added_cols
            if deleted_cols:
                result['isChanged'] = True
                result['removed_columns'] = deleted_cols

        meta_record = pdf_meta.to_dict(orient='records')[0]
        try:
            meta_record['validation_rules'] = json.loads(meta_record['validation_rules'])
        except:
            meta_record['validation_rules'] = meta_record['validation_rules']
        result['meta_record'] = meta_record
    return result

def insert_or_update_metadata(ip_catalog, ip_schema, ip_table, op_catalog, op_schema, op_table, qt_catalog,qt_schema, qt_table, op_check_meta_data_func, ui_rules_json):
    ui_rules_json_str = json.dumps(ui_rules_json)

    if not op_check_meta_data_func['meta_found']:
        row_data = {
            "dq_checks_id": str(uuid.uuid4()),
            "input_catalog_name": ip_catalog,
            "input_schema_name": ip_schema,
            "input_table_name": ip_table,

            "output_catalog_name": op_catalog,
            "output_schema_name": op_schema,
            "output_table_name": op_table,

            "quarantine_catalog_name": qt_catalog,
            "quarantine_schema_name": qt_schema,
            "quarantine_table_name": qt_table,

            "input_table_column_list": op_check_meta_data_func["current_columns"],
            "selected_column_list": op_check_meta_data_func.get("current_selected_columns",[]),
            "validation_rules": ui_rules_json_str,

            "inserted_at": None,
            "inserted_by": None,
            "updated_at": None,
            "updated_by": None
        }

        df_insert = spark.createDataFrame([row_data], schema=dq_schema)

        df_insert = df_insert.withColumn('inserted_at',current_timestamp()).withColumn('inserted_by',current_user()).withColumn('updated_at',current_timestamp()).withColumn('updated_by',current_user())
        
        try:
            df_insert.write.mode("append").insertInto("data_quality.admin.dq_table_metadata_temp")
        except Exception as e:
            return {"status" : "failed", "message" : str(e) }  

        return {"message" : "inserted", "status" : "success" }
    
    else:
        meta_record = op_check_meta_data_func['meta_record']
        
        df_existing = pd.DataFrame([meta_record])
        df_existing = spark.createDataFrame(df_existing)
        
        # df_existing = spark.createDataFrame(df_existing)

        df_update = (
            df_existing
            .withColumn("output_catalog_name", lit(op_catalog))
            .withColumn("output_schema_name", lit(op_schema))
            .withColumn("output_table_name", lit(op_table))
            .withColumn("quarantine_catalog_name", lit(qt_catalog))
            .withColumn("quarantine_schema_name", lit(qt_schema))
            .withColumn("quarantine_table_name", lit(qt_table))
            .withColumn("input_table_column_list", lit(op_check_meta_data_func['current_columns']))
            .withColumn("selected_column_list", lit(op_check_meta_data_func['current_selected_columns']))
            .withColumn("validation_rules", lit(ui_rules_json_str))
            .withColumn("updated_at", current_timestamp())
            .withColumn("updated_by", current_user())
        )

        df_update.createOrReplaceTempView("update_temp")

        try:

            spark.sql("""
                MERGE INTO data_quality.admin.dq_table_metadata_temp AS target
                USING update_temp AS source
                ON target.dq_checks_id = source.dq_checks_id
                WHEN MATCHED THEN UPDATE SET *
            """)
        except Exception as e:
            return {"status" : "failed", "message" : str(e) }

        return {"message" : "updated", "status" : "success" }
    
    
def generate_checks(ip_catalog,ip_schema,ip_table,llm_model_name,ip_promt):
    ip_catalog = ip_catalog
    ip_schema = ip_schema
    ip_table = ip_table
    llm_model_name = llm_model_name
    ip_promt = ip_promt
    if ip_promt == '':
        ip_promt = dbutils_sdk.fs.head('/Volumes/data_quality/data/files/quality_check_generate_promt.txt')
    

    ws = WorkspaceClient()
    profiler = DQProfiler(ws)
    dq_engine = DQEngine(ws, spark)

    # create generator with tuned LLM config
    llm_cfg = LLMModelConfig(model_name=llm_model_name)
    generator = DQGenerator(ws, llm_model_config=llm_cfg)
    ai_checks = generator.generate_dq_rules_ai_assisted(user_input=ip_promt, input_config=InputConfig(location=f'{ip_catalog}.{ip_schema}.{ip_table}'))
    print("======== Generated checks =========")
    return ai_checks

def generate_checks_for_input_columns(ip_catalog,ip_schema,ip_table,ip_column_list,llm_model_name,ip_promt):
    generate_only_for_columns = ip_column_list

    generate_only_for_columns_str = ",".join(generate_only_for_columns)
    print(generate_only_for_columns_str)

    try:
        count_df = spark.table(f"{ip_catalog}.{ip_schema}.{ip_table}").count()
        thirty_percent = int(count_df * 0.30)
        print(thirty_percent)
        generate_only_for_columns_df = spark.sql(f"select {generate_only_for_columns_str} from {ip_catalog}.{ip_schema}.{ip_table} limit {thirty_percent}")
        tmp_catalog = ip_catalog
        tmp_schema = ip_schema
        tmp_table = f'tmp_{ip_table}_dqx_selected_cols_{uuid.uuid4().hex[:8]}'

        # write as a managed/catalog table (overwrite if exists)
        generate_only_for_columns_df.write.mode("overwrite").saveAsTable(f'{tmp_catalog}.{tmp_schema}.{tmp_table}')
        print("Written temp catalog table:", tmp_table)
    
        generated_checks = generate_checks(tmp_catalog,tmp_schema,tmp_table,llm_model_name,ip_promt)
        spark.sql(f"drop table tmp_{ip_table}_dqx_selected_cols_{uuid.uuid4().hex[:8]}")
        return generated_checks
    
    except PySparkException as ex:
        print("Error Condition   : " + ex.getErrorClass())
        print("Message arguments : " + str(ex.getMessageParameters()))
        print("SQLSTATE          : " + ex.getSqlState())
        print(ex)
        return ex

def generate_checks_by_checking_column_list(ip_catalog,ip_schema,ip_table,llm_model_name,ip_promt,ip_column_list=[]):
    ip_catalog = ip_catalog
    ip_schema = ip_schema
    ip_table = ip_table
    llm_model_name = llm_model_name
    promt = ip_promt
    ip_column_list = ip_column_list
    print(ip_column_list)
    if len(ip_column_list) == 0:
        generated_checks = generate_checks(ip_catalog,ip_schema,ip_table,llm_model_name,promt)
    else:
        generated_checks = generate_checks_for_input_columns(ip_catalog,ip_schema,ip_table,ip_column_list,llm_model_name,promt)
    
    return generated_checks


