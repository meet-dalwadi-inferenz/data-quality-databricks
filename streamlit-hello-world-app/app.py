import streamlit as st
import pandas as pd
import json
import re
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, StAggridTheme
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, StAggridTheme, DataReturnMode
from conn import create_connection
from db import get_catalogs, get_schemas, get_tables, preview_table, get_columns_list
from rules import load_rules_for_selected_table
from helper_functions import list_to_string, string_to_list, normalize_allowed, reorder_rule_columns, unified_column

st.set_page_config(layout="wide")
st.title("SELECT CATALOG, SCHEMA, TABLE")

@st.cache_resource  # connection is cached
def get_connection():
    return create_connection()

if "rules_df" not in st.session_state:
    st.session_state["rules_df"] = None

if "pending_new_rule" not in st.session_state:
    st.session_state["pending_new_rule"] = None

if "columns_with_list_values" not in st.session_state:
    st.session_state.columns_with_list_values = []

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

column_placeholder = "select column (Keep it Null if want to select all column)"
selected_column = []
if (
    selected_catalog != catalog_placeholder
    and selected_schema != schema_placeholder
    and selected_table != table_placeholder
):
    try:
        columns = get_columns_list(conn, selected_catalog, selected_schema, selected_table) or []
    except Exception as e:
        columns = []
        st.warning(f"Could not fetch columns: {e}")

    if columns:
        selected_column = st.multiselect(column_placeholder, options=columns, default=[])
        if not selected_column:
            selected_column = columns
    else:
        st.info("No columns found for the selected table.")
else:
    st.info("Please select catalog, schema and table to choose columns.")

st.write(
    f"selected catalog: {selected_catalog}, schema: {selected_schema}, "
    f"table: {selected_table}, column: {selected_column}"
)

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
        or selected_column == column_placeholder
    ):
        st.session_state.selected_catalog = selected_catalog
        st.session_state.selected_schema = selected_schema
        st.session_state.selected_table = selected_table
        st.session_state.selected_column = selected_column

        # Send the catalog.schema.table for Quality Check
        # Returned Json Data
        load_rules_for_selected_table()
    else:
        st.error("Please choose valid catalog, schema and table before submitting.")

rules_df = st.session_state.get("rules_df", None)

if rules_df is None:
    st.info("Please choose a catalog, schema, table and click Submit to load rules.")
