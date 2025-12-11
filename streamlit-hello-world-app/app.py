import streamlit as st
import pandas as pd
import json
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, StAggridTheme
from conn import create_connection
from db import get_catalogs, get_schemas, get_tables, preview_table, get_columns_list
from rules import load_rules_for_selected_table
from helper_functions import list_to_string, string_to_list, normalize_allowed, reorder_rule_columns, unified_column


#FALSI 

# cfg = Config()  # Set the DATABRICKS_HOST environment variable when running locally

st.set_page_config(layout="wide")
st.title("SELECT CATALOG, SCHEMA, TABLE")

@st.cache_resource  # connection is cached
def get_connection():
    return create_connection()

if "rules_df" not in st.session_state:
    st.session_state["rules_df"] = None

if "pending_new_rule" not in st.session_state:
    st.session_state["pending_new_rule"] = None


conn = get_connection()
catalogs = get_catalogs(conn)
catalog_placeholder = "select catalog"
catalogs = [catalog_placeholder] + catalogs
selected_catalog = st.selectbox("catalog", catalogs, index=0)

if selected_catalog != catalog_placeholder:
    schemas = get_schemas(conn, selected_catalog) or []
else:
    schemas = []

schema_placeholder = "select schema"
schemas = [schema_placeholder] + schemas
selected_schema = st.selectbox("schema", schemas, index=0)

if selected_schema != schema_placeholder:
    tables = get_tables(conn, selected_catalog, selected_schema) or []
else:
    tables = []

table_placeholder = "select table"
tables = [table_placeholder] + tables
selected_table = st.selectbox("table", tables, index=0)

st.write(f"selected catalog: {selected_catalog}, schema: {selected_schema}, table: {selected_table}")

# display table preview by clicking on the preview button
if st.button("Preview Table"):
    if not (
        selected_catalog == catalog_placeholder
        or selected_schema == schema_placeholder
        or selected_table == table_placeholder
    ):
        with st.spinner("Loading table preview..."):
            rows, columns, error = preview_table(conn, selected_catalog, selected_schema, selected_table)
            if error:
                st.error(f"Error while previewing table : {error}")
            else:
                df = pd.DataFrame(rows, columns=columns)
                st.dataframe(df)
    else:
        st.error("Please choose valid catalog, schema and table before previewing.")


if st.button("Submit"):
    if not (
        selected_catalog == catalog_placeholder
        or selected_schema == schema_placeholder
        or selected_table == table_placeholder
    ):
        st.session_state.selected_catalog = selected_catalog
        st.session_state.selected_schema = selected_schema
        st.session_state.selected_table = selected_table

        # Send the catalog.schema.table for Quality Check
        # Returned Json Data
        load_rules_for_selected_table()
    else:
        st.error("Please choose valid catalog, schema and table before submitting.")

# SAFELY get rules_df from session state
rules_df = st.session_state.get("rules_df", None)

rules_df = st.session_state.get("rules_df", None)

if rules_df is None:
    st.info("Please choose a catalog, schema, table and click Submit to load rules.")
