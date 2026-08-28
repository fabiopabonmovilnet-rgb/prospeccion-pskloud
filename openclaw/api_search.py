"""
Módulo de búsqueda de leads por API (migrado desde Streamlit app.py al entorno :9000).
- Hunter.io: domain-search para emails por dominio
- Lusha: enriquecimiento de empresa/contacto (reutiliza enrichment.py)
- RocketReach: búsqueda por empresa/cargo/país
- CUFinder: búsqueda por empresa + cargo + país
- Fallback: scraping local (local_search / enrichment)
Keys persistentes en /app/data/api_keys.json
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import random
from typing import Optional

import httpx

logger = logging.getLogger("openclaw.api_search")

BASE_DIR = "/app/data"
KEYS_FILE = os.path.join(BASE_DIR, "api_keys.json")
RESULTS_FILE = os.path.join(BASE_DIR, "leads_api_search.json")

try:
    import enrichment
    from enrichment import search_lusha_company, search_lusha_by_email, search_lusha
    HAS_LUSHA = True
except Exception as e:
    logger.warning(f"Lusha/enrichment no disponible: {e}")
    HAS_LUSHA = False


def get_keys() -> dict:
    if not os.path.exists(KEYS_FILE):
        return {}
    try:
        with open(KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_keys(keys: dict) -> dict:
    data = get_keys()
    data.update(keys)
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def buscar_contactos_hunter(api_key: str, dominio: str, limite: int = 10) -> tuple[list, dict]:
    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": dominio, "api_key": api_key, "limit": limite, "type": "personal"}
    try:
        resp = httpx.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        datos_empresa = data.get("data", {})
        contactos = datos_empresa.get("emails", [])
        resultados = []
        for c in contactos:
            resultados.append({
                "Contacto Clabe": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                "Cargo": c.get("position", "") or c.get("seniority", ""),
                "Empresa": datos_empresa.get("organization", ""),
                "País": c.get("country", ""),
                "Correo": c.get("value", ""),
                "Fuente": "Hunter.io",
                "dominio": dominio,
            })
        info = {
            "empresa": datos_empresa.get("organization", ""),
            "dominio": datos_empresa.get("domain", dominio),
            "fundada": datos_empresa.get("founded_year", ""),
            "industria": datos_empresa.get("industry", ""),
            "cuenta": data.get("requests", {}),
        }
        return resultados, info
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return [], {"error": "API key Hunter inválida"}
        if e.response.status_code == 429:
            return [], {"error": "Cuota Hunter agotada"}
        return [], {"error": f"Error Hunter: {e.response.status_code}"}
    except Exception as e:
        return [], {"error": f"Error Hunter: {str(e)}"}


def buscar_contactos_rocketreach(api_key: str, empresa: str, pais: str = "", cargo: str = "", limite: int = 10) -> tuple[list, dict]:
    url = "https://api.rocketreach.co/v1/api/search"
    headers = {"Api-Key": api_key}
    params = {"query": empresa, "page_size": limite}
    if pais:
        params["current_country"] = pais
    if cargo:
        params["current_title"] = cargo
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        contactos = data.get("profiles", [])
        resultados = []
        for p in contactos:
            resultados.append({
                "Contacto Clabe": f"{p.get('name', '')}".strip(),
                "Cargo": p.get("current_title", ""),
                "Empresa": p.get("current_employer", ""),
                "País": p.get("current_country", ""),
                "Correo": p.get("email", ""),
                "Fuente": "RocketReach",
                "empresa": empresa,
            })
        return resultados, {"error": "", "total": data.get("total", len(resultados))}
    except httpx.HTTPStatusError as e:
        return [], {"error": f"Error RocketReach: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return [], {"error": f"Error RocketReach: {str(e)}"}


def buscar_contactos_cufinder(api_key: str, empresa: str, pais: str = "", cargo: str = "", limite: int = 10) -> tuple[list, dict]:
    url = "https://api.cufinder.io/v1/search"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"company": empresa, "limit": limite}
    if pais:
        payload["country"] = pais
    if cargo:
        payload["title"] = cargo
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        contactos = data.get("data", []) or data.get("results", []) or []
        resultados = []
        for c in contactos:
            resultados.append({
                "Contacto Clabe": f"{c.get('name', '')}".strip(),
                "Cargo": c.get("title", ""),
                "Empresa": c.get("company", "") or empresa,
                "País": c.get("country", "") or pais,
                "Correo": c.get("email", ""),
                "Fuente": "CUFinder",
                "empresa": empresa,
            })
        return resultados, {"error": ""}
    except httpx.HTTPStatusError as e:
        return [], {"error": f"Error CUFinder: {e.response.status_code} - {e.response.text[:200]}"}
    except Exception as e:
        return [], {"error": f"Error CUFinder: {str(e)}"}


def buscar_organizaciones_apollo(api_key: str, rubro: str = "", pais: str = "", ciudad: str = "", limite: int = 10) -> tuple[list, dict]:
    """Apollo.io Organizations Search (plan Free, no consume créditos de people-export).
    Pagina (máx 3 páginas / hasta 25 por página) para alcanzar el límite pedido."""
    url = "https://api.apollo.io/v1/organizations/search"
    headers = {"X-Api-Key": api_key, "Api-Key": api_key, "Content-Type": "application/json", "Cache-Control": "no-cache"}
    espacios = max(1, min(int(limite or 10), 75))
    per_page = min(25, max(1, espacios))
    resultados = []
    vistos = set()
    page = 1
    ultimo_error = ""
    while len(resultados) < espacios and page <= 3:
        payload: dict = {"page": page, "per_page": per_page, "q_keywords": rubro or "software"}
        if pais:
            payload["country"] = pais
        if ciudad:
            payload["city"] = ciudad
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 401:
                return [], {"error": "API key Apollo inválida (401)", "status": 401}
            if resp.status_code == 429:
                return [], {"error": "Cuota Apollo agotada (429)", "status": 429}
            resp.raise_for_status()
            data = resp.json()
            orgs = data.get("organizations", []) or []
            if not orgs:
                break
            for o in orgs:
                nombre = o.get("name", "")
                clave = f"{nombre}|{o.get('website_url', '')}".lower()
                if clave in vistos:
                    continue
                vistos.add(clave)
                tel = o.get("phone_numbers")
                if isinstance(tel, list) and tel:
                    prim = tel[0]
                    tel = prim.get("phone", "") if isinstance(prim, dict) else str(prim)
                elif isinstance(tel, dict):
                    tel = tel.get("phone", "")
                else:
                    tel = o.get("phone", "") or ""
                resultados.append({
                    "Contacto Clabe": "",
                    "Cargo": "",
                    "Empresa": nombre,
                    "País": o.get("country", "") or pais,
                    "Ciudad": o.get("city", "") or ciudad,
                    "Correo": o.get("email", "") or "",
                    "Telefono": tel,
                    "Fuente": "Apollo (empresas)",
                    "industria": o.get("industry", "") or "",
                    "website": o.get("website_url", "") or o.get("primary_domain", "") or "",
                    "empleados": o.get("employees", "") or "",
                    "fundada": o.get("founded_year", "") or "",
                })
        except httpx.HTTPStatusError as e:
            ultimo_error = f"Error Apollo: {e.response.status_code} - {e.response.text[:200]}"
            break
        except Exception as e:
            ultimo_error = f"Error Apollo: {str(e)}"
            break
        page += 1
    if not resultados and ultimo_error:
        return [], {"error": ultimo_error, "status": "error"}
    return resultados[:espacios], {"total": len(resultados), "solo_orgs": True,
                                    "nota": "Plan Free: solo búsqueda de empresas (organizations/search)"}


def buscar_contactos_apollo(api_key: str, empresa: str = "", pais: str = "", cargo: str = "", limite: int = 10, solo_orgs: bool = False) -> tuple[list, dict]:
    """Apollo.io People Search (mixed_people/search). Header X-Api-Key.
    En planes Free devuelve 403 → fallback automático a búsqueda de empresas (organizations/search).
    Con solo_orgs=True salta el people-search (no consume créditos en ningún plan)."""
    if solo_orgs:
        res, info = buscar_organizaciones_apollo(api_key, empresa or cargo, pais, "", limite)
        info["solo_orgs"] = True
        info["credits"] = 0
        return res, info
    url = "https://api.apollo.io/v1/mixed_people/search"
    headers = {"X-Api-Key": api_key, "Api-Key": api_key, "Content-Type": "application/json", "Cache-Control": "no-cache"}
    payload: dict = {"page": 1, "per_page": max(1, min(int(limite), 25))}
    if empresa:
        payload["q_keywords"] = empresa
    if pais:
        payload["country"] = pais
    if cargo:
        payload["person_titles"] = [cargo]
    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=25)
        if resp.status_code == 401:
            return [], {"error": "API key Apollo inválida (401)", "status": 401}
        if resp.status_code == 403:
            res, info = buscar_organizaciones_apollo(api_key, empresa or cargo, pais, "", limite)
            return res, info
        if resp.status_code == 429:
            return [], {"error": "Cuota Apollo agotada (429)", "status": 429}
        resp.raise_for_status()
        data = resp.json()
        personas = data.get("people", []) or []
        resultados = []
        n_emails = 0
        for c in personas[:limite]:
            org = c.get("organization") or {}
            email = c.get("email", "") or ""
            if not email:
                emails = c.get("emails")
                if isinstance(emails, list) and emails:
                    prim = emails[0]
                    if isinstance(prim, dict):
                        email = prim.get("email", "")
                    elif isinstance(prim, str):
                        email = prim
            nombre = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or c.get("name", "")
            resultados.append({
                "Contacto Clabe": nombre,
                "Cargo": c.get("title", "") or "",
                "Empresa": org.get("name", "") or empresa,
                "País": org.get("country", "") or pais,
                "Correo": email,
                "Telefono": c.get("phone", "") or "",
                "Fuente": "Apollo",
                "industria": org.get("industry", "") or "",
                "linkedin": c.get("linkedin_url", "") or "",
            })
            if email:
                n_emails += 1
        info = {
            "total": len(personas),
            "con_email": n_emails,
            "solo_orgs": False,
            "credits": data.get("credits_consumed", "") or resp.headers.get("x-credits-consumed", ""),
        }
        return resultados, info
    except httpx.HTTPStatusError as e:
        return [], {"error": f"Error Apollo: {e.response.status_code} - {e.response.text[:200]}", "status": e.response.status_code}
    except Exception as e:
        return [], {"error": f"Error Apollo: {str(e)}"}


def _extract_domain(empresa: str) -> str:
    dominio = ""
    try:
        import enrichment as _en
        d = _en.scrape_website(empresa, "") if hasattr(_en, "scrape_website") else {}
    except Exception:
        d = {}
    if isinstance(d, dict):
        dominio = d.get("dominio", "") or d.get("website", "") or ""
        if dominio and not dominio.startswith("http"):
            dominio = f"https://{dominio}"
    if not dominio:
        dominio = f"https://{empresa.lower().replace(' ', '').replace('.', '')}.com"
    m = re.match(r"https?://(?:www\.)?([^/]+)", dominio)
    return m.group(1) if m else dominio


def buscar_por_empresa(empresa: str, pais: str = "", cargo: str = "", limite: int = 10, fuentes: list[str] | None = None) -> dict:
    keys = get_keys()
    fuentes = fuentes or ["Hunter", "Lusha", "RocketReach", "CUFinder", "Apollo", "Web"]
    todo = []
    errores = []
    info_por_fuente = {}

    hunter_key = keys.get("hunter") or keys.get("HUNTER_API_KEY")
    if "Hunter" in fuentes and hunter_key:
        dominio = _extract_domain(empresa)
        res, info = buscar_contactos_hunter(hunter_key, dominio, limite)
        info_por_fuente["Hunter"] = info
        if info.get("error"):
            errores.append(f"Hunter: {info['error']}")
        todo.extend(res)

    if "Lusha" in fuentes and HAS_LUSHA:
        lusha_key = keys.get("lusha") or keys.get("LUSHA_API_KEY")
        if lusha_key:
            try:
                info = search_lusha_company(lusha_key, empresa)
                info_por_fuente["Lusha"] = info
            except Exception as e:
                errores.append(f"Lusha: {str(e)}")

    if "RocketReach" in fuentes:
        rr_key = keys.get("rocketreach") or keys.get("ROCKETREACH_API_KEY")
        if rr_key:
            res, info = buscar_contactos_rocketreach(rr_key, empresa, pais, cargo, limite)
            info_por_fuente["RocketReach"] = info
            if info.get("error"):
                errores.append(f"RocketReach: {info['error']}")
            todo.extend(res)

    if "CUFinder" in fuentes:
        cf_key = keys.get("cufinder") or keys.get("CUFINDER_API_KEY")
        if cf_key:
            res, info = buscar_contactos_cufinder(cf_key, empresa, pais, cargo, limite)
            info_por_fuente["CUFinder"] = info
            if info.get("error"):
                errores.append(f"CUFinder: {info['error']}")
            todo.extend(res)

    if "Apollo" in fuentes:
        a_key = keys.get("apollo") or keys.get("APOLLO_API_KEY")
        if a_key:
            res, info = buscar_contactos_apollo(a_key, empresa, pais, cargo, limite, solo_orgs=True)
            info_por_fuente["Apollo"] = info
            if info.get("error"):
                errores.append(f"Apollo: {info['error']}")
            todo.extend(res)

    if "Web" in fuentes:
        try:
            import local_search
            loc = local_search.search_local(empresa, ciudad=pais, rubro=cargo, max_results=limite) if hasattr(local_search, "search_local") else {}
            if isinstance(loc, dict) and loc.get("leads"):
                for l in loc["leads"][:limite]:
                    todo.append({
                        "Contacto Clabe": l.get("nombre", ""),
                        "Empresa": l.get("empresa", "") or empresa,
                        "País": l.get("pais", "") or pais,
                        "Rubro": l.get("rubro", ""),
                        "Teléfono": l.get("telefono", ""),
                        "Fuente": "Web",
                    })
                info_por_fuente["Web"] = {"leads": len(loc["leads"])}
        except Exception as e:
            errores.append(f"Web: {str(e)}")

    # Dedup por email/teléfono
    vistos = set()
    unicos = []
    for lead in todo:
        clave = (lead.get("Correo") or lead.get("Teléfono") or lead.get("Contacto Clabe", "")).lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(lead)

    return {"leads": unicos, "errores": errores, "fuentes": list(info_por_fuente.keys()), "info": info_por_fuente}


def guardar_resultados(leads: list[dict]) -> int:
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        prev = []
    prev.extend(leads)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prev, f, ensure_ascii=False, indent=2)
    return len(leads)


def cargar_resultados() -> list:
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []
