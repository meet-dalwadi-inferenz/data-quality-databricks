import pandas as pd
import json

def list_to_string(value):
    if isinstance(value, list):
        return ", ".join(value)
    return value

def string_to_list(value):
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip() == "":
            return []
        return [item.strip() for item in value.split(',')]
    return []

def normalize_allowed(x):
    if isinstance(x, list):
        return x
    else:
        if x is None or pd.isna(x):
            return []
        else:
            return [v.strip() for v in str(x).split(",") if v.strip()]

def reorder_rule_columns(df):
    preferred_order = ["selected","Manage", "rule_index", "column", "rule_name","check_function","allowed"]

    # Keep only the ones that actually exist in this df (avoid KeyErrors)
    existing_preferred = [col for col in preferred_order if col in df.columns]

    # All other columns (remaining ones), in original order
    remaining_columns = [col for col in df.columns if col not in existing_preferred]

    # Final desired order
    return df[existing_preferred + remaining_columns]
  
def unified_column(df):

    if "columns" in df.columns:
        df["column"] = df.apply(
            lambda row:
                ", ".join(row["columns"]) if (
                    (row.get("column") is None or row.get("column") == "" or pd.isna(row.get("column")))
                    and isinstance(row.get("columns"), list)
                )
                else row.get("column"),
            axis=1
        )

        # df.drop(columns=["columns"], inplace=True)

    return df

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


def convert_df_suitable_for_json(df,rename_col_map):

    df = df.copy()
    na_replace_value = "NOT TO BE INCLUDED"

    df.drop(columns=["rule_index"], inplace=True)
    df = df.where(df.notna(), na_replace_value)

    reversed_rename_col_map = {v: k for k, v in rename_col_map.items()}
    df_renamed = df.rename(columns=reversed_rename_col_map)

    return df_renamed

def has_invalid_values(df: pd.DataFrame) -> bool:
    INVALID_SENTINEL = "__EMPTY__"
    return (df == INVALID_SENTINEL).any().any()