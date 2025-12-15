import streamlit as st
import pandas as pd
import json

def rules_json_to_dataframe(rules_json):
    """
    Flatten the rules JSON into a pandas DataFrame using json_normalize (Optimized).
    """

    if isinstance(rules_json, list) and len(rules_json) > 0 and isinstance(rules_json[0], dict):
        rules_map = rules_json[0]
    elif isinstance(rules_json, dict):
        rules_map = rules_json
    else:
        return pd.DataFrame(), []
 
    if not rules_map:
        return pd.DataFrame(), []
 
    df = pd.json_normalize(list(rules_map.values()))
 
    # 3. Rename Columns: Clean up dot notation (e.g., 'check.arguments.column' -> 'column')
    # We take the last part of the key to keep names simple
    df.columns = [col.split('.')[-1] for col in df.columns]
 
    # 4. Add Index Column (from the keys of the dictionary)
    df['rule_index'] = list(rules_map.keys())
 
    # 5. Safe Reorder: Priority columns first, others appended
    # We filter 'preferred_order' to only include columns that actually exist in the data
    preferred_order = ['rule_index', 'column', 'function', 'criticality', 'columns']
    existing_preferred = [c for c in preferred_order if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in preferred_order]
    # Combine lists to form final column order
    df = df[existing_preferred + remaining_cols]
 
    return df

def load_rules_for_selected_table():

    ## If Rules already present in our table then display that rules or for first time Rules comes from the DQX function.
    
    sample_rules = [
       {0: {'criticality': 'error', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'PATIENT_ID', 'trim_strings': True}}}, 1: {'criticality': 'error', 'check': {'function': 'is_unique', 'arguments': {'columns': ['PATIENT_ID']}}}, 2: {'criticality': 'error', 'check': {'function': 'regex_match', 'arguments': {'column': 'PATIENT_ID', 'regex': '^[A-Z0-9_-]+$'}}}, 3: {'criticality': 'error', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'FIRST_NAME', 'trim_strings': True}}}, 4: {'criticality': 'error', 'check': {'function': 'regex_match', 'arguments': {'column': 'FIRST_NAME', 'regex': "^[A-Za-z][A-Za-z\\s'-]*$"}}}, 5: {'criticality': 'error', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'LAST_NAME', 'trim_strings': True}}}, 6: {'criticality': 'error', 'check': {'function': 'regex_match', 'arguments': {'column': 'LAST_NAME', 'regex': "^[A-Za-z][A-Za-z\\s'-]*$"}}}, 7: {'criticality': 'error', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'DATE_OF_BIRTH', 'trim_strings': True}}}, 8: {'criticality': 'error', 'check': {'function': 'is_valid_date', 'arguments': {'column': 'DATE_OF_BIRTH'}}}, 9: {'criticality': 'error', 'check': {'function': 'sql_expression', 'arguments': {'expression': 'DATE_OF_BIRTH <= CURRENT_DATE()', 'columns': ['DATE_OF_BIRTH']}}}, 10: {'criticality': 'warn', 'check': {'function': 'is_in_range', 'arguments': {'column': 'AGE', 'min_limit': 0, 'max_limit': 120}}}, 11: {'criticality': 'error', 'check': {'function': 'sql_expression', 'arguments': {'expression': 'AGE = FLOOR(DATEDIFF(CURRENT_DATE(), TO_DATE(DATE_OF_BIRTH)) / 365.25)', 'columns': ['AGE', 'DATE_OF_BIRTH']}}, 'filter': 'DATE_OF_BIRTH IS NOT NULL AND AGE IS NOT NULL'}, 12: {'criticality': 'error', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'GENDER', 'trim_strings': True}}}, 13: {'criticality': 'error', 'check': {'function': 'is_in_list', 'arguments': {'column': 'GENDER', 'allowed': ['M', 'F', 'Male', 'Female', 'O', 'Other', 'U', 'Unknown'], 'case_sensitive': False}}}, 14: {'criticality': 'warn', 'check': {'function': 'regex_match', 'arguments': {'column': 'CONTACT_NUMBER', 'regex': '^[+]?[0-9\\s()-]{7,20}$'}}, 'filter': 'CONTACT_NUMBER IS NOT NULL'}, 15: {'criticality': 'warn', 'check': {'function': 'regex_match', 'arguments': {'column': 'EMAIL', 'regex': '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'}}, 'filter': 'EMAIL IS NOT NULL'}, 16: {'criticality': 'warn', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'ADDRESS_LINE1', 'trim_strings': True}}}, 17: {'criticality': 'warn', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'CITY', 'trim_strings': True}}}, 18: {'criticality': 'warn', 'check': {'function': 'regex_match', 'arguments': {'column': 'CITY', 'regex': "^[A-Za-z][A-Za-z\\s.'-]*$"}}, 'filter': 'CITY IS NOT NULL'}, 19: {'criticality': 'warn', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'STATE', 'trim_strings': True}}}, 20: {'criticality': 'warn', 'check': {'function': 'regex_match', 'arguments': {'column': 'STATE', 'regex': '^[A-Z]{2}$|^[A-Za-z\\s]+$'}}, 'filter': 'STATE IS NOT NULL'}, 21: {'criticality': 'warn', 'check': {'function': 'regex_match', 'arguments': {'column': 'POSTAL_CODE', 'regex': '^[0-9]{5}(-[0-9]{4})?$|^[A-Z][0-9][A-Z]\\s?[0-9][A-Z][0-9]$'}}, 'filter': 'POSTAL_CODE IS NOT NULL'}, 22: {'criticality': 'error', 'check': {'function': 'is_not_null', 'arguments': {'column': 'ADMISSION_DATE'}}}, 23: {'criticality': 'error', 'check': {'function': 'is_not_in_future', 'arguments': {'column': 'ADMISSION_DATE', 'offset': 0}}}, 24: {'criticality': 'warn', 'check': {'function': 'sql_expression', 'arguments': {'expression': 'DISCHARGE_DATE IS NULL OR DISCHARGE_DATE >= ADMISSION_DATE', 'columns': ['ADMISSION_DATE', 'DISCHARGE_DATE']}}}, 25: {'criticality': 'warn', 'check': {'function': 'is_not_in_future', 'arguments': {'column': 'DISCHARGE_DATE', 'offset': 0}}, 'filter': 'DISCHARGE_DATE IS NOT NULL'}, 26: {'criticality': 'error', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'DEPARTMENT', 'trim_strings': True}}}, 27: {'criticality': 'warn', 'check': {'function': 'is_not_null_and_not_empty', 'arguments': {'column': 'REASON_FOR_ADMISSION', 'trim_strings': True}}}}
    ]
    
    try:
        rules_df = rules_json_to_dataframe(sample_rules)

        list_columns = [
            col
            for col in rules_df.columns
            if rules_df[col].apply(lambda v: isinstance(v, list)).any()
        ]

        st.session_state.columns_with_list_values = list_columns
        st.session_state.rules_df = rules_df.copy()

    except Exception as e:
        st.error(f"Failed to parse rules JSON: {e}")