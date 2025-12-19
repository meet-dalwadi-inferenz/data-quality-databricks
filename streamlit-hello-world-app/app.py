import streamlit as st
import pandas as pd
import json
import re
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, StAggridTheme, DataReturnMode
from helper.conn import create_connection
from helper.db import get_catalogs, get_schemas, get_tables, preview_table, get_columns_list
from helper.rules import load_rules_for_selected_table, rules_json_to_dataframe,save_columns_with_list_values
from helper.metadata_helper import check_metadata_for_table,generate_checks_by_checking_column_list, generate_checks, get_idx_json, unflatten_df_to_json,generate_checks_for_input_columns, insert_or_update_metadata, apply_safe_column_mapping
from helper.helper_functions import list_to_string, string_to_list, normalize_allowed, reorder_rule_columns, unified_column, unflatten_df_to_json, convert_df_suitable_for_json,has_invalid_values, get_all_check_rules, archive_rules_for_removed_columns
from helper.grid_helper import render_rules_grid, get_selected_rules_combined,get_next_rule_index_and_target

st.set_page_config(layout="wide")
st.title("Data Quality Validator")

@st.cache_resource  # connection is cached
def get_connection():
    return create_connection()

# state to manage the previous only one grid dataframe rules df
if "rules_df" not in st.session_state:
    st.session_state["rules_df"] = None

if "selected_rules" not in st.session_state:
    st.session_state.selected_rules = None

if "selected_rule_indexes" not in st.session_state:
    st.session_state.selected_rule_indexes = []

# states for metadata rules management
if "metadata_rules_df" not in st.session_state:
    st.session_state["metadata_rules_df"] = None

if "metadata_selected_rules" not in st.session_state:
    st.session_state["metadata_selected_rules"] = None

if "metadata_selected_rules_indexes" not in st.session_state:
    st.session_state["metadata_selected_rules_indexes"] = []

# states for generated rules management
if "generated_rules_df" not in st.session_state:
    st.session_state["generated_rules_df"] = None

if "generated_selected_rules" not in st.session_state:
    st.session_state["generated_selected_rules"] = None

if "generated_selected_rules_indexes" not in st.session_state:
    st.session_state["generated_selected_rules_indexes"] = []
    
# state for adding new rule
if "pending_new_rule" not in st.session_state:
    st.session_state["pending_new_rule"] = None

# state to manage lists
if "columns_with_list_values" not in st.session_state:
    st.session_state.columns_with_list_values = []

# state to manage versions of grid dataframe
if "grid_version" not in st.session_state:
    st.session_state.grid_version = 0

if "is_adding_rule" not in st.session_state:
    st.session_state.is_adding_rule = False

#workflow
if "submitted" not in st.session_state:
    st.session_state.submitted = False

def refresh_all():
    keys_to_reset = [
        # selection
        "catalog","schema","table",
        "selected_catalog", "selected_schema", "selected_table", "selected_columns",

        # workflow
        "submitted",

        # rules
        "metadata_rules_df",
        "generated_rules_df",
        "selected_rules_df",
        "archived_rules_df",
        "metadata_check_result",

        # selections
        "metadata_selected_rules",
        "generated_selected_rules",

        # prompts / UI
        # "ai_prompt",
        "warning",
        "pending_new_rule",
        "is_adding_rule"
    ]

    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

conn = get_connection()

catalogs = get_catalogs(conn) or []
catalog_placeholder = "select catalog"
catalogs = [catalog_placeholder] + catalogs

col1, col2, col3, col4 = st.columns([3, 3, 3, 1])

with col1:
    selected_catalog = st.selectbox("Catalog",catalogs,index=0,key="catalog")

if selected_catalog != catalog_placeholder:
    schemas = get_schemas(conn, selected_catalog) or []
else:
    schemas = []

schema_placeholder = "select schema"
schemas = [schema_placeholder] + schemas

with col2:
    selected_schema = st.selectbox("Schema", schemas, index=0, key="schema")

if selected_schema != schema_placeholder:
    tables = get_tables(conn, selected_catalog, selected_schema) or []
