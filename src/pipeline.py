"""
pipeline.py — Acquisizione automatica atti parlamentari
=======================================================
Fonti monitorate:
  - OdG Assemblea Senato
  - OdG Commissioni Senato (1ª–14ª)
  - OdG Assemblea Camera
  - OdG Commissioni Camera (I–XIV)
"""

import json
import hashlib
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser


# ─── CONFIGURAZIONE FONTI ─────────────────────────────────────────────────────

FONTI = {
    # SENATO — Assemblea
    "senato_assemblea": {
        "url": "https://www.senato.it/lavori/assemblea/ordine-del-giorno",
        "ramo": "Senato",
        "organo": "Assemblea",
    },
    # SENATO — Commissioni permanenti
    "senato_comm_1":  {"url": "https://www.senato.it/lavori/commissioni/1/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 1ª (Affari Costituzionali)"},
    "senato_comm_2":  {"url": "https://www.senato.it/lavori/commissioni/2/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 2ª (Giustizia)"},
    "senato_comm_3":  {"url": "https://www.senato.it/lavori/commissioni/3/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 3ª (Esteri)"},
    "senato_comm_4":  {"url": "https://www.senato.it/lavori/commissioni/4/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 4ª (Difesa)"},
    "senato_comm_5":  {"url": "https://www.senato.it/lavori/commissioni/5/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 5ª (Bilancio)"},
    "senato_comm_6":  {"url": "https://www.senato.it/lavori/commissioni/6/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 6ª (Finanze)"},
    "senato_comm_7":  {"url": "https://www.senato.it/lavori/commissioni/7/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 7ª (Cultura)"},
    "senato_comm_8":  {"url": "https://www.senato.it/lavori/commissioni/8/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 8ª (Ambiente)"},
    "senato_comm_9":  {"url": "https://www.senato.it/lavori/commissioni/9/ordine-del-giorno",  "ramo": "Senato", "organo": "Commissione 9ª (Trasporti)"},
    "senato_comm_10": {"url": "https://www.senato.it/lavori/commissioni/10/ordine-del-giorno", "ramo": "Senato", "organo": "Commissione 10ª (Industria)"},
    "senato_comm_11": {"url": "https://www.senato.it/lavori/commissioni/11/ordine-del-giorno", "ramo": "Senato", "organo": "Commissione 11ª (Lavoro)"},
    "senato_comm_12": {"url": "https://www.senato.it/lavori/commissioni/12/ordine-del-giorno", "ramo": "Senato", "organo": "Commissione 12ª (Sanità)"},
    "senato_comm_13": {"url": "https://www.senato.it/lavori/commissioni/13/ordine-del-giorno", "ramo": "Senato", "organo": "Commissione 13ª (Territorio)"},
    "senato_comm_14": {"url": "https://www.senato.it/lavori/commissioni/14/ordine-del-giorno", "ramo": "Senato", "organo": "Commissione 14ª (Politiche UE)"},
    # CAMERA — Assemblea
    "camera_assemblea": {
        "url": "https://www.camera.it/leg19/634",
        "ramo": "Camera",
        "organo": "Assemblea",
    },
    # CAMERA — Commissioni permanenti
    "camera_comm_1":  {"url": "https://www.camera.it/leg19/comm/1/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione I (Affari Costituzionali)"},
    "camera_comm_2":  {"url": "https://www.camera.it/leg19/comm/2/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione II (Giustizia)"},
    "camera_comm_3":  {"url": "https://www.camera.it/leg19/comm/3/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione III (Esteri)"},
    "camera_comm_4":  {"url": "https://www.camera.it/leg19/comm/4/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione IV (Difesa)"},
    "camera_comm_5":  {"url": "https://www.camera.it/leg19/comm/5/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione V (Bilancio)"},
    "camera_comm_6":  {"url": "https://www.camera.it/leg19/comm/6/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione VI (Finanze)"},
    "camera_comm_7":  {"url": "https://www.camera.it/leg19/comm/7/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione VII (Cultura)"},
    "camera_comm_8":  {"url": "https://www.camera.it/leg19/comm/8/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione VIII (Ambiente)"},
    "camera_comm_9":  {"url": "https://www.camera.it/leg19/comm/9/ordine_del_giorno.asp",  "ramo": "Camera", "organo": "Commissione IX (Trasporti)"},
    "camera_comm_10": {"url": "https://www.camera.it/leg19/comm/10/ordine_del_giorno.asp", "ramo": "Camera", "organo": "Commissione X (Attività Produttive)"},
    "camera_comm_11": {"url": "https://www.camera.it/leg19/comm/11/ordine_del_giorno.asp", "ramo": "Camera", "organo": "Commissione XI (Lavoro)"},
    "camera_comm_12": {"url": "https://www.camera.it/leg19/comm/12/ordine_del_giorno.asp", "ramo": "Camera", "organo": "Commissione XII (Affari Sociali)"},
    "camera_comm_13": {"url": "https://www.camera.it/leg19/comm/13/ordine_del_giorno.asp", "ramo": "Camera", "organo": "Commissione XIII (Agricoltura)"},
    "camera_comm_14": {"url": "https://www.camera.it/leg19/comm/14/ordine_del_giorno.asp", "ramo": "Camera", "organo": "Commissione XIV (Politiche UE)"},
}

