from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

import pandas as pd
import streamlit as st

from upas import UPAS_DF
from core.scraper import fetch_html
from core.parser import parse_upa_dashboard
from core.storage import get_cached, set_cached
from sidebar import render_sidebar
from settings import get_verify_ssl



st.set_page_config(page_title="UPAs DF - Filas (IGESDF)SCRAPE", layout="wide")


def _flatten_row(upa_nome: str, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "upa": upa_nome,
        "url": url,
        "updated_at": data.get("updated_at"),
        "pacientes_unidade": data.get("pacientes_unidade"),
        "pacientes_regulacao": data.get("pacientes_regulacao"),
        "pacientes_at_medico": data.get("pacientes_at_medico"),
    }

    classifs = data.get("classificacoes", {}) or {}
    for cor in ["AZUL", "VERDE", "AMARELO", "LARANJA", "VERMELHO"]:
        info = classifs.get(cor, {}) or {}
        row[f"{cor.lower()}_pacientes"] = info.get("pacientes")
        row[f"{cor.lower()}_tempo_medio"] = info.get("tempo_medio")

    return row


def _fetch_one(upa_nome: str, url: str, ttl: int) -> Dict[str, Any]:
    cached = get_cached(url, ttl_seconds=ttl)
    if cached:
        return _flatten_row(upa_nome, url, cached)

    res = fetch_html(url)
    parsed = parse_upa_dashboard(res.html)
    set_cached(url, parsed)
    return _flatten_row(upa_nome, url, parsed)


@st.cache_data(ttl=120, show_spinner=False)
def load_all_upas(ttl_storage: int = 120, max_workers: int = 6) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    items = list(UPAS_DF.items())
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_one, nome, url, ttl_storage): (nome, url) for nome, url in items}

        for fut in as_completed(futures):
            nome, url = futures[fut]
            try:
                rows.append(fut.result())
            except Exception as e:
                rows.append(
                    {
                        "upa": nome,
                        "url": url,
                        "updated_at": None,
                        "pacientes_unidade": None,
                        "pacientes_regulacao": None,
                        "pacientes_at_medico": None,
                        "azul_pacientes": None,
                        "azul_tempo_medio": None,
                        "verde_pacientes": None,
                        "verde_tempo_medio": None,
                        "amarelo_pacientes": None,
                        "amarelo_tempo_medio": None,
                        "laranja_pacientes": None,
                        "laranja_tempo_medio": None,
                        "vermelho_pacientes": None,
                        "vermelho_tempo_medio": None,
                        "erro": str(e),
                    }
                )

    df = pd.DataFrame(rows)

    # Ordena por nome e deixa colunas principais primeiro
    main = ["upa", "updated_at", "pacientes_unidade", "pacientes_regulacao", "pacientes_at_medico"]
    rest = [c for c in df.columns if c not in main]
    df = df[main + rest]
    df = df.sort_values("upa", kind="stable")
    return df


st.title("Filas de atendimento - UPAs DF (IGESDF)SCRAPE")
with st.expander("🔧 Debug (HTML do scraping)", expanded=False):
    debug_upa = st.selectbox("Escolha uma UPA para inspecionar", list(UPAS_DF.keys()))
    debug_url = UPAS_DF[debug_upa]
    if st.button("Rodar debug dessa UPA (sem cache)"):
        res = fetch_html(debug_url)
        html = res.html
        st.write("status_code:", res.status_code)
        st.write("html_len:", len(html))
        st.write("contém <svg:", "<svg" in html)
        st.write("contém svg.card:", "svg.card" in html)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        svgs = soup.select("svg.card[aria-label]")
        st.write("svg.card[aria-label] count:", len(svgs))
        st.write("aria-labels (até 15):", [s.get("aria-label") for s in svgs[:15]])

        # salva pra abrir no browser e comparar
        import os, re
        os.makedirs("debug_html", exist_ok=True)
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", debug_upa).strip("_")
        path = f"debug_html/{safe}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        st.success(f"HTML salvo em: {path}")


if not get_verify_ssl():
    st.warning("SSL verification DESLIGADO (VERIFY_SSL=false). Use só quando precisar.", icon="⚠️")
else:
    st.caption("SSL verification ligado (VERIFY_SSL=true).")


colA, colB, colC = st.columns([1, 1, 2])
with colA:
    ttl = st.number_input("TTL cache (segundos)", min_value=30, max_value=1800, value=120, step=30)
with colB:
    workers = st.number_input("Paralelismo (workers)", min_value=1, max_value=20, value=6, step=1)
with colC:
    if st.button("Atualizar agora (limpar cache do Streamlit)", type="primary"):
        st.cache_data.clear()
        st.toast("Cache do Streamlit limpo. Recarregando...", icon="🔄")

with st.spinner("Coletando dados..."):
    df = load_all_upas(ttl_storage=int(ttl), max_workers=int(workers))

df_f = render_sidebar(df)

st.subheader("Tabela")

# Coluna URL clicável + tabela full width (sem warning do Streamlit)
st.dataframe(
    df_f,
    width="stretch",
    hide_index=True,
    column_config={
        "url": st.column_config.LinkColumn("url", display_text="abrir"),
    },
)

st.download_button(
    "Baixar CSV (filtrado)",
    data=df_f.to_csv(index=False).encode("utf-8"),
    file_name="upas_df_filas.csv",
    mime="text/csv",
)

# Mostra erros, se houver
if "erro" in df_f.columns and df_f["erro"].notna().any():
    st.warning("Algumas UPAs falharam na coleta. Veja a coluna 'erro'.")
