import streamlit as st
import pandas as pd
import json
import re
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, StAggridTheme
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, StAggridTheme, DataReturnMode
from conn import create_connection
from db import get_catalogs, get_schemas, get_tables, preview_table, get_columns_list
from rules import load_rules_for_selected_table, rules_json_to_dataframe
from helper_functions import list_to_string, string_to_list, normalize_allowed, reorder_rule_columns, unified_column
from metadata_helper import check_metadata_for_table,generate_checks_by_checking_column_list, generate_checks, get_idx_json, unflatten_df_to_json,generate_checks_for_input_columns, insert_or_update_metadata, apply_safe_column_mapping

st.set_page_config(layout="wide")
st.title("Data Quality Validator")

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


st.write(f"selected catalog: {selected_catalog}")
st.write(f"selected schema: {selected_schema}")
st.write(f"selected table: {selected_table}")
st.write(f"selected column: {selected_column}")

# display table preview by clicking on the preview button
# if st.button("Preview Table"):
#     if not (
#         selected_catalog == catalog_placeholder
#         or selected_schema == schema_placeholder
#         or selected_table == table_placeholder
#     ):
#         with st.spinner("Loading table preview..."):
#             rows, columns, error = preview_table(conn, selected_catalog, selected_schema, selected_table)
#             if error:
#                 st.error(f"Error while previewing table : {error}")
#             else:
#                 df = pd.DataFrame(rows, columns=columns)
#                 st.dataframe(df)
#     else:
#         st.error("Please choose valid catalog, schema and table before previewing.")

if st.button("Submit"):
    if selected_table == table_placeholder:
        st.error("Select a table first.")
    else:
        try:
            st.session_state["selected_catalog"] = selected_catalog
            st.session_state["selected_schema"] = selected_schema
            st.session_state["selected_table"] = selected_table
            st.session_state["selected_column"] = selected_column

rules_df = st.session_state.get("rules_df", None)

if rules_df is None:
    st.info("Please choose a catalog, schema, table and click Submit to load rules.")
else:
            result = check_metadata_for_table(selected_catalog, selected_schema, selected_table)
            st.session_state["metadata_check_result"] = result

            if not result.get("meta_found"):
                st.session_state["rules_df"] = None
                st.warning("No metadata found for this table.")

            else:
                meta_record = result.get("meta_record", {})
                raw_rules = meta_record.get("validation_rules")

                # Convert JSON String → Python List using ONLY json.loads
                try:
                    validation_rules = raw_rules
                except Exception as e:
                    validation_rules = None
                    st.error(f"Failed to parse validation_rules JSON string. Error: {e}")

                # Column Change Handling 
                is_changed = result.get("isChanged", False)
                added_cols  = result.get("added_columns", [])
                removed_cols = result.get("removed_columns", [])

                if is_changed:
                    st.success("Metadata found, but column structure has changed.")
                    if added_cols:
                        st.warning(f"New columns found: {added_cols}")

                    if removed_cols:
                        st.info("Please generate rules for new columns or archive removed-column rules.")

                    # Load existing rules if present
                    if validation_rules:
                        df = rules_json_to_dataframe(validation_rules)
                        st.session_state["rules_df"] = df
                    else:
                        st.session_state["rules_df"] = None
                else:
                    st.success("Metadata found and no changes in column detected. Below are Previous Validation Rules")

                    if validation_rules:
                        try:
                            df = rules_json_to_dataframe(validation_rules)
                            st.session_state["rules_df"] = df
                        except Exception as e:
                            st.error(f"conversion_failure: {e}")
                    else:
                        st.warning("Validation rules are empty.")
                        st.session_state["rules_df"] = None

        except Exception as e:
            st.error(f"Metadata check failed: {e}")
            st.session_state["metadata_check_result"] = None


# ----------- FOLLOW-UP ACTION BUTTONS (OUTSIDE submit button) -----------
meta_result = st.session_state.get("metadata_check_result")