else:
    tables = []

table_placeholder = "select table"
tables = [table_placeholder] + tables

with col3:
    selected_table = st.selectbox("Table", tables, index=0, key="table")

with col4:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_all()   


column_placeholder = "Select columns (leave empty to select all)"
selected_columns = []
if (
    selected_catalog != catalog_placeholder
    and selected_schema != schema_placeholder
    and selected_table != table_placeholder
):
    try:
        available_columns = get_columns_list(conn, selected_catalog, selected_schema, selected_table) or []
        # st.session_state["available_columns"] = available_columns
    except Exception as e:
        available_columns = []
        st.warning(f"Could not fetch columns: {e}")

    if available_columns:
        # if "selected_columns" not in st.session_state:
        #     st.session_state["selected_columns"] = available_columns.copy()

        selected_columns = st.multiselect(column_placeholder, options=available_columns, key="selected_columns")
        
        selected_columns = (selected_columns if selected_columns else available_columns)
    else:
        st.info("No columns found for the selected table.")
else:
    st.info("Please select catalog, schema and table to choose columns.")


# st.write(f"selected catalog: {selected_catalog}")
# st.write(f"selected schema: {selected_schema}")
# st.write(f"selected table: {selected_table}")
# st.write(f"selected column: {selected_columns}")

if st.button("Submit"):
    if selected_table == table_placeholder:
        st.error("Select a table first.")
    else:
        try:
            st.session_state["submitted"] = True
            st.session_state["selected_catalog"] = selected_catalog
            st.session_state["selected_schema"] = selected_schema
            st.session_state["selected_table"] = selected_table
            # st.session_state["selected_columns"] = selected_columns

            st.session_state["metadata_rules_df"] = None
            st.session_state["generated_rules_df"] = None
            st.session_state["archived_rules_df"] = None

            #work: on the check metada
            result = check_metadata_for_table(selected_catalog, selected_schema, selected_table,selected_columns)
            st.session_state["metadata_check_result"] = result

            if not result.get("meta_found"):
                st.warning("No metadata found for this table.")
                st.session_state["metadata_rules_df"] = None

            else:
                validation_rules = result["meta_record"].get("validation_rules", [])
                df = rules_json_to_dataframe(validation_rules)
                save_columns_with_list_values(df)

                st.session_state["metadata_rules_df"] = df
                if "rule_index" in df.columns:
                    st.session_state["metadata_selected_rules_indexes"] = (
                        df["rule_index"]
                        .dropna()
                        .astype(int)
                        .tolist()
                    )
                else:
                    st.session_state["metadata_selected_rules_indexes"] = []
                added_cols = result.get("added_columns", [])
                removed_cols = result.get("removed_columns", [])
        #work: falsi's code should be here work on that

                if removed_cols:
                    active_df, archived_df = archive_rules_for_removed_columns(df, removed_cols)
                    save_columns_with_list_values(active_df)
                    st.session_state["metadata_rules_df"] = active_df
                    if "rule_index" in active_df.columns:
                        st.session_state["metadata_selected_rules_indexes"] = (
                            active_df["rule_index"]
                            .dropna()
                            .astype(int)
                            .tolist()
                        )
                    else:
                        st.session_state["metadata_selected_rules_indexes"] = []                        
                    st.session_state["archived_rules_df"] = archived_df

                    st.warning(f"Removed {len(archived_df)} rules due to removed columns.")
                    st.session_state["warning"] = f"Removed {len(archived_df)} rules due to removed columns."
                else:
                    st.session_state["metadata_rules_df"] = df
                    if "rule_index" in df.columns:
                        st.session_state["metadata_selected_rules_indexes"] = (
                            df["rule_index"]
                            .dropna()
                            .astype(int)
                            .tolist()
                        )
                    else:
                        st.session_state["metadata_selected_rules_indexes"] = []                        

                if added_cols:
                    st.info(f"New columns detected: {added_cols}")

                st.success("Metadata rules loaded successfully.")
        except Exception as e:
            st.error(f"Metadata check failed: {e}")
            st.session_state["submitted"] = False

