import os
import re
from bs4 import BeautifulSoup

from upas import UPAS_DF
from core.scraper import fetch_html
from core.parser import parse_upa_dashboard


def slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def main():
    upa_nome, url = list(UPAS_DF.items())[0]
    print(f"\n[DEBUG] UPA: {upa_nome}")
    print(f"[DEBUG] URL: {url}")

    res = fetch_html(url)
    html = res.html

    print(f"[DEBUG] via: {getattr(res, 'via', '??')}")
    print(f"[DEBUG] status_code: {getattr(res, 'status_code', '??')}")
    print(f"[DEBUG] html_len: {len(html)}")
    print(f"[DEBUG] contains '<iframe': {'<iframe' in html.lower()}")
    print(f"[DEBUG] contains 'powerbi': {'powerbi' in html.lower()}")
    print(f"[DEBUG] contains 'app.powerbi': {'app.powerbi' in html.lower()}")
    print(f"[DEBUG] contains 'PACIENTES NA UNIDADE': {'PACIENTES NA UNIDADE' in html.upper()}")
    print(f"[DEBUG] contains 'ATUALIZADO EM': {'ATUALIZADO EM' in html.upper()}")

    soup = BeautifulSoup(html, "lxml")
    labels = [el.get("aria-label") for el in soup.select("[aria-label]") if el.get("aria-label")]
    print(f"[DEBUG] aria-label count: {len(labels)}")
    for i, lab in enumerate(labels[:25], start=1):
        print(f"  {i:02d} aria-label: {lab}")

    os.makedirs("debug_html", exist_ok=True)
    out = f"debug_html/{slug(upa_nome)}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[DEBUG] HTML salvo em: {out}")

    data = parse_upa_dashboard(html)
    print("\n[DEBUG] parse result (resumo):")
    print("  pacientes_unidade:", data.get("pacientes_unidade"))
    print("  pacientes_regulacao:", data.get("pacientes_regulacao"))
    print("  pacientes_at_medico:", data.get("pacientes_at_medico"))
    print("  updated_at:", data.get("updated_at"))
    print("  classifs:", data.get("classificacoes"))


if __name__ == "__main__":
    main()