if meta_result:
    st.markdown("---")

    # If no metadata → allow generate rules
    if not meta_result.get("meta_found", False):
        prompt = st.text_area("Prompt", placeholder = 'Keep Null, If you dont want to give any prompt')
        
        if st.button("Generate rules for Selected columns"):
            try:
                ai_rules = generate_checks_by_checking_column_list( st.session_state["selected_catalog"], st.session_state["selected_schema"], st.session_state["selected_table"], "databricks/databricks-claude-sonnet-4-5", prompt, st.session_state["selected_column"])

                rules_json = get_idx_json(ai_rules)
                
                # st.write(rules_json)
                
                df = rules_json_to_dataframe(rules_json)

                st.session_state["rules_df"] = df

                st.success("Generated rules for all columns.")
            except Exception as e:
                st.error(f"Rule generation failed: {e}")

    else:
        added = meta_result.get("added_columns", [])
        removed = meta_result.get("removed_columns", [])

        if added:
            prompt = st.text_area("Prompt", placeholder = 'Keep Null, If you dont want to give any prompt')

            if st.button("Generate rules for New columns"):
                try:
                    df_new = generate_checks_by_checking_column_list(st.session_state["selected_catalog"], st.session_state["selected_schema"], st.session_state["selected_table"], "databricks/databricks-claude-sonnet-4-5",prompt, added)

                    st.session_state["rules_df"] = pd.concat([st.session_state["rules_df"], df_new], ignore_index=True)
                    st.success("Generated rules for new columns.")

                except Exception as e:
                    st.error(f"Failed to generate rules: {e}")

        if removed:
            if st.button("Archive rules for REMOVED columns"):
                try:
                    df = st.session_state.get("rules_df", pd.DataFrame())
                    mask = df["check.arguments.column"].isin(removed)
                    archived = df[mask]

                    if "archived_rules" not in st.session_state:
                        st.session_state["archived_rules"] = []

                    st.session_state["archived_rules"].extend(archived.to_dict("records"))
                    st.session_state["rules_df"] = df[~mask].reset_index(drop=True)
                    st.success(f"Archived {len(archived)} rules.")
                except Exception as e:
                    st.error(f"Archive failed: {e}")

# show archived
if st.session_state.get("archived_rules"):
    st.subheader("Archived Rules")
    st.dataframe(pd.DataFrame(st.session_state["archived_rules"]))

raw_rules_obj = st.session_state.get("rules_df", None)

def _normalize_to_df(obj):
    import pandas as pd
    # None => None
    if obj is None:
        return None

    # Already a DataFrame -> return as-is
    if isinstance(obj, pd.DataFrame):
        return obj

    # If a tuple -> try to find a DataFrame inside, or convert first element
    if isinstance(obj, tuple):
        for part in obj:
            if isinstance(part, pd.DataFrame):
                return part
        # fallback: try convert first element if it's list/dict
        if len(obj) > 0:
            first = obj[0]
            if isinstance(first, (list, dict)):
                try:
                    return pd.DataFrame(first)
                except Exception:
                    return None
        return None

    # If list of dicts -> DataFrame
    if isinstance(obj, list):
        try:
            return pd.DataFrame(obj)
        except Exception:
            return None

    # If dict -> one-row DataFrame
    if isinstance(obj, dict):
        try:
            return pd.DataFrame([obj])
        except Exception:
            return None

    # If pandas Series -> convert to one-row DF
    if isinstance(obj, pd.Series):
        try:
            return obj.to_frame().T
        except Exception:
            return None

    # Unknown types -> None (avoid crash)
    return None

rules_df = _normalize_to_df(raw_rules_obj)
# store normalized version back to session for consistency
st.session_state["rules_df"] = rules_df

if rules_df is not None:
>>>>>>> Stashed changes
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

    # ---- FIX: ensure rule_index is always numeric ----
    if "rule_index" in st_aggrid_rules_df.columns:
        st_aggrid_rules_df["rule_index"] = pd.to_numeric(
            st_aggrid_rules_df["rule_index"],
            errors="coerce"
        ).fillna(-1).astype(int)


    if "allowed" in st_aggrid_rules_df.columns:
        st_aggrid_rules_df["allowed"] = st_aggrid_rules_df["allowed"].apply(list_to_string)

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

        st.session_state["selected_rules"] = selected_data_df
        st.dataframe(selected_data_df)

    st.markdown("---")
    st.markdown("### ➕ Add new rule")

    # next_idx calculation
# ---- FIX: convert to numeric before computing next index ----
    if (
        st_aggrid_rules_df is None
        or st_aggrid_rules_df.empty
        or "rule_index" not in st_aggrid_rules_df.columns
    ):
        next_idx = 0
    else:
        st_aggrid_rules_df["rule_index"] = pd.to_numeric(
            st_aggrid_rules_df["rule_index"],
            errors="coerce"
        ).fillna(-1).astype(int)

        next_idx = int(st_aggrid_rules_df["rule_index"].max()) + 1


    current_cols = get_columns_list(conn, st.session_state["selected_catalog"], st.session_state["selected_schema"], st.session_state["selected_table"])

    new_column = st.selectbox("Column name",current_cols,key="new_rule_column")

    # Criticality
    new_criticality = st.selectbox("Criticality", ["error", "warn"], index=0, key="new_rule_criticality")

    # Rule name
    function_options = sorted(st_aggrid_rules_df["function"].dropna().unique().tolist())
    new_function = st.selectbox("Rule name", function_options, key="new_function")

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
        new_expression = st.text_input("SQL expression (Please give sql_expression)", key="new_rule_expression")

    elif new_function == "regex_match":
        new_regex = st.text_input("Regex pattern (Please give regex pattern)", key="new_rule_regex")

        if new_regex and new_regex.strip():
            #enforce at least one regex meta-character
            meta_chars = r".^$*+?{}[]\|()"
            has_meta = any(c in new_regex for c in meta_chars)

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
    
    # ================= TARGET & QUARANTINE INPUTS =================
    st.markdown("---")
    st.markdown("### 🎯 Output Configuration")

    col1, col2 = st.columns(2)

    with col1:
        target_table = st.text_input(
            "Target Table (catalog.schema.table)",
            placeholder="eg: dq_results.prod.patient_rules",
            key="target_table_input"
        )

    with col2:
        quarantine_table = st.text_input(
            "Quarantine Table (catalog.schema.table)",
            placeholder="eg: dq_quarantine.prod.patient_quarantine",
            key="quarantine_table_input"
        )

    # ================= SAVE APPLIED RULES =================
    if st.button("Save Applied Rules", key="btn_save_applied_rules"):
        try:
            if not target_table or not quarantine_table:
                st.warning("Please provide both Target and Quarantine table details.")
            else:
                grid_df = st.session_state.get("selected_rules")

                if grid_df is None or grid_df.empty:
                    st.warning("No rules available to save.")
                else:
                    grid_df = grid_df.copy()

                    # UI → backend format
                    if "allowed" in grid_df.columns:
                        grid_df["allowed"] = grid_df["allowed"].apply(string_to_list)

                    if "columns" in grid_df.columns:
                        grid_df["columns"] = grid_df["columns"].apply(string_to_list)

                    if "rule_index" in grid_df.columns:
                        grid_df["rule_index"] = (
                            pd.to_numeric(grid_df["rule_index"], errors="coerce")
                            .fillna(0)
                            .astype(int)
                        )

                    # grid_df = grid_df.drop(["rule_index"], axis=1)
                    grid_df = grid_df.fillna('NOT TO BE INCLUDED')

                    rename_map = {
                            "check!#!function": "function",
                            "check!#!arguments!#!column": "column",
                            "check!#!arguments!#!columns": "columns",
                            "check!#!arguments!#!regex": "regex",
                            "check!#!arguments!#!expression": "expression",
                            "check!#!arguments!#!allowed": "allowed",
                            "check!#!arguments!#!min_limit": "min_limit",
                            "check!#!arguments!#!max_limit": "max_limit",
                            "check!#!arguments!#!case_sensitive": "case_sensitive",
                        }

                    grid_df = apply_safe_column_mapping(grid_df, rename_map)

                    # Convert DF → JSON
                    ui_rules_json = unflatten_df_to_json(grid_df, '!#!')

                    # Split target & quarantine tables
                    op_catalog, op_schema, op_table = target_table.split(".")
                    qt_catalog, qt_schema, qt_table = quarantine_table.split(".")

                    # Call your insert function
                    result = insert_or_update_metadata(
                        ip_catalog=st.session_state["selected_catalog"],
                        ip_schema=st.session_state["selected_schema"],
                        ip_table=st.session_state["selected_table"],
                        op_catalog=op_catalog,
                        op_schema=op_schema,
                        op_table=op_table,
                        qt_catalog=qt_catalog,
                        qt_schema=qt_schema,
                        qt_table=qt_table,
                        op_check_meta_data_func=st.session_state["metadata_check_result"],
                        ui_rules_json=ui_rules_json
                    )
                    
                    if result['status'] == 'success':
                        st.success("Applied rules saved successfully.")
                    else:
                        st.error(f"Failed to save applied rules: {result['message']}")

        except ValueError:
            st.error("Please enter table names in catalog.schema.table format.")
        except Exception as e:
            st.error(f"Failed to save applied rules: {e}")
    # =============================================================

