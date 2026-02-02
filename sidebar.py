import streamlit as st
import pandas as pd


COLOR_OPTIONS = ["TODAS", "AZUL", "VERDE", "AMARELO", "LARANJA", "VERMELHO"]


def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filtros")

    upas = ["TODAS"] + sorted(df["upa"].dropna().unique().tolist())
    sel_upa = st.sidebar.selectbox("UPA", upas, index=0)

    sel_color = st.sidebar.selectbox("Classificação", COLOR_OPTIONS, index=0)

    only_nonzero = st.sidebar.checkbox("Mostrar apenas com pacientes > 0 (na classificação escolhida)", value=False)

    out = df.copy()

    if sel_upa != "TODAS":
        out = out[out["upa"] == sel_upa]

    if sel_color != "TODAS":
        col_pac = f"{sel_color.lower()}_pacientes"
        if col_pac in out.columns:
            if only_nonzero:
                out = out[out[col_pac].fillna(0).astype(int) > 0]

    return out
