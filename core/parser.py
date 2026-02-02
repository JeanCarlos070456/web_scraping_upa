# core/parser.py  (substitua pelo conteúdo completo abaixo)
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple, Iterable

from bs4 import BeautifulSoup


COLORS = ["AZUL", "VERDE", "AMARELO", "LARANJA", "VERMELHO"]


def _norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_updated_at(soup: BeautifulSoup) -> Optional[str]:
    text = soup.get_text(" ", strip=True)
    m = re.search(r"ATUALIZADO EM\s+(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", _norm(text))
    return m.group(1) if m else None


def _extract_time(text: str) -> Optional[str]:
    # 00:20:21 ou IMEDIATO
    m = re.search(r"\b(\d{2}:\d{2}:\d{2})\b", text)
    if m:
        return m.group(1)
    if "IMEDIATO" in _norm(text):
        return "IMEDIATO"
    return None


def _extract_int_candidates(text: str) -> Tuple[int, ...]:
    # remove timestamps HH:MM:SS antes de pegar números
    text2 = re.sub(r"\d{2}:\d{2}:\d{2}", " ", text)
    nums = re.findall(r"\b\d+\b", text2)
    return tuple(int(n) for n in nums) if nums else tuple()


def _pick_patient_count(*texts: str) -> Optional[int]:
    """
    Heurística robusta:
    - junta candidatos de inteiros (ignorando HH:MM:SS)
    - remove anos/datas gigantes (p. ex. 2026)
    - escolhe o primeiro "plausível" (0..9999)
    """
    ints: Iterable[int] = []
    all_candidates = []
    for t in texts:
        if t:
            all_candidates.extend(list(_extract_int_candidates(t)))

    # filtra coisas tipo 2026 (ano) e afins
    filtered = [n for n in all_candidates if 0 <= n <= 9999 and n not in (2020, 2021, 2022, 2023, 2024, 2025, 2026)]
    return filtered[0] if filtered else None


def _iter_aria_nodes(soup: BeautifulSoup):
    # Qualquer nó com aria-label (não só svg.card)
    for el in soup.select("[aria-label]"):
        aria = (el.get("aria-label") or "").strip()
        if aria:
            yield el, aria


def parse_upa_dashboard(html: str) -> Dict[str, Any]:
    """
    Retorna:
    - pacientes_unidade
    - pacientes_regulacao
    - pacientes_at_medico
    - classificacoes: {COR: {pacientes, tempo_medio}}
    - updated_at
    """
    soup = BeautifulSoup(html, "lxml")

    out: Dict[str, Any] = {
        "updated_at": _extract_updated_at(soup),
        "pacientes_unidade": None,
        "pacientes_regulacao": None,
        "pacientes_at_medico": None,
        "classificacoes": {c: {"pacientes": None, "tempo_medio": None} for c in COLORS},
    }

    # 1) Passo principal: varre TODOS os aria-labels
    for el, aria_raw in _iter_aria_nodes(soup):
        aria = _norm(aria_raw)
        el_text = el.get_text(" ", strip=True) if hasattr(el, "get_text") else ""
        el_text_norm = _norm(el_text)

        # Cards principais (podem NÃO ser svg.card em alguns layouts)
        if "PACIENTES NA UNIDADE" in aria or "PACIENTES NA UNIDADE" in el_text_norm:
            out["pacientes_unidade"] = _pick_patient_count(aria_raw, el_text)
            continue

        if "AGUARDANDO REGULACAO" in aria or "AGUARDANDO REGULACAO" in el_text_norm:
            out["pacientes_regulacao"] = _pick_patient_count(aria_raw, el_text)
            continue

        # Atendimento médico (muitos textos variam)
        if ("ATENDIMENTO" in aria or "ATENDIMENTO" in el_text_norm) and ("MEDICO" in aria or "MEDICO" in el_text_norm):
            # tenta evitar falsos positivos: precisa ter PACIENTES ou AGUARD
            if ("PACIENT" in aria or "PACIENT" in el_text_norm or "AGUARD" in aria or "AGUARD" in el_text_norm):
                out["pacientes_at_medico"] = _pick_patient_count(aria_raw, el_text)
                continue

        # 2) Classificações: detectar cor + extrair (pacientes, tempo)
        # A palavra "classificação" às vezes some; então o gatilho é: cor + (tempo/pacientes/risco/classif)
        color = None
        for c in COLORS:
            if c in aria or c in el_text_norm:
                color = c
                break
        if not color:
            continue

        gate = ("CLASSIF" in aria) or ("CLASSIF" in el_text_norm) or ("RISCO" in aria) or ("RISCO" in el_text_norm) or ("TEMPO" in aria) or ("TEMPO" in el_text_norm) or ("PACIENT" in aria) or ("PACIENT" in el_text_norm)
        if not gate:
            continue

        tempo = _extract_time(aria_raw) or _extract_time(el_text) or _extract_time(aria) or _extract_time(el_text_norm)
        pacientes = _pick_patient_count(aria_raw, el_text)

        # grava só se encontrou algo (evita sobrescrever um valor bom por None)
        prev = out["classificacoes"].get(color, {}) or {}
        if prev.get("pacientes") is None and pacientes is not None:
            prev["pacientes"] = pacientes
        if prev.get("tempo_medio") is None and tempo is not None:
            prev["tempo_medio"] = tempo
        out["classificacoes"][color] = prev

    # 3) Fallback bruto: tentar achar padrões no texto inteiro (quando aria-label vem capado)
    # Ex.: "... CLASSIFICACAO AZUL 3 00:10:00 ..."
    big_text = soup.get_text(" ", strip=True)
    big_norm = _norm(big_text)

    for c in COLORS:
        if out["classificacoes"][c]["pacientes"] is None:
            # pega um trecho em volta da cor
            idx = big_norm.find(c)
            if idx != -1:
                window = big_text[max(0, idx - 120): idx + 220]
                window_norm = _norm(window)
                if ("CLASSIF" in window_norm) or ("RISCO" in window_norm) or ("TEMPO" in window_norm):
                    out["classificacoes"][c]["pacientes"] = _pick_patient_count(window)
                    out["classificacoes"][c]["tempo_medio"] = out["classificacoes"][c]["tempo_medio"] or _extract_time(window)

    return out
