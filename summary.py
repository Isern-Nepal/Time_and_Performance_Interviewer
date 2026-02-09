import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.title("Interviewer Duration & Performance Dashboard")

uploaded_file = st.file_uploader("Upload your Survey Data", type=["csv", "xlsx"])

if uploaded_file is not None:

    # -----------------------------
    # Load data
    # -----------------------------
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    # -----------------------------
    # Time conversion & duration
    # -----------------------------
    df["Start_dt"] = pd.to_datetime(df["StartTime_TS"], errors="coerce", utc=True)
    df["End_dt"]   = pd.to_datetime(df["EndTime_TS"], errors="coerce", utc=True)

    df = df.dropna(subset=["Start_dt", "End_dt"])

    df["duration_minutes"] = (
        (df["End_dt"] - df["Start_dt"]).dt.total_seconds() / 60
    ).astype(int)

    df["duration_display"] = df["duration_minutes"].astype(str) + " min"

    # -----------------------------
    # Identify interviewer columns dynamically
    # -----------------------------
    prefixes = ["F", "M", "HH", "ORGHH", "C"]

    interviewer_name_cols = [
        c for c in df.columns
        if any(c.startswith(p) for p in prefixes) and c.endswith("IntName_W4")
    ]

    interviewer_id_cols = [
        c for c in df.columns
        if any(c.startswith(p) for p in prefixes) and c.endswith("IntID_W4")
    ]

    # ==========================================================
    #  PER-ID DURATION CHECK (DISPLAY FIRST)
    # ==========================================================
    st.subheader("Duration Check with Interviewer Info (Per Interview ID)")

    display_cols = (
        ["ID"]
        + interviewer_id_cols
        + interviewer_name_cols
        + ["Start_dt", "End_dt", "duration_minutes"]
    )

    st.dataframe(df[display_cols])

    # -----------------------------
    # Identify question columns
    # -----------------------------
    exclude_cols = (
        ["ID", "StartTime_TS", "EndTime_TS",
         "Start_dt", "End_dt",
         "duration_minutes", "duration_display"]
        + interviewer_name_cols
        + interviewer_id_cols
    )

    question_cols = [c for c in df.columns if c not in exclude_cols]

    df[question_cols] = df[question_cols].replace(r"^\s*$", np.nan, regex=True)

    # -----------------------------
    # DK / RF detection
    # -----------------------------
    def is_dk(val):
        if pd.isna(val):
            return False
        return str(val).strip().endswith("97")

    def is_rf(val):
        if pd.isna(val):
            return False
        return str(val).strip().endswith("99")
    
    def is_na(val):
        if pd.isna(val):
            return False
        return str(val).strip().endswith("98")

    df["DK_count"] = df[question_cols].apply(
        lambda row: sum(is_dk(v) for v in row),
        axis=1
    )

    df["RF_count"] = df[question_cols].apply(
        lambda row: sum(is_rf(v) for v in row),
        axis=1
    )

    df["NA_count"] = df[question_cols].apply(
        lambda row: sum(is_na(v) for v in row),
        axis=1
    )
    # -----------------------------
    # Build long interviewer table
    # -----------------------------
    all_interviewer_data = []

    for name_col in interviewer_name_cols:
        prefix = name_col.replace("IntName_W4", "")
        id_col = next(
            (c for c in interviewer_id_cols if c.startswith(prefix)),
            None
        )

        if id_col:
            temp = df[
                [id_col, name_col,
                 "duration_minutes", "DK_count", "RF_count", "NA_count"]
                + question_cols
            ].copy()

            temp = temp.rename(
                columns={id_col: "IntID", name_col: "IntName"}
            )

            temp["questions_answered"] = (
                temp[question_cols].notna().sum(axis=1)
            )

            all_interviewer_data.append(temp)

    long_df = pd.concat(all_interviewer_data, ignore_index=True)

    # -----------------------------
    # FINAL aggregation (ID-based) with min/max duration
    # -----------------------------
    final_df = (
        long_df
        .groupby("IntID", as_index=False)
        .agg(
            IntName=("IntName", "first"),
            total_interviews=("duration_minutes", "count"),
            avg_duration_minutes=("duration_minutes", "mean"),
            min_duration_minutes=("duration_minutes", "min"),
            max_duration_minutes=("duration_minutes", "max"),
            avg_questions=("questions_answered", "mean"),
            total_DK=("DK_count", "sum"),
            total_RF=("RF_count", "sum"),
            total_NA=("NA_count", "sum")
        )
    )

    # -----------------------------
    # Sort strictly by Interviewer ID
    # -----------------------------
    final_df["IntID_sort"] = pd.to_numeric(final_df["IntID"], errors="coerce")
    final_df = final_df.sort_values("IntID_sort").drop(columns="IntID_sort")

    # -----------------------------
    # Formatting
    # -----------------------------
    final_df["avg_duration_display"] = (
        final_df["avg_duration_minutes"].round(2).astype(str) + " min"
    )
    final_df["min_duration_display"] = (
        final_df["min_duration_minutes"].astype(int).astype(str) + " min"
    )
    final_df["max_duration_display"] = (
        final_df["max_duration_minutes"].astype(int).astype(str) + " min"
    )
    final_df["avg_questions"] = final_df["avg_questions"].round(0).astype(int)
    final_df["total_DK"] = final_df["total_DK"].astype(int)
    final_df["total_RF"] = final_df["total_RF"].astype(int)
    final_df["total_NA"] = final_df["total_NA"].astype(int)

    # ==========================================================
    #  AVERAGE DURATION & QUESTIONS PER INTERVIEWER (SECOND)
    # ==========================================================
    st.subheader("Interviewer Performance Summary")

    st.dataframe(
        final_df[
            ["IntID", "IntName", "total_interviews",
             "min_duration_display", "avg_duration_display", "max_duration_display",
             "avg_questions", "total_DK", "total_RF", "total_NA"]
        ]
    )

    # -----------------------------
    # Download & summary
    # -----------------------------
    col1, col2 = st.columns([1, 2])

    with col1:
        # Export to Excel instead of CSV
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            final_df.to_excel(writer, index=False, sheet_name='Interviewer Stats')
        buffer.seek(0)
        
        st.download_button(
            "Download Interviewer Stats Excel",
            data=buffer,
            file_name="interviewer_statistics.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with col2:
        st.markdown(
            f"""
            **Total interviews:** {len(df)}  
            **Overall average time:** {df["duration_minutes"].mean().round(2)} min
            """
        )