else:
    st.subheader("Applied Rules on the selected table")

    # DEBUG: show last few rows before applying pending rule
    # st.write("DEBUG: rules_df BEFORE pending:", rules_df.tail())

    # Apply pending new rule (if any)
    pending = st.session_state.get("pending_new_rule", None)
    if pending is not None:
        # st.write("DEBUG: Applying pending_new_rule:", pending)
        pending_df = pd.DataFrame([pending])
        rules_df = pd.concat([rules_df, pending_df], ignore_index=True)
        st.session_state.rules_df = rules_df
        st.session_state.pending_new_rule = None



    rules_df = unified_column(rules_df)
    rules_df = reorder_rule_columns(rules_df)

    st_aggrid_rules_df = rules_df.copy()

    if "allowed" in st_aggrid_rules_df.columns:
        st_aggrid_rules_df["allowed"] = st_aggrid_rules_df["allowed"].apply(list_to_string)

    if "columns" in st_aggrid_rules_df.columns:
        st_aggrid_rules_df["columns"] = st_aggrid_rules_df["columns"].apply(list_to_string)

    st.write("DEBUG: rules_df AFTER reorder_rule_columns:", rules_df.tail())

    is_editable_allowed = JsCode(
        """
        function(params) {
            if (params.data.function === 'is_in_list') {
                return true;
            } else {
                return false;
            }
        }
        """
    )

    is_editable_regex = JsCode(
        """
        function(params) {
            if (params.data.function === 'regex_match') {
                return true;
            } else {
                return false;
            }
        }
        """
    )

    is_editable_expression = JsCode(
        """
        function(params){
            if (params.data.function === 'sql_expression'){
                return true;
            }
            else {
                return false;
            }
        } 
        """
    )

    id_editable_min_limit = JsCode(
        """
        function(params) {
            if (params.data.function === 'is_in_range' || params.data.function === 'is_aggr_not_less_than')
            {
                return true;
            }
            else {
                return false;
            }
        }
        """
    )

    is_editable_max_limit = JsCode(
        """
        function(params) {
            if (params.data.function === 'is_in_range' || params.data.function === 'is_aggr_not_greater_than')
            {
                return true;
            }
            else {
                return false;
            }
        }
        """
    )

    column_configs = {
        "criticality": {
            "editable": True,
            "cellEditor": "agSelectCellEditor",
            "cellEditorParams": {"values": ["error", "warn"]},
        },
        "allowed": {"editable": is_editable_allowed},
        "regex": {"editable": is_editable_regex},
        "trim_strings": {"editable": True},
        "expression": {"editable": is_editable_expression},
        "min_limit": {"editable": id_editable_min_limit},
        "max_limit": {"editable": is_editable_max_limit},
        "case_sensitive": {"editable": True, "cellDataType": "boolean"},
    }

    st_aggrid_rules_df = st_aggrid_rules_df.reset_index(drop=True)

    gb = GridOptionsBuilder.from_dataframe(st_aggrid_rules_df)
    gb.configure_selection("multiple", use_checkbox=True)


    last_added_rule_index = st.session_state.get("last_added_rule_index", None)

    if last_added_rule_index is not None:
        on_row_data_updated = JsCode(
            f"""
            function(params) {{
                var target = {int(last_added_rule_index)};
                params.api.forEachNode(function(node) {{
                    if (node.data && node.data.rule_index === target) {{
                        node.setSelected(true);  // add to existing selection
                    }}
                }});
            }}
            """
        )
        gb.configure_grid_options(onRowDataUpdated=on_row_data_updated)
        # clear so it only applies once per added row
        st.session_state["last_added_rule_index"] = None

    for col, params in column_configs.items():
        if col in st_aggrid_rules_df.columns:
            gb.configure_column(col, **params)
    
    st.write("DEBUG: rules_df AFTER column_configs_items:", rules_df.tail())

    grid_options = gb.build()

    custom_theme = (
        StAggridTheme(base="quartz")
        .withParams(
            selectedRowBackgroundColor="rgba(0, 128, 0, 0.3)",
            rowBorder=True,
            columnBorder=True,
            borderColor="#9ca3af",
        )
    )

    grid_return = AgGrid(
        st_aggrid_rules_df,
        gridOptions=grid_options,
        allow_unsafe_jscode=True,
        update_mode=GridUpdateMode.MODEL_CHANGED,  # send back edits
        data_return_mode="AS_INPUT",
        theme=custom_theme,
        key="grid_rules",
    )

    selected_data_df = grid_return.get("selected_data")

    if selected_data_df is None or selected_data_df.empty:
        st.info("No rules selected!")
    else:
        selected_data_df = selected_data_df.set_index("rule_index", drop=True)

        if "allowed" in selected_data_df.columns:
            selected_data_df["allowed"] = selected_data_df["allowed"].apply(string_to_list)

        if "columns" in selected_data_df.columns:
            selected_data_df["columns"] = selected_data_df["columns"].apply(string_to_list)

        st.success(f"{len(selected_data_df)} rules selected for processing.")
        st.dataframe(selected_data_df)

    st.markdown("---")

    st.markdown("### ➕ Add new rule")

    # next_idx calculation
    if (
        st_aggrid_rules_df is None
        or st_aggrid_rules_df.empty
        or "rule_index" not in st_aggrid_rules_df.columns
    ):
        next_idx = 0
    else:
        next_idx = int(st_aggrid_rules_df["rule_index"].max()) + 1

    # Column dropdown – from actual table columns
    current_cols = []
    try:
        current_cols = get_columns_list(conn, selected_catalog, selected_schema, selected_table)
    except Exception:
        # fallback: columns from rules_df if DESCRIBE fails
        if "column" in st_aggrid_rules_df.columns:
            current_cols = sorted(st_aggrid_rules_df["column"].dropna().unique().tolist())

    new_column = st.selectbox(
        "Column name",
        current_cols,
        key="new_rule_column",
    )

    # Criticality
    new_criticality = st.selectbox(
        "Criticality",
        ["error", "warn"],
        index=0,
        key="new_rule_criticality",
    )

    # Rule name
    function_options = sorted(st_aggrid_rules_df["function"].dropna().unique().tolist())
    new_function = st.selectbox(
        "Rule name",
        function_options,
        key="new_function",
    )

    # Dynamic inputs depending on function
    new_min = None
    new_max = None
    new_expression = ""
    new_regex = ""
    new_allowed = ""

    if new_function == "is_in_range":
        st.write("Put range limits:")
        new_min = st.text_input("Min value", key="new_rule_min")
        new_max = st.text_input("Max value", key="new_rule_max")

    elif new_function == "sql_expression":
        new_expression = st.text_input(
            "SQL expression (Please give sql_expression)",
            key="new_rule_expression",
        )

    elif new_function == "regex_match":
        new_regex = st.text_input(
            "Regex pattern (Please give regex pattern)",
            key="new_rule_regex",
        )

    elif new_function == "is_in_list":
        new_allowed = st.text_input(
            "Allowed values (Please give comma-separated values)",
            key="new_rule_allowed",
        )
    else:
        st.info("No extra parameters needed for this rule type.")

    # Add rule button
    if st.button("Add rule", key="btn_add_rule"):

        errors = []

        if not new_column:
            errors.append("Please select a column.")

        # rule-specific validations
        if new_function == "is_in_range":
            if not new_min or not new_min.strip():
                errors.append("Min value is required for is_in_range.")
            if not new_max or not new_max.strip():
                errors.append("Max value is required for is_in_range.")
        elif new_function == "sql_expression" and not new_expression.strip():
            errors.append("SQL expression is required for sql_expression.")
        elif new_function == "regex_match" and not new_regex.strip():
            errors.append("Regex is required for regex_match.")
        elif new_function == "is_in_list" and not new_allowed.strip():
            errors.append("Allowed values are required for is_in_list.")

        if errors:
            for msg in errors:
                st.warning(msg)
        else:
            # Build new row – only populate relevant fields
            new_row = {
                "rule_index": next_idx,
                "criticality": new_criticality,
                "function": new_function,
                "column": new_column,
                "expression": None,
                "regex": None,
                "allowed": [],
            }

            if new_function == "is_in_range":
                new_row["min_limit"] = new_min.strip()
                new_row["max_limit"] = new_max.strip()
            elif new_function == "sql_expression":
                new_row["expression"] = new_expression.strip()
            elif new_function == "regex_match":
                new_row["regex"] = new_regex.strip()
            elif new_function == "is_in_list":
                new_row["allowed"] = [
                    v.strip()
                    for v in new_allowed.split(",")
                    if v.strip()
                ]

            st.session_state.pending_new_rule = new_row

            # for auto-select of this rule in the grid
            st.session_state["last_added_rule_index"] = int(next_idx)

            st.success(f"Added new rule with index {next_idx}.")
            st.rerun()