if st.session_state.get("warning") is not None:
    st.warning(st.session_state.get("warning"))


if (st.session_state.get("submitted") and st.session_state.get("metadata_rules_df") is not None):
    
    render_rules_grid(
        rules_df_key = "metadata_rules_df",
        title = "Existing Validation Rules (from Metadata)",
        grid_version_key = "grid_version",
        grid_version_prefix  = "metadata_grid_rules",
        selected_rules_indexes_key = "metadata_selected_rules_indexes",
        selected_rules_key = "metadata_selected_rules"
    )

#  RULE GENERATION SECTION (AFTER SUBMIT) 

meta_result = st.session_state.get("metadata_check_result")

if st.session_state.get("submitted") and meta_result:

    st.markdown("---")
    st.subheader("🤖 Generate New Validation Rules")

    prompt = st.text_area(
        "Prompt (optional)",
        placeholder="Describe any specific validation rules you want"
    )

    # --
    # CASE 1: NO METADATA EXISTS
    # --
    if not meta_result.get("meta_found", False):

        if st.button("Generate rules for selected columns"):
            try:
                ai_rules = generate_checks_by_checking_column_list(
                    st.session_state["selected_catalog"],
                    st.session_state["selected_schema"],
                    st.session_state["selected_table"],
                    "databricks/databricks-claude-sonnet-4-5",
                    prompt,
                    st.session_state["selected_columns"]
                )

                df = rules_json_to_dataframe(get_idx_json(ai_rules))
                save_columns_with_list_values(df)

                st.session_state["generated_rules_df"] = df
                st.success("Rules generated successfully.")

            except Exception as e:
                st.error(f"Rule generation failed: {e}")

    # --
    # CASE 2: METADATA EXISTS
    # --
    else:
        added_cols = meta_result.get("added_columns", [])

        # Show checkbox only if new columns exist
        generate_for_all = False
        if added_cols:
            generate_for_all = st.checkbox(
                "Generate rules for all selected columns (unchecked = only new columns)",
                value=False
            )

        if st.button("Generate new rules"):
            try:
                target_columns = (
                    st.session_state["selected_columns"]
                    if generate_for_all or not added_cols
                    else added_cols
                )

                ai_rules = generate_checks_by_checking_column_list(
                    st.session_state["selected_catalog"],
                    st.session_state["selected_schema"],
                    st.session_state["selected_table"],
                    "databricks/databricks-claude-sonnet-4-5",
                    prompt,
                    target_columns
                )

                df = rules_json_to_dataframe(get_idx_json(ai_rules))
                save_columns_with_list_values(df)

                st.session_state["generated_rules_df"] = df
                st.success("New rules generated successfully.")

            except Exception as e:
                st.error(f"Rule generation failed: {e}")



# --
# GENERATED RULES GRID (AFTER GENERATION)
# --
if (
    st.session_state.get("submitted")
    and st.session_state.get("generated_rules_df") is not None
):
    render_rules_grid(
        rules_df_key = "generated_rules_df",
        title = "🤖 Newly Generated Validation Rules",
        grid_version_key = "grid_version",
        grid_version_prefix  = "generated_grid_rules",
        selected_rules_indexes_key = "generated_selected_rules_indexes",
        selected_rules_key = "generated_selected_rules"
    )

# -----
# COMBINE SELECTED RULES (METADATA + GENERATED)
# -----

