#!/usr/bin/env python3
"""Versão na nuvem do whv-brasil-check — roda no GitHub Actions a cada ~5 min.

Lê o status do Brasil na tabela oficial e manda push pelo ntfy quando muda.
O estado (último status + falhas seguidas) fica em state.json, que o workflow
commita de volta no repositório quando muda.
"""
import base64
import gzip
import html
import json
import os
import re
import urllib.request
from pathlib import Path

URL = "https://immi.homeaffairs.gov.au/what-we-do/whm-program/status-of-country-caps"
COUNTRY = "Brazil"
STATE = Path(__file__).with_name("state.json")
TOPIC = os.environ["NTFY_TOPIC"]  # vem do secret do repositório, não fica no código
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
MAX_ERRORS = 6  # ~30 min falhando seguido → avisa que o monitor está cego


def push(title, body, priority="default", click=URL):
    headers = {
        "Title": "=?UTF-8?B?" + base64.b64encode(title.encode()).decode() + "?=",
        "Priority": priority,
        "Click": click,
        "Tags": "flag-au",
    }
    req = urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=body.encode(), headers=headers)
    urllib.request.urlopen(req, timeout=30)


def fetch_status():
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    resp = urllib.request.urlopen(req, timeout=60)
    raw = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    page = raw.decode("utf-8", "replace")
    for row in re.findall(r"<tr.*?</tr>", page, re.S | re.I):
        cells = [
            re.sub(r"[​\s]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<td.*?</td>", row, re.S | re.I)
        ]
        if cells and cells[0].lower().startswith(COUNTRY.lower()):
            return cells[1].lower()
    return None


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {"status": None, "errors": 0}
    old = state["status"]

    try:
        status = fetch_status() or "não encontrado"
    except Exception as e:
        state["errors"] += 1
        print(f"erro ao baixar ({state['errors']}x seguidas): {e}")
        if state["errors"] == MAX_ERRORS:
            push("⚠️ Monitor WHV na nuvem falhando",
                 f"Não consigo ler o site da imigração há ~30 min.\nÚltimo erro: {e}")
        STATE.write_text(json.dumps(state, ensure_ascii=False) + "\n")
        return

    if state["errors"] >= MAX_ERRORS:
        push("✅ Monitor WHV na nuvem voltou", f"Lendo o site de novo. Brasil: {status}")
    state["errors"] = 0

    print(f"{COUNTRY}: {status} (antes: {old or '-'})")
    if status != old:
        state["status"] = status
        if "open" in status:
            push("🇦🇺 COTA DO BRASIL ABERTA!",
                 "Work and Holiday 462 reabriu. Aplica AGORA na ImmiAccount — costuma esgotar em horas.",
                 "urgent", "https://online.immi.gov.au/lusc/login")
        elif old is not None:
            push("WHV Austrália: status mudou", f"Brasil: {old} → {status}")
        else:
            push("☁️ Monitor WHV na nuvem ligado", f"Primeira leitura ok. Brasil: {status}")

    STATE.write_text(json.dumps(state, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