SPARQL_ENDPOINT = "http://dati.senato.it/sparql"
LEGISLATURA_CORRENTE = 19
OUTPUT_PATH = "public/atti_estratti.json"


# ─── REGOLE DI RILEVAMENTO FASI ──────────────────────────────────────────────

REGOLE_FASE = [
    {
        "id": "voto_finale",
        "label": "Voto finale",
        "urgenza": "critical",
        "espressioni": [
            "voto finale con la presenza del numero legale",
            "previsto voto finale",
            "voto finale",
        ],
    },
    {
        "id": "votazioni",
        "label": "Votazioni previste",
        "urgenza": "critical",
        "espressioni": ["previste votazioni"],
    },
    {
        "id": "approvato",
        "label": "Approvato",
        "urgenza": "done",
        "espressioni": [
            "approvato testo",
            "testo approvato",
            "concluso l'esame",
            "conclusione esame",
            "seguito e conclusione della discussione",
            "seguito e conclusione esame",
            "seguito e conclusione",
        ],
        "escludi_se_seguito_da": ["dalla camera", "dal senato", "dalla commissione"],
    },
    {
        "id": "emendamenti_approvati",
        "label": "Emendamenti approvati",
        "urgenza": "warning",
        "espressioni": [
            "approvati emendamenti",
            "approvazione emendamenti",
        ],
    },
    {
        "id": "emendamenti_presentati",
        "label": "Emendamenti presentati",
        "urgenza": "warning",
        "espressioni": [
            "presentati emendamenti",
        ],
    },
    {
        "id": "termine_emendamenti",
        "label": "Termine emendamenti",
        "urgenza": "warning",
        "espressioni": [
            "fissato termine per la presentazione degli emendamenti",
            "termine per la presentazione degli emendamenti",
            "termine per la presentazione di emendamenti",
        ],
    },
    {
        "id": "mandato_relatore",
        "label": "Mandato relatore",
        "urgenza": "info",
        "espressioni": [
            "conferito mandato al relatore a riferire favorevolmente",
            "conferito mandato alla relatrice a riferire favorevolmente",
            "conferito mandato al relatore",
            "conferito mandato alla relatrice",
            "mandato al relatore a riferire favorevolmente",
        ],
    },
    {
        "id": "testo_base",
        "label": "Testo base adottato",
        "urgenza": "info",
        "espressioni": [
            "adottato testo base testo unificato",
            "adottato testo base",
            "proposto testo unificato",
        ],
    },
    {
        "id": "sede",
        "label": "Sede referente/redigente",
        "urgenza": "info",
        "espressioni": ["sede referente", "sede redigente"],
    },
    {
        "id": "coordinamento",
        "label": "Coordinamento formale",
        "urgenza": "info",
        "espressioni": ["coordinamento formale"],
    },
]


# ─── PARSER HTML ──────────────────────────────────────────────────────────────

class OdGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.testo = []
        self._skip_tags = {"script", "style", "nav", "header", "footer"}
        self._tag_stack = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip_depth += 1
        self._tag_stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        testo = data.strip()
        if testo:
            self.testo.append(testo)

    def get_testo(self):
        return "\n".join(self.testo)


def fetch_pagina(url: str) -> dict:
    result = {
        "url": url,
        "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "testo": None,
        "hash_sorgente": None,
        "errore": None,
    }
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ParlamentoMonitor/2.0 (ricerca istituzionale)",
                "Accept-Language": "it-IT,it;q=0.9",
            }
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result["http_status"] = resp.status
            html = resp.read().decode("utf-8", errors="replace")
            parser = OdGParser()
            parser.feed(html)
            testo = parser.get_testo()
            result["testo"] = testo
            result["hash_sorgente"] = hashlib.sha256(testo.encode()).hexdigest()
    except Exception as e:
        result["errore"] = str(e)
    return result