else:
    st.subheader("Applied Rules on the selected table")

    rules_df = st.session_state.get("rules_df", None)
    # Apply pending new rule (if any)
    pending = st.session_state.get("pending_new_rule", None)
    if pending is not None:
        pending_df = pd.DataFrame([pending])
        rules_df = pd.concat([rules_df, pending_df], ignore_index=True)
        st.session_state.rules_df = rules_df
        st.session_state.pending_new_rule = None


    rules_df = st.session_state.rules_df
    # rules_df = unified_column(rules_df)
    rules_df = reorder_rule_columns(rules_df)

    st_aggrid_rules_df = rules_df.copy()

    if "columns_with_list_values" in st.session_state:
        for col in st.session_state.columns_with_list_values:
            if col in st_aggrid_rules_df.columns:
                st_aggrid_rules_df[col] = st_aggrid_rules_df[col].apply(list_to_string)

    is_editable_when_value_present = JsCode("""
        function(params) {
            // safety checks
            console.log('editable params', params);

            if (!params || !params.data || !params.colDef || !params.colDef.field ) return false;

            var field = params.colDef.field;
            var v = params.data[field]; 
            
            if (v === null || v === undefined) return false;

            if (typeof v === "string") {
                return v.trim().length > 0;
            }
            return true;
        }
        """)
    

    value_setter_keep_editable = JsCode(
        """
        function(params) {
            
            console.log('setter params', params);
            var field = params.colDef.field;
            var newValue = params.newValue;

            if (newValue === null || newValue === undefined ||
                (typeof newValue === "string" && newValue.trim() === "")) {
                params.data[field] = "__EMPTY__";
            } else {
                params.data[field] = newValue;
            }
            return true;
        }
        """
    )


    st_aggrid_rules_df = st_aggrid_rules_df.reset_index(drop=True)

    meta_cols = {"rule_index", "criticality", "function", "column", "columns"}
    argument_cols = [c for c in st_aggrid_rules_df.columns if c not in meta_cols]

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

    column_configs = {
        "criticality": {
            "editable": True,
            "cellEditor": "agSelectCellEditor",
            "cellEditorParams": {"values": ["error", "warn"]},
        },
        "trim_strings": {"editable": True},
        "case_sensitive": {"editable": True, "cellDataType": "boolean"},
    }

    for col, params in column_configs.items():
        if col in st_aggrid_rules_df.columns:
            gb.configure_column(col, **params)
    
    for col in argument_cols:
        if col in st_aggrid_rules_df.columns  and col not in column_configs:
            gb.configure_column(
                col,
                editable=is_editable_when_value_present,
                valueSetter=value_setter_keep_editable
            )
    
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
        update_mode=GridUpdateMode.MODEL_CHANGED,
        data_return_mode=DataReturnMode.AS_INPUT,
        theme=custom_theme,
        key="grid_rules",
    )

    selected_data_df = grid_return.get("selected_data")

    if selected_data_df is None or selected_data_df.empty:
        st.info("No rules selected!")
    else:

        # For values which are empty, replace with sentinel
        # meta_cols = {"rule_index", "criticality", "function", "column", "columns"}
        # argument_cols = [c for c in st_aggrid_rules_df.columns if c not in meta_cols]
        # sentinel = "__EMPTY__"
        # for col in argument_cols:
        #     if col in selected_data_df.columns:
        #         selected_data_df[col] = selected_data_df[col].replace(sentinel, "")

        if "columns_with_list_values" in st.session_state:
            for col in st.session_state.columns_with_list_values:
                if col in selected_data_df.columns:
                    selected_data_df[col] = selected_data_df[col].apply(string_to_list)

        st.success(f"{len(selected_data_df)} rules selected for processing.")

        selected_data_df = selected_data_df.set_index("rule_index", drop=True)
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

        new_min = st.number_input("Min value", key="new_rule_min_number", format="%f")
        new_max = st.number_input("Max value", key="new_rule_max_number", format="%f")

        #validation message
        if new_min is not None and new_max is not None:
            try:
                if float(new_min) > float(new_max):
                    st.warning("Min is greater than Max — please check the limits.")
                else:
                    st.info(f"Range set: {new_min} — {new_max}")
            except Exception:
                # should not happen when using number_input, but kept defensively
                st.error("Invalid numeric input for range.")

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

        if new_regex and new_regex.strip():
            #enforce at least one regex meta-character
            meta_chars = r".^$*+?{}[]\|()"
            has_meta = any(c in new_regex for c in meta_chars)

            # long_enough = len(new_regex) >= 3

            #compile check
            try:
                re.compile(new_regex)
                compile_ok = True
            except re.error as compile_err:
                compile_ok = False
                st.error(f"Invalid regex syntax: {compile_err}")

            # Final decision
            if compile_ok:
                if not has_meta:
                    st.warning("This pattern has no regex operators — it will only match literal text.")
                # elif not long_enough:
                #     st.warning("Regex pattern looks too short.")
                else:
                    st.success("Regex pattern looks valid.")

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

        if new_function == "is_in_range":
            try:
                min_val = float(new_min)
                max_val = float(new_max)
                if min_val > max_val:
                    errors.append("Min value cannot be greater than Max value for is_in_range.")
            except Exception:
                errors.append("Min and Max must be numeric values for is_in_range.")

        elif new_function == "sql_expression" and not new_expression.strip():
            errors.append("SQL expression is required for sql_expression.")

        elif new_function == "regex_match":
            if not new_regex or not new_regex.strip():
                errors.append("Regex is required for regex_match.")
            else:
                # compile check
                try:
                    re.compile(new_regex)
                except re.error as compile_err:
                    errors.append(f"Invalid regex syntax: {compile_err}")

                # enforce meta-character rule
                meta_chars = r".^$*+?{}[]\|()"
                if not any(c in new_regex for c in meta_chars):
                    errors.append("Pattern must contain at least one regex operator (.,^,$,*,+,?,{ },( ), etc.)")
                    
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
                new_row["min_limit"] = str(new_min)
                new_row["max_limit"] = str(new_max)
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

            # if "columns_with_list_values" not in st.session_state:
            #     st.session_state.columns_with_list_values = []

            # if "allowed" not in st.session_state.columns_with_list_values:
            #     st.session_state.columns_with_list_values.append("allowed")

            st.session_state.pending_new_rule = new_row

            # for auto-select of this rule in the grid
            st.session_state["last_added_rule_index"] = int(next_idx)

            st.success(f"Added new rule with index {next_idx}.")
            st.rerun()
