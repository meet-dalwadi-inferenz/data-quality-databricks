import streamlit as st
import pandas as pd
import json
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, StAggridTheme
from conn import create_connection
from db import get_catalogs, get_schemas, get_tables, preview_table
from rules import load_rules_for_selected_table
from helper_functions import list_to_string, normalize_allowed, reorder_rule_columns, unified_column

st.set_page_config(layout="wide")
st.title("select catalog, schema, table")

@st.cache_resource # connection is cached
def get_connection():
    return create_connection()


if "rules_df" not in st.session_state:
    st.session_state["rules_df"] = None
    
conn = get_connection()
catalogs = get_catalogs(conn)
catalog_placeholder = "select catalog"
catalogs = [catalog_placeholder] + catalogs
selected_catalog = st.selectbox("catalog", catalogs, index=0)

if selected_catalog != catalog_placeholder:
    schemas = get_schemas(conn, selected_catalog) or []
else : 
    schemas = []

schema_placeholder = "select schema"
schemas = [schema_placeholder] + schemas
selected_schema = st.selectbox("schema", schemas, index=0)

if selected_schema != schema_placeholder:
    tables = get_tables(conn, selected_catalog, selected_schema) or []
else :
    tables = []

table_placeholder = "select table"
tables = [table_placeholder] + tables
selected_table = st.selectbox("table", tables, index=0)

st.write(f"selected catalog: {selected_catalog}, schema: {selected_schema}, table: {selected_table}")

## display table preview by clicking on the preview button
if st.button("Preview Table"):
    if not (selected_catalog == catalog_placeholder or selected_schema == schema_placeholder or selected_table == table_placeholder):
        with st.spinner("Loading table preview..."):
            rows,columns,error = preview_table(conn, selected_catalog, selected_schema, selected_table)
            if error : 
                st.error(f"Error while previewing table : {error}")
            else :
                df = pd.DataFrame(rows,columns=columns)
                st.dataframe(df)
    else : 
        st.error("Please choose valid catalog, schema and table before previewing.")


if st.button("Submit"):
    if not (selected_catalog == catalog_placeholder or selected_schema == schema_placeholder or selected_table == table_placeholder):

            st.session_state.selected_catalog = selected_catalog
            st.session_state.selected_schema = selected_schema
            st.session_state.selected_table = selected_table

            ## Send the catalog.schema.table for Quality Check
            ## Returned Json Data
            load_rules_for_selected_table()

            
    else:
            st.error("Please choose valid catalog, schema and table before submitting.")


rules_df = st.session_state.rules_df

