import streamlit as st
import pandas as pd
import json
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, StAggridTheme, DataReturnMode
from helper.rules import save_columns_with_list_values
from helper.helper_functions import list_to_string, string_to_list, reorder_rule_columns

def render_rules_grid(
    rules_df_key : str,
    title : str,
    grid_version_key : str,
    grid_version_prefix : str,
    selected_rules_indexes_key : str,
    selected_rules_key : str
) :
    
    rules_df = st.session_state.get(rules_df_key, None)

    if rules_df is not None :
        st.subheader(title)

        pending = st.session_state.get("pending_new_rule", None)
        if pending is not None:
            pending_df = pd.DataFrame([pending])
            rules_df = pd.concat([rules_df, pending_df], ignore_index=True)
            st.session_state[rules_df_key] = rules_df
            st.session_state.pending_new_rule = None

        save_columns_with_list_values(rules_df)
        rules_df = reorder_rule_columns(rules_df)
        st_aggrid_rules_df = rules_df.copy()

        if "columns_with_list_values" in st.session_state:
            for col in st.session_state.columns_with_list_values:
                if col in st_aggrid_rules_df.columns:
                    st_aggrid_rules_df[col] = st_aggrid_rules_df[col].apply(list_to_string)
        
        if "rule_index" in st_aggrid_rules_df.columns:
            st_aggrid_rules_df["rule_index"] = pd.to_numeric(
                st_aggrid_rules_df["rule_index"],
                errors="coerce"
            ).fillna(-1).astype(int)

        st_aggrid_rules_df = st_aggrid_rules_df.reset_index(drop=True)
        
        is_editable_when_value_present = JsCode(
            """
                function(params) {
                    // safety checks
                    console.log('editable params', params);

                    if (!params || !params.data || !params.colDef || !params.colDef.field ) return false;

                    var field = params.colDef.field;
                    var v = params.data[field]; 
                    
                    if (v === null || v === undefined) return false;

                    if (typeof v === "boolean") {
                            return true;
                        }

                    if (typeof v === "string") {
                        return v.trim().length > 0;
                    }
                    return true;
                }
                """
        )
    

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

        meta_cols = {"rule_index", "criticality", "function", "column", "columns"}
        argument_cols = [c for c in st_aggrid_rules_df.columns if c not in meta_cols]

        gb = GridOptionsBuilder.from_dataframe(st_aggrid_rules_df)
        gb.configure_selection("multiple", use_checkbox=True)
        
        saved_ids = st.session_state.get(selected_rules_indexes_key, [])
        saved_ids_str = [str(x) for x in saved_ids]

        last_added_rule_index = st.session_state.get("last_added_rule_index", None)
        last_added_rule_index_str = str(last_added_rule_index) if last_added_rule_index is not None else None

        on_row_data_updated = JsCode(
            f"""
            function(params) {{
                const saved = {saved_ids_str};
                const last_added = {json.dumps(str(last_added_rule_index))};

                console.log("Saved IDs:", saved);
                console.log("Last added:", last_added);

                params.api.forEachNode(function(node) {{

                    console.log(
                        "Row index => rule_index:", 
                        node.data?.rule_index, 
                        ", type:", typeof node.data?.rule_index
                    );

                    // Try matching old selections
                    for (var i = 0; i < saved.length; i++) {{
                        if (String(node.data.rule_index) == String(saved[i])) {{
                            console.log("MATCH OLD => selecting:", node.data.rule_index);
                            node.setSelected(true);
                        }}
                    }}

                    // Try matching new row
                    if (node.data && last_added && String(node.data.rule_index) === last_added) {{
                        console.log("MATCH NEW => selecting:", node.data.rule_index);
                        node.setSelected(true);
                    }}
                }});
            }}
            """
        )

        gb.configure_grid_options(onRowDataUpdated=on_row_data_updated)
        st.session_state["last_added_rule_index"] = None

        column_configs = {
            "criticality": {
                "editable": True,
                "cellEditor": "agSelectCellEditor",
                "cellEditorParams": {"values": ["error", "warn"]},
            },
            "trim_strings": {"editable": is_editable_when_value_present,"cellDataType": "boolean"},
            "case_sensitive": {"editable": is_editable_when_value_present, "cellDataType": "boolean"},
            "filter":{"editable":True}
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

        grid_version = st.session_state.get(grid_version_key, 0)
        grid_key = f"{grid_version_prefix}_v{grid_version}"

        grid_return = AgGrid(
            st_aggrid_rules_df,
            gridOptions=grid_options,
            allow_unsafe_jscode=True,
            update_mode=GridUpdateMode.MODEL_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            theme=custom_theme,
            key=grid_key,
        )

        if grid_return.get("data") is not None:
            st.session_state[rules_df_key] = grid_return["data"]
        

        selected_rows = grid_return.get("selected_rows")

        is_adding_rule = st.session_state.get("is_adding_rule", False)
        prev = set(st.session_state.get(selected_rules_indexes_key, []))

        if isinstance(selected_rows, pd.DataFrame) and not selected_rows.empty:
            curr = set(selected_rows["rule_index"].astype(int).tolist())

            if curr != prev:
                st.session_state[selected_rules_indexes_key] = list(curr)
                st.rerun()

        # else:
        #     if prev and not is_adding_rule:
        #         st.session_state[selected_rules_indexes_key] = []
        #         st.rerun()
        
        selected_data_df = grid_return.get("selected_data")

        if isinstance(selected_data_df, pd.DataFrame) and not selected_data_df.empty:
            
            st.session_state.is_adding_rule = False

            if "columns_with_list_values" in st.session_state:
                for col in st.session_state.columns_with_list_values:
                    if col in selected_data_df.columns:
                        selected_data_df[col] = selected_data_df[col].apply(string_to_list)
            st.session_state[selected_rules_key] = selected_data_df
        
        else:
            st.session_state[selected_rules_key] = pd.DataFrame()
        


def get_selected_rules_combined():
    dfs = []

    meta = st.session_state.get("metadata_selected_rules")
    gen  = st.session_state.get("generated_selected_rules")

    # selected_rules_df = st.session_state.get("selected_rules")

    for df in [meta,gen]:
        if isinstance(df, list):
            df = pd.DataFrame(df)
        if isinstance(df, pd.DataFrame):
            dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)

    return combined




def get_next_rule_index_and_target():

    metadata_df = st.session_state.get("metadata_rules_df")
    generated_df = st.session_state.get("generated_rules_df")

    def max_index(df):
        if not isinstance(df, pd.DataFrame) or df.empty:
            return -1

        if "rule_index" not in df.columns:
            return -1

        return (
            pd.to_numeric(df["rule_index"], errors="coerce")
              .fillna(-1)
              .astype(int)
              .max()
        )

    # Priority 1: metadata
    if isinstance(metadata_df, pd.DataFrame):
        next_idx = max_index(metadata_df) + 1
        return next_idx, "metadata_rules_df"

    # Priority 2: generated
    if isinstance(generated_df, pd.DataFrame):
        next_idx = max_index(generated_df) + 1
        return next_idx, "generated_rules_df"

    return 0, "metadata_rules_df"