# scraper.py
from __future__ import annotations

import os
import random
import time
import warnings
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import certifi
import requests

# Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


# =========================
# Settings helpers
# =========================
def _get_verify_ssl_default() -> bool:
    """
    Tenta pegar VERIFY_SSL do settings.py.
    Aceita também get_verify_ssl() se existir.
    Default: True.
    """
    try:
        from settings import get_verify_ssl  # type: ignore
        return bool(get_verify_ssl())
    except Exception:
        pass

    try:
        from settings import VERIFY_SSL  # type: ignore
        return bool(VERIFY_SSL)
    except Exception:
        return True


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


VERIFY_SSL = _get_verify_ssl_default()


# =========================
# Types
# =========================
@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str
    via: str  # "requests" | "selenium-main" | "selenium-iframe"
    iframe_url: Optional[str] = None


# =========================
# Requests (rápido / fallback)
# =========================
def _build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
            "Connection": "keep-alive",
        }
    )
    return s


_SESSION: Optional[requests.Session] = None


def fetch_html_requests(
    url: str,
    timeout: int = 30,
    retries: int = 3,
    backoff_base: float = 0.8,
    verify_ssl: Optional[bool] = None,
) -> FetchResult:
    global _SESSION
    if _SESSION is None:
        _SESSION = _build_session()

    verify = VERIFY_SSL if verify_ssl is None else bool(verify_ssl)

    if not verify:
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    last_status = 0
    last_exc: Optional[Exception] = None

    verify_opt = (certifi.where() if verify else False)

    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                time.sleep(backoff_base * (2 ** (attempt - 1)) + random.random() * 0.2)

            resp = _SESSION.get(url, timeout=timeout, verify=verify_opt, allow_redirects=True)
            last_status = resp.status_code

            if resp.status_code in (429, 503, 502, 504):
                continue

            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"

            return FetchResult(url=url, status_code=resp.status_code, html=resp.text, via="requests")

        except Exception as e:
            last_exc = e
            continue

    msg = f"[scraper] Falha ao baixar {url} (status={last_status})"
    if last_exc:
        msg += f" | erro={type(last_exc).__name__}: {last_exc}"
    raise RuntimeError(msg)


# =========================
# Selenium helpers
# =========================
def _mk_chrome_driver(headless: bool = True) -> webdriver.Chrome:
    opts = ChromeOptions()

    if headless:
        # headless "novo" (Chrome >= 109)
        opts.add_argument("--headless=new")

    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--lang=pt-BR")

    # sites chatinhos / embeds
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_argument("--allow-insecure-localhost")

    # deixa mais “leve”
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    opts.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(70)
    return driver


def _save_debug_artifacts(
    debug_dir: str,
    tag: str,
    html: str,
    driver: Optional[webdriver.Chrome] = None,
) -> Tuple[str, Optional[str]]:
    os.makedirs(debug_dir, exist_ok=True)
    safe_tag = "".join(c for c in tag.lower() if c.isalnum() or c in ("_", "-"))[:90] or "page"
    html_path = os.path.join(debug_dir, f"{safe_tag}.html")
    with open(html_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(html)

    png_path = None
    if driver is not None:
        try:
            png_path = os.path.join(debug_dir, f"{safe_tag}.png")
            driver.save_screenshot(png_path)
        except Exception:
            png_path = None

    return html_path, png_path


def _try_click_cookie(driver: webdriver.Chrome, timeout: int = 8) -> None:
    """
    Tenta clicar no banner de cookie (Aceitar). Não falha se não achar.
    """
    wait = WebDriverWait(driver, timeout)

    # tenta por texto "Aceitar"
    candidates = [
        # FIX: translate precisa de vírgula: translate(., 'ACEITAR', 'aceitar')
        (By.XPATH, "//button[contains(translate(., 'ACEITAR', 'aceitar'), 'aceitar')]"),
        (By.XPATH, "//a[contains(translate(., 'ACEITAR', 'aceitar'), 'aceitar')]"),
        (By.CSS_SELECTOR, "button#onetrust-accept-btn-handler"),
        (By.CSS_SELECTOR, "button.cookie-accept"),
    ]

    for by, sel in candidates:
        try:
            el = wait.until(EC.element_to_be_clickable((by, sel)))
            el.click()
            time.sleep(0.3)
            return
        except Exception:
            pass


def _is_powerbi_rendered(html_lower: str) -> bool:
    # marcadores que aparecem quando o PowerBI já pintou o DOM do relatório
    markers = [
        "visualcontainerhost",
        "visual-container",
        "visualcontainer",
        "powerbireport",
        "relatório do power bi",
        "reportembed",
        "app.powerbi.com",
    ]
    return any(m in html_lower for m in markers)


def _wait_powerbi_ready(driver: webdriver.Chrome, timeout: int = 45) -> None:
    wait = WebDriverWait(driver, timeout)
    wait.until(lambda d: _is_powerbi_rendered((d.page_source or "").lower()))


def _wait_for_metrics_loaded(driver: webdriver.Chrome, timeout: int = 35) -> None:
    """
    IMPORTANTÍSSIMO: o PowerBI "aparece" antes dos visuais carregarem.
    Isso espera evidência de que as métricas (cards/textos) já pintaram no HTML.
    Não levanta exceção (só tenta).
    """
    t0 = time.time()
    patterns = [
        r"PACIENTES\s+NA\s+UNIDADE",
        r"AGUARDANDO\s+REGULA",
        r"ATENDIMENTO",
        r"CLASSIF",
        r"\bAZUL\b|\bVERDE\b|\bAMARELO\b|\bLARANJA\b|\bVERMELHO\b",
    ]
    while (time.time() - t0) < timeout:
        src = (driver.page_source or "")
        up = src.upper()
        if any(re.search(p, up) for p in patterns):
            return
        time.sleep(0.5)
    return


def _collect_iframe_elements(driver: webdriver.Chrome, timeout: int = 20):
    wait = WebDriverWait(driver, timeout)
    wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "iframe")))
    return driver.find_elements(By.TAG_NAME, "iframe")


def _get_iframe_src(el) -> Optional[str]:
    src = (el.get_attribute("src") or "").strip()
    if not src:
        src = (el.get_attribute("data-src") or "").strip()
    return src or None


# =========================
# Selenium: pega HTML já renderizado do PowerBI
# =========================
def fetch_html_selenium_powerbi(
    url: str,
    headless: bool = True,
    timeout: int = 55,
    debug_dir: str = "debug_html",
    debug: bool = False,
) -> FetchResult:
    driver: Optional[webdriver.Chrome] = None
    last_exc: Optional[Exception] = None

    try:
        driver = _mk_chrome_driver(headless=headless)
        driver.get(url)
        time.sleep(1.2)

        # cookie atrapalha MUITO iframe/lazy load
        _try_click_cookie(driver, timeout=10)

        # scrollzinho pra forçar lazy-load (Elementor adora isso)
        try:
            driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(0.8)
            driver.execute_script("window.scrollTo(0, 1200);")
            time.sleep(0.8)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
        except Exception:
            pass

        # Primeiro: tenta detectar se o PowerBI já aparece NO DOM (às vezes acontece)
        main_html = driver.page_source or ""
        if _is_powerbi_rendered(main_html.lower()):
            # Espera as métricas “de verdade”
            _wait_for_metrics_loaded(driver, timeout=min(35, timeout))
            main_html = driver.page_source or ""
            if debug:
                _save_debug_artifacts(debug_dir, f"selenium_main_{url}", main_html, driver)
            return FetchResult(url=url, status_code=200, html=main_html, via="selenium-main")

        # Segundo: tenta entrar em cada iframe e ver se dentro dele tem PowerBI
        try:
            iframes = _collect_iframe_elements(driver, timeout=25)
        except Exception as e:
            if debug:
                _save_debug_artifacts(debug_dir, f"no_iframe_{url}", driver.page_source or "", driver)
            raise RuntimeError(f"[scraper] Não achei iframe na página. erro={type(e).__name__}: {e}")

        for idx, iframe in enumerate(iframes, start=1):
            src = _get_iframe_src(iframe)

            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(iframe)

                # espera shell PowerBI
                _wait_powerbi_ready(driver, timeout=timeout)
                # espera visuais/métricas
                _wait_for_metrics_loaded(driver, timeout=min(35, timeout))

                html_in = driver.page_source or ""
                if _is_powerbi_rendered(html_in.lower()):
                    if debug:
                        _save_debug_artifacts(debug_dir, f"powerbi_iframe_{idx}_{url}", html_in, driver)
                    return FetchResult(
                        url=url,
                        status_code=200,
                        html=html_in,
                        via="selenium-iframe",
                        iframe_url=src,
                    )

            except TimeoutException as e:
                last_exc = e
            except WebDriverException as e:
                last_exc = e
            except Exception as e:
                last_exc = e
            finally:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass

        # Terceiro: fallback — abre o src do “melhor” iframe em uma nova navegação
        best_src = None
        for iframe in iframes:
            s = _get_iframe_src(iframe)
            if s and (best_src is None or len(s) > len(best_src)):
                best_src = s

        if not best_src:
            if debug:
                _save_debug_artifacts(debug_dir, f"no_iframe_src_{url}", driver.page_source or "", driver)
            raise RuntimeError("[scraper] Achei iframe(s), mas nenhum com src/data-src utilizável.")

        try:
            driver.get(best_src)
            _wait_powerbi_ready(driver, timeout=timeout)
            _wait_for_metrics_loaded(driver, timeout=min(35, timeout))
            html2 = driver.page_source or ""
            if debug:
                _save_debug_artifacts(debug_dir, f"powerbi_direct_{url}", html2, driver)
            return FetchResult(
                url=url,
                status_code=200,
                html=html2,
                via="selenium-iframe",
                iframe_url=best_src,
            )
        except Exception as e:
            last_exc = e
            if debug:
                _save_debug_artifacts(debug_dir, f"powerbi_direct_fail_{url}", driver.page_source or "", driver)
            raise

    except Exception as e:
        last_exc = last_exc or e
        if debug and driver is not None:
            _save_debug_artifacts(debug_dir, f"fail_{url}", driver.page_source or "", driver)
        raise RuntimeError(
            f"[scraper] Falha Selenium/PowerBI em {url} | erro={type(last_exc).__name__}: {last_exc}"
        )
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


# =========================
# API principal (usada no app)
# =========================
def fetch_html(
    url: str,
    *,
    mode: str = "powerbi",        # "requests" | "powerbi" | "auto"
    timeout: int = 55,
    retries: int = 3,
    debug: bool = False,
    debug_dir: str = "debug_html",
    headless: Optional[bool] = None,
    verify_ssl: Optional[bool] = None,
) -> FetchResult:
    """
    mode:
      - "requests": baixa HTML cru (não pega PowerBI renderizado)
      - "powerbi": Selenium + iframe + espera render
      - "auto": tenta requests e depois powerbi
    """

    if headless is None:
        headless = _env_bool("SELENIUM_HEADLESS", True)

    m = (mode or "powerbi").strip().lower()

    if m == "requests":
        return fetch_html_requests(url, timeout=timeout, retries=retries, verify_ssl=verify_ssl)

    if m == "auto":
        try:
            r = fetch_html_requests(url, timeout=timeout, retries=2, verify_ssl=verify_ssl)
            # se já veio “renderizado” (quase nunca), devolve
            if _is_powerbi_rendered((r.html or "").lower()):
                return r
        except Exception:
            pass
        return fetch_html_selenium_powerbi(url, headless=headless, timeout=timeout, debug=debug, debug_dir=debug_dir)

    # default: powerbi
    return fetch_html_selenium_powerbi(url, headless=headless, timeout=timeout, debug=debug, debug_dir=debug_dir)