if st.session_state.get("submitted", False):
    st.markdown("---")
    selected_rules_combined = get_selected_rules_combined()

    #work: check if this work outside properly
    # st.session_state["has_invalid_selected_rules"] = False
    # st.session_state["ui_rules_json"] = None

    if selected_rules_combined.empty:
        st.subheader("Selected Rules")
        st.info("No rules selected")
        st.session_state["has_invalid_selected_rules"] = False
        st.session_state["ui_rules_json"] = None

    else:
        st.subheader("Selected Rules")

        st.success(f"{len(selected_rules_combined)} rules selected for processing.")
        selected_rules_combined = selected_rules_combined.drop(columns=["rule_index"])
        st.dataframe(selected_rules_combined)

        has_invalid = has_invalid_values(selected_rules_combined)
        st.session_state["has_invalid_selected_rules"] = has_invalid

        if has_invalid:
            st.error(
                "❌ Some selected rules contain empty required values.\n\n"
                "Please fill in all required fields or deselect the affected rows before saving."
            )
        else:
            if "rule_index" in selected_rules_combined.columns:
                selected_rules_combined = selected_rules_combined.drop(columns=["rule_index"])

            rename_col_map = st.session_state.get("rename_col_map", {})
            final_df_for_json = convert_df_suitable_for_json(
                selected_rules_combined,
                rename_col_map
            )
            json_data = unflatten_df_to_json(final_df_for_json, "!#!")
            st.session_state["ui_rules_json"] = json_data
            # st.write(json_data)
    # # Work on a copy to avoid mutating source data
    # final_selected_df = selected_rules_combined.copy()

    # # -
    # # Normalize list-based columns (AG-Grid → backend format)
    # # -
    # for col in st.session_state.get("columns_with_list_values", []):
    #     if col in final_selected_df.columns:
    #         final_selected_df[col] = final_selected_df[col].apply(string_to_list)

    # st.success(f"{len(final_selected_df)} rules selected for processing.")
    # st.dataframe(final_selected_df)

    # # -
    # # Validate required fields
    # # -
    # has_invalid = has_invalid_values(final_selected_df)
    # st.session_state["has_invalid_selected_rules"] = has_invalid

    # if has_invalid:
    #     st.error(
    #         "❌ Some selected rules contain empty required values.\n\n"
    #         "Please fill in all required fields or deselect the affected rows "
    #         "before saving."
    #     )

    # else:
    #     # --------
    #     # Prepare DF for JSON conversion
    #     # --------
    #     rename_col_map = st.session_state.get("rename_col_map", {})

    #     df_for_json = convert_df_suitable_for_json(
    #         final_selected_df,
    #         rename_col_map
    #     )

    #     # Rule index must NOT go to metadata JSON
    #     df_for_json = df_for_json.drop(columns=["rule_index"], errors="ignore")

    #     # --------
    #     # Convert DF → JSON (final backend format)
    #     # --------
    #     ui_rules_json = unflatten_df_to_json(df_for_json, "!#!")

    #     st.session_state["ui_rules_json"] = ui_rules_json





















# -----
# ➕ ADD NEW RULE (VISIBLE AFTER SUBMIT)
# -----