if rules_df is not None:
    st.subheader("Applied Rules on the selected table")

    # rules_df = rules_df.copy()

    # if "selected" not in rules_df.columns:
    #     rules_df["selected"] = False
    
    # your helper functions
    rules_df = unified_column(rules_df)
    rules_df = reorder_rule_columns(rules_df)


    # edited_df = st.data_editor(
    #     rules_df,
    #     key="rules_editor",
    #     use_container_width=True,
    #     column_config={
    #         "selected": st.column_config.CheckboxColumn(
    #             "select Rule",
    #             help="Select the rules you want to apply",
    #             default=False,
    #         ),
    #         "criticality": st.column_config.SelectboxColumn(
    #             "rule criticality",
    #             help="select the criticality of the rule",
    #             width="medium",
    #             options=["error", "warn"],
    #             required=True,
    #         ),
    #     },
    #     # disabled=[c for c in rules_df.columns if c not in ["selected", "criticality"]],
    #     hide_index=True,
    # )

    temp_rules_df = rules_df.copy()

    if 'allowed' in temp_rules_df.columns:
        temp_rules_df['allowed'] = temp_rules_df['allowed'].apply(list_to_string)

    is_editable_allowed = JsCode("""
        function(params) {
            if (params.data.rule_name === 'is_in_list') {
                return true;
            } else {
                return false;
            }
        }
        """)
        
    is_editable_regex = JsCode("""
        function(params) {
            if (params.data.rule_name === 'regex_match') {
                return true;
            } else {
                return false;
            }
        }
        """)

    is_editable_expression = JsCode("""
        function(params){
            if (params.data.rule_name === 'sql_expression'){
                return true;
            }
            else {
                false;
            }
        } 
    """)

    id_editable_min_limit = JsCode("""
        function(params) {
            if (params.data.rule_name === 'is_in_range' || params.data.rule_name === 'is_aggr_not_less_than')
            {
                return true;
            }
            else {
                return false;
            }
            }
        """)

    is_editable_max_limit = JsCode("""
                        function(params) {
                            if (params.data.rule_name === 'is_in_range' || params.data.rule_name === 'is_aggr_not_greater_than')
                            {
                                return true;
                                }
                            else {
                                return false;
                                }
                            }
                        """)

    gb = GridOptionsBuilder.from_dataframe(rules_df)
    gb.configure_selection("multiple", use_checkbox=True)
    gb.configure_column(
        "criticality",
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": ["error", "warn"]},
    )
    gb.configure_column("allowed",
                        cellDataType="text",
                         editable=is_editable_allowed)
    gb.configure_column("regex", editable=is_editable_regex)
    gb.configure_column("trim_strings",editable=True)
    gb.configure_column("expression", editable=is_editable_expression)
    gb.configure_column("min_limit", editable=id_editable_min_limit)
    gb.configure_column("max_limit", editable=is_editable_max_limit)
    gb.configure_column("case_sensitive", editable=True, cellDataType='boolean')
    gb.configure_column("divy_kaila",editable=True)

    grid_options = gb.build()

    custom_theme = (  
            StAggridTheme(base="quartz") 
            .withParams(
                selectedRowBackgroundColor="rgba(0, 128, 0, 0.3)", 
                rowBorder=True, 
                columnBorder=True,
                borderColor="#9ca3af"              
            )    
        )

    grid_return = AgGrid(
        temp_rules_df,
        gridOptions=grid_options,
        allow_unsafe_jscode=True,
        update_mode=GridUpdateMode.MODEL_CHANGED,   # send back edits
        data_return_mode="AS_INPUT",
        theme=custom_theme
    )

    selected_data = grid_return.get("selected_data")

    if selected_data is None or selected_data.empty:
        st.info("No rules selected!")
    else:
        st.success(f"{len(selected_data)} rules selected for processing.")
        st.dataframe(selected_data)

    # if st.button("View Selected Rules"):
    # selected_df = edited_df[edited_df["selected"] == True].copy()

    # if selected_df.empty:
    #     st.info("No rules selected!")
    # else:
    #     st.success(f"{len(selected_df)} rules selected for processing.")
    #     st.dataframe(selected_df, use_container_width=True)

    st.markdown("---")



    # # mapping: for a given rule_name, which fields are editable
    # EDITABLE_BY_RULE = {
    #     "is_in_list":     ["allowed"],
    #     "regex_match":    ["regex"],
    #     "is_in_range":    ["min_limit", "max_limit"],
    #     "sql_expression": ["expression"],
    #     # other rule types -> no editable fields by default
    # }

    # # build dropdown of rules to edit (based on the latest edited_df)
    # rule_options = [
    #     f"{idx} | {row['column']} | {row['rule_name']}"
    #     for idx, row in edited_df.iterrows()
    # ]

    # chosen = st.selectbox(
    #     "Edit a specific rule (optional)",
    #     ["-- select rule --"] + rule_options,
    # )

    # if chosen != "-- select rule --":
    #     # parse the index from "idx | column | rule_name"
    #     edit_idx = int(chosen.split(" | ")[0])
    #     row = edited_df.loc[edit_idx]

    #     st.subheader(f"Edit Rule {row['rule_index']} for column {row['column']}")
    #     st.write(f"Rule type: `{row['rule_name']}`")

    #     rule_type = row["rule_name"]
    #     editable_cols = set(EDITABLE_BY_RULE.get(rule_type, []))

    #     # always read-only:
    #     fixed_cols = {"rule_index", "column", "rule_name", "selected", "raw_rule"}

    #     new_values = {}

    #     for col in edited_df.columns:
    #         val = row[col]

    #         # fixed fields: always read-only
    #         if col in fixed_cols:
    #             st.text_input(
    #                 col,
    #                 value="" if val is None else str(val),
    #                 disabled=True,
    #                 key=f"{col}_{edit_idx}_ro",
    #             )
    #             continue

    #         # editable only if this column is allowed for this rule type
    #         if col in editable_cols:
    #             # choose widget based on current type
    #             if isinstance(val, bool):
    #                 new_values[col] = st.checkbox(
    #                     col,
    #                     value=bool(val),
    #                     key=f"{col}_{edit_idx}",
    #                 )
    #             elif isinstance(val, (int, float)) and not isinstance(val, bool):
    #                 new_values[col] = st.number_input(
    #                     col,
    #                     value=float(val),
    #                     key=f"{col}_{edit_idx}",
    #                 )
    #             elif isinstance(val, list):
    #                 s = ", ".join(map(str, val))
    #                 txt = st.text_input(
    #                     f"{col} (comma-separated)",
    #                     value=s,
    #                     key=f"{col}_{edit_idx}",
    #                 )
    #                 new_values[col] = [x.strip() for x in txt.split(",") if x.strip()]
    #             else:
    #                 new_values[col] = st.text_input(
    #                     col,
    #                     value="" if val is None else str(val),
    #                     key=f"{col}_{edit_idx}",
    #                 )
    #         else:
    #             # any other dynamic column: show as read-only
    #             st.text_input(
    #                 col,
    #                 value="" if val is None else str(val),
    #                 disabled=True,
    #                 key=f"{col}_{edit_idx}_ro2",
    #             )

    #     if new_values and st.button("Save changes for this rule"):
    #         # apply changes on top of the latest table state
    #         updated_df = edited_df.copy()
    #         for c, v in new_values.items():
    #             updated_df.at[edit_idx, c] = v

    #         # store back to session so next rerun uses updated rules
    #         st.session_state.rules_df = updated_df
    #         st.success("Rule updated")
    #         st.experimental_rerun()