# ─── PARSER ATTI ─────────────────────────────────────────────────────────────

PATTERN_NUMERATO = re.compile(
    r'(?:^|\n)\s*\d+\.\s+(.*?)\((\d{3,5})\)\s*(?:\n|$)',
    re.DOTALL
)

PATTERN_PARENTESI = re.compile(r'\((\d{4,5})\)')


def parsa_atti(testo: str, fonte: dict) -> list:
    atti = []
    ramo = fonte["ramo"]
    organo = fonte["organo"]
    prefisso = "AS" if ramo == "Senato" else "AC"

    matches = list(PATTERN_NUMERATO.finditer(testo))

    if matches:
        for i, m in enumerate(matches):
            testo_atto = m.group(1).strip()
            numero = m.group(2).strip()
            fine = matches[i+1].start() if i+1 < len(matches) else len(testo)
            testo_completo = testo[m.start():fine].strip()

            tipo = "DDL"
            if re.search(r"conversione.*decreto[- ]legge", testo_atto, re.IGNORECASE):
                tipo = "Conversione DL"
            elif re.search(r"decreto[- ]legge", testo_atto, re.IGNORECASE):
                tipo = "Decreto-Legge"

            stato = "All'ordine del giorno"
            tc_low = testo_completo.lower()
            if "ove approvato dalla camera" in tc_low:
                stato = "All'odg (condizionato – prev. approvazione Camera)"
            elif "approvato dalla camera" in tc_low:
                stato = "Approvato dalla Camera – in esame Senato"
            elif "approvato dal senato" in tc_low:
                stato = "Approvato dal Senato – in esame Camera"

            atti.append({
                "id": f"{ramo[0]}{organo[:3].replace(' ','')}-{numero}",
                "ramo": ramo,
                "organo": organo,
                "tipo": tipo,
                "numero": f"{prefisso} {numero}",
                "numero_raw": numero,
                "stato": stato,
                "testo_estratto": testo_completo,
                "metodo_estrazione": "pattern_numerato",
            })
    else:
        # Fallback: cerca numeri atto tra parentesi
        visti = set()
        for m in PATTERN_PARENTESI.finditer(testo):
            numero = m.group(1)
            if numero in visti:
                continue
            visti.add(numero)
            start = max(0, m.start() - 300)
            ctx = testo[start:m.end()].strip()
            atti.append({
                "id": f"{ramo[0]}{organo[:3].replace(' ','')}-{numero}",
                "ramo": ramo,
                "organo": organo,
                "tipo": "DDL",
                "numero": f"{prefisso} {numero}",
                "numero_raw": numero,
                "stato": "All'ordine del giorno",
                "testo_estratto": ctx,
                "metodo_estrazione": "fallback_parentesi",
            })

    return atti


# ─── SPARQL ───────────────────────────────────────────────────────────────────

def query_sparql(numero: str) -> dict:
    query = f"""
PREFIX osr: <http://dati.senato.it/osr/>
SELECT DISTINCT ?titolo ?stato ?dataPresentazione ?natura
WHERE {{
  ?ddl a osr:Ddl.
  ?ddl osr:idFase ?idFase.
  ?ddl osr:titolo ?titolo.
  ?ddl osr:statoDdl ?stato.
  ?ddl osr:natura ?natura.
  ?ddl osr:dataPresentazione ?dataPresentazione.
  ?ddl osr:legislatura {LEGISLATURA_CORRENTE}.
  FILTER(?idFase = {numero})
}}
LIMIT 1
"""
    params = urllib.parse.urlencode({
        "query": query,
        "format": "application/sparql-results+json",
    })
    try:
        req = urllib.request.Request(
            f"{SPARQL_ENDPOINT}?{params}",
            headers={"Accept": "application/sparql-results+json", "User-Agent": "ParlamentoMonitor/2.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            bindings = data.get("results", {}).get("bindings", [])
            if not bindings:
                return {"errore": f"nessun risultato per {numero}"}
            return {k: v.get("value") for k, v in bindings[0].items()}
    except Exception as e:
        return {"errore": str(e)}


# ─── RILEVAMENTO FASI ─────────────────────────────────────────────────────────

def rileva_fasi(testo: str) -> list:
    testo_lower = testo.lower()
    trovate = []
    for regola in REGOLE_FASE:
        for expr in regola["espressioni"]:
            idx = testo_lower.find(expr.lower())
            if idx == -1:
                continue
            escludi = regola.get("escludi_se_seguito_da", [])
            if escludi:
                dopo = testo_lower[idx + len(expr):idx + len(expr) + 30].strip()
                if any(dopo.startswith(e) for e in escludi):
                    continue
            ctx_start = max(0, idx - 40)
            ctx_end = min(len(testo), idx + len(expr) + 40)
            trovate.append({
                "id": regola["id"],
                "label": regola["label"],
                "urgenza": regola["urgenza"],
                "found_text": testo[idx:idx + len(expr)],
                "found_context": testo[ctx_start:ctx_end].strip(),
            })
            break
    return trovate


# ─── PIPELINE PRINCIPALE ─────────────────────────────────────────────────────

def esegui_pipeline(fetch_sparql=True, verbose=True) -> dict:
    timestamp_run = datetime.now(timezone.utc).isoformat()
    report = {
        "pipeline_run": {
            "timestamp": timestamp_run,
            "versione_motore": "2.0.0",
            "fonti_interrogate": [],
            "n_atti_estratti": 0,
            "n_atti_con_segnali": 0,
            "n_alert": 0,
        },
        "atti": [],
    }

    ids_visti = set()  # evita duplicati cross-fonte

    for fonte_id, fonte in FONTI.items():
        if verbose:
            print(f"\n→ {fonte['organo']} ({fonte['ramo']}): {fonte['url']}")

        fetch = fetch_pagina(fonte["url"])
        report["pipeline_run"]["fonti_interrogate"].append({
            "id": fonte_id,
            "url": fonte["url"],
            "http_status": fetch["http_status"],
            "errore": fetch["errore"],
            "testo_lunghezza": len(fetch.get("testo") or ""),
        })

        if fetch["errore"]:
            if verbose:
                print(f"  ✗ {fetch['errore']}")
            continue

        if verbose:
            print(f"  ✓ HTTP {fetch['http_status']}, {len(fetch['testo'])} chars")

        atti_estratti = parsa_atti(fetch["testo"], fonte)
        if verbose:
            print(f"  ✓ {len(atti_estratti)} atti trovati")

        for ar in atti_estratti:
            # Evita duplicati (stesso atto in assemblea e commissione)
            uid = f"{ar['ramo']}-{ar['numero_raw']}"
            if uid in ids_visti:
                continue
            ids_visti.add(uid)

            sparql_meta = {}
            if fetch_sparql and ar["numero_raw"] and ar["ramo"] == "Senato":
                sparql_meta = query_sparql(ar["numero_raw"])

            fasi = rileva_fasi(ar["testo_estratto"])
            titolo = sparql_meta.get("titolo") or ar["testo_estratto"][:200]

            atto = {
                "id": ar["id"],
                "ramo": ar["ramo"],
                "organo": ar["organo"],
                "tipo": ar["tipo"],
                "numero": ar["numero"],
                "stato": ar["stato"],
                "titolo": titolo,
                "note": ar["testo_estratto"],
                "fasi_rilevate": fasi,
                "sparql_metadati": sparql_meta,
                "alert": [],
                "link": fonte["url"],
                "provenance": {
                    "source_url": fonte["url"],
                    "fetch_timestamp": fetch["fetch_timestamp"],
                    "hash_sorgente": fetch["hash_sorgente"],
                    "fonte_ufficiale": f"OdG {fonte['organo']} {fonte['ramo']} – XIX Legislatura",
                    "metodo_estrazione": ar.get("metodo_estrazione"),
                },
            }
            report["atti"].append(atto)

    report["pipeline_run"]["n_atti_estratti"] = len(report["atti"])
    report["pipeline_run"]["n_atti_con_segnali"] = sum(1 for a in report["atti"] if a["fasi_rilevate"])
    report["pipeline_run"]["n_alert"] = sum(len(a["alert"]) for a in report["atti"])
    return report


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  PIPELINE PARLAMENTARE v2.0 — avvio acquisizione")
    print("=" * 60)

    report = esegui_pipeline(fetch_sparql=True, verbose=True)

    print(f"\n{'='*60}")
    print(f"  Fonti interrogate:  {len(report['pipeline_run']['fonti_interrogate'])}")
    print(f"  Atti estratti:      {report['pipeline_run']['n_atti_estratti']}")
    print(f"  Con segnali:        {report['pipeline_run']['n_atti_con_segnali']}")
    print(f"{'='*60}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Output: {OUTPUT_PATH}")