if st.session_state.get("submitted", False):

    st.markdown("---")
    st.markdown("### ➕ Add new rule")


    next_idx, df_name_for_new_rule = get_next_rule_index_and_target()


    try:
        current_cols = get_columns_list(
            conn,
            st.session_state["selected_catalog"],
            st.session_state["selected_schema"],
            st.session_state["selected_table"]
        )
    except Exception:
        current_cols = []

    new_column = st.selectbox(
        "Column name",
        current_cols,
        key="new_rule_column"
    )


    new_criticality = st.selectbox(
        "Criticality",
        ["error", "warn"],
        index=0,
        key="new_rule_criticality"
    )


    function_options = get_all_check_rules()
    new_function = st.selectbox(
        "Rule name",
        function_options,
        key="new_function"
    )


    new_min = None
    new_max = None
    new_expression = ""
    new_regex = ""
    new_allowed = None  # IMPORTANT: default is None

    if new_function == "is_in_range":
        st.write("Put range limits:")

        new_min = st.number_input(
            "Min value",
            key="new_rule_min_number",
            format="%f"
        )
        new_max = st.number_input(
            "Max value",
            key="new_rule_max_number",
            format="%f"
        )

        if new_min is not None and new_max is not None:
            if float(new_min) > float(new_max):
                st.warning("Min is greater than Max — please check the limits.")
            else:
                st.info(f"Range set: {new_min} — {new_max}")

    elif new_function == "sql_expression":
        new_expression = st.text_input(
            "SQL expression (Please give sql_expression)",
            key="new_rule_expression"
        )

    elif new_function == "regex_match":
        new_regex = st.text_input(
            "Regex pattern (Please give regex pattern)",
            key="new_rule_regex"
        )

        if new_regex.strip():
            meta_chars = r".^$*+?{}[]\|()"
            try:
                re.compile(new_regex)
                if not any(c in new_regex for c in meta_chars):
                    st.warning(
                        "This pattern has no regex operators — it will match literal text."
                    )
                else:
                    st.success("Regex pattern looks valid.")
            except re.error as err:
                st.error(f"Invalid regex syntax: {err}")

    elif new_function == "is_in_list":
        new_allowed = st.text_input(
            "Allowed values (comma-separated)",
            key="new_rule_allowed"
        )

    else:
        st.info("No extra parameters needed for this rule type.")


    if st.button("Add rule", key="btn_add_rule"):

        errors = []

        if not new_column:
            errors.append("Please select a column.")

        if new_function == "is_in_range":
            try:
                if float(new_min) > float(new_max):
                    errors.append("Min cannot be greater than Max.")
            except Exception:
                errors.append("Min and Max must be numeric.")

        elif new_function == "sql_expression" and not new_expression.strip():
            errors.append("SQL expression is required.")

        elif new_function == "regex_match":
            if not new_regex.strip():
                errors.append("Regex is required.")

        elif new_function == "is_in_list" and not new_allowed:
            errors.append("Allowed values are required.")

        if errors:
            for msg in errors:
                st.warning(msg)

        else:
            #work: if is_unique function then put this into the COLUMNS rather than the column
            new_row = {
                "rule_index": next_idx,
                "criticality": new_criticality,
                "function": new_function,
                "column": new_column,
                "expression": None,
                "regex": None,
                "allowed": None,
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

            # Push to session
            st.session_state["pending_new_rule"] = new_row
            st.session_state["is_adding_rule"] = True
            st.session_state["last_added_rule_index"] = int(next_idx)
            st.session_state["grid_version"] = (
                st.session_state.get("grid_version", 0) + 1
            )

            st.success(f"Added new rule with index {next_idx}.")
            st.rerun()


    
    # # ================= TARGET & QUARANTINE INPUTS =================
    # st.markdown("---")
    # st.markdown("### 🎯 Output Configuration")

    # col1, col2 = st.columns(2)

    # with col1:
    #     target_table = st.text_input(
    #         "Target Table (catalog.schema.table)",
    #         placeholder="eg: dq_results.prod.patient_rules",
    #         key="target_table_input"
    #     )

    # with col2:
    #     quarantine_table = st.text_input(
    #         "Quarantine Table (catalog.schema.table)",
    #         placeholder="eg: dq_quarantine.prod.patient_quarantine",
    #         key="quarantine_table_input"
    #     )

# =============================================================
# SAVE CONFIGURATION (VISIBLE AFTER SUBMIT)
# =============================================================

if st.session_state.get("submitted", False):

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

    # --
    # SAVE APPLIED RULES
    # --
    save_disabled = (
        st.session_state.get("has_invalid_selected_rules", True)
        or st.session_state.get("ui_rules_json") is None
    )

    if st.button(
        "Save Applied Rules",
        key="btn_save_applied_rules",
        disabled=save_disabled
    ):
        try:
            if not target_table or not quarantine_table:
                st.warning(
                    "Please provide both Target and Quarantine table details."
                )
            else:
                # Split target & quarantine tables
                op_catalog, op_schema, op_table = target_table.split(".")
                qt_catalog, qt_schema, qt_table = quarantine_table.split(".")

                # Call insert / update
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
                    ui_rules_json=st.session_state["ui_rules_json"]
                )

                if result.get("status") == "success":
                    st.success("Applied rules saved successfully.")
                else:
                    st.error(
                        f"Failed to save applied rules: {result.get('message')}"
                    )

        except ValueError:
            st.error(
                "Please enter table names in catalog.schema.table format."
            )
        except Exception as e:
            st.error(f"Failed to save applied rules falsi: {e}")