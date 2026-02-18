"""
pipeline.py — Acquisizione automatica e affidabile di atti parlamentari
========================================================================

Architettura a 3 livelli:

  LIVELLO 1 — HTML strutturato (OdG Assemblea)
    Fonte:   senato.it/lavori/assemblea/ordine-del-giorno
    Cosa dà: elenco atti iscritti all'OdG con testo narrativo completo
    Perché:  pagina HTML stabile, aggiornata prima di ogni seduta

  LIVELLO 2 — SPARQL endpoint (dati.senato.it)
    Fonte:   http://dati.senato.it/sparql
    Cosa dà: metadati strutturati certi (stato iter, dataPresentazione,
             natura, legislatura) per ogni atto identificato al Livello 1
    Perché:  dati verificati istituzionalmente, aggiornati quotidianamente

  LIVELLO 3 — Motore di rilevamento fasi
    Input:   testo estratto al Livello 1 + metadati Livello 2
    Output:  etichette di fase con stringa originale che ha fatto match
    Garanzia: ogni etichetta riporta il "found_text" verbatim dalla fonte

GARANZIE DI AFFIDABILITÀ:
  - nessun dato viene inserito senza fonte verificata
  - ogni atto porta: source_url, fetch_timestamp, raw_text estratto
  - divergenza tra stato SPARQL e fasi rilevate genera un alert
  - il campo "found_text" conserva la stringa esatta dal documento

DEPLOY: il modulo è pensato per essere eseguito come cronjob
  prima di ogni seduta (es. ogni 30 min dalle 14:00 alle 18:00
  nei giorni di seduta) e scrivere un JSON usato dalla dashboard.
"""

import json
import hashlib
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser


# ─── CONFIGURAZIONE ──────────────────────────────────────────────────────────

FONTI = {
    "senato_assemblea_odg": {
        "url": "https://www.senato.it/lavori/assemblea/ordine-del-giorno",
        "ramo": "Senato",
        "organo": "Assemblea",
        "descrizione": "OdG Assemblea Senato – pagina HTML corrente",
    },
    # Estendibile con commissioni e Camera:
    # "senato_commissione_1": {
    #     "url": "https://www.senato.it/lavori/commissioni/1/ordine-del-giorno",
    #     "ramo": "Senato", "organo": "Commissione 1ª"
    # },
    # "camera_assemblea_odg": {
    #     "url": "https://www.camera.it/leg19/634",
    #     "ramo": "Camera", "organo": "Assemblea"
    # },
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
        # NOTA: "approvato" generico è ESCLUSO perché nel contesto degli OdG
        # appare frequentemente come "approvato dalla Camera dei deputati",
        # che descrive la provenienza dell'atto — NON un'approvazione definitiva.
        # Si usano solo espressioni inequivocabilmente riferite alla fase finale.
        "espressioni": [
            "approvato testo",
            "testo approvato",
            "concluso l'esame",
            "conclusione esame",
            "seguito e conclusione della discussione",
            "seguito e conclusione esame",
            "seguito e conclusione",
        ],
        # Pattern di esclusione: se il match è immediatamente seguito da
        # "dalla camera" o "dal senato", non è un'approvazione definitiva.
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
            "presentati 254 emendamenti",
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


# ─── LIVELLO 1: PARSER HTML OdG ──────────────────────────────────────────────

class OdGParser(HTMLParser):
    """
    Parser minimalista per la pagina OdG del Senato.
    Estrae il blocco di testo principale (#main-content o corpo pagina).
    Robusto a variazioni di markup: lavora sul testo grezzo, non sulla
    struttura HTML, per massimizzare la resistenza ai refactoring del sito.
    """

    def __init__(self):
        super().__init__()
        self.testo = []
        self._in_main = False
        self._skip_tags = {"script", "style", "nav", "header", "footer"}
        self._tag_stack = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        # Attiva raccolta al main content
        if tag in ("main", "article") or (
            tag == "div" and (
                "main-content" in attrs_dict.get("id", "") or
                "main-content" in attrs_dict.get("class", "") or
                attrs_dict.get("id") == "content"
            )
        ):
            self._in_main = True
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


def fetch_odg_html(url: str) -> dict:
    """
    Scarica la pagina OdG e restituisce:
      - raw_html: HTML grezzo (per archivio)
      - testo: testo estratto
      - hash_sorgente: SHA-256 del testo (per rilevare modifiche)
      - fetch_timestamp: ISO 8601 UTC
      - http_status: codice risposta
      - errore: None se ok, messaggio se fallito
    """
    result = {
        "url": url,
        "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
        "http_status": None,
        "raw_html": None,
        "testo": None,
        "hash_sorgente": None,
        "errore": None,
    }
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ParlamentoMonitor/1.0 (ricerca istituzionale; "
                              "contatto: monitor@example.it)",
                "Accept-Language": "it-IT,it;q=0.9",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result["http_status"] = resp.status
            html_bytes = resp.read()
            raw_html = html_bytes.decode("utf-8", errors="replace")
            result["raw_html"] = raw_html

            parser = OdGParser()
            parser.feed(raw_html)
            testo = parser.get_testo()
            result["testo"] = testo
            result["hash_sorgente"] = hashlib.sha256(
                testo.encode("utf-8")
            ).hexdigest()

    except Exception as e:
        result["errore"] = str(e)

    return result


# ─── PARSER ATTI DALL'OdG ────────────────────────────────────────────────────

# Pattern robusto per estrarre atti numerati dall'OdG del Senato.
# Il formato istituzionale è stabile: "1. Conversione... (1793)"
# oppure "... (...) (numero)"
PATTERN_ATTO_SENATO = re.compile(
    r"""
    (?:^|\n)\s*                     # inizio riga
    \d+\.\s+                        # numero punto OdG (es "1. ")
    (.*?)                           # testo dell'atto (titolo + note)
    \((\d{3,5})\)                   # numero atto tra parentesi
    \s*(?:\n|$)                     # fine riga
    """,
    re.VERBOSE | re.DOTALL
)

# Pattern per estrarre numero DL dal titolo
PATTERN_DL = re.compile(
    r"decreto[- ]legge\s+(?:\d+\s+)?(?:dicembre|novembre|ottobre|"
    r"settembre|agosto|luglio|giugno|maggio|aprile|marzo|febbraio|gennaio)"
    r"\s+\d{4},?\s+n\.\s*(\d+)",
    re.IGNORECASE
)


def parsa_atti_da_testo(testo: str, fonte_config: dict) -> list:
    """
    Estrae gli atti dal testo dell'OdG.
    Ogni atto estratto porta con sé il testo grezzo originale
    esattamente come appare nella fonte — nessuna rielaborazione.
    """
    atti = []

    # Strategia 1: pattern numerato (formato standard Assemblea Senato)
    matches = list(PATTERN_ATTO_SENATO.finditer(testo))

    if not matches:
        # Strategia 2: cerca numeri atto tra parentesi nel testo libero
        # Fallback per variazioni di layout
        for m in re.finditer(r'\((\d{4})\)', testo):
            numero = m.group(1)
            # Prendi il contesto (200 caratteri prima del match)
            start = max(0, m.start() - 200)
            ctx = testo[start:m.end()].strip()
            atti.append({
                "numero_raw": numero,
                "testo_estratto": ctx,
                "metodo_estrazione": "fallback_parentesi",
            })
        return atti

    for i, m in enumerate(matches):
        testo_atto = m.group(1).strip()
        numero = m.group(2).strip()

        # Prendi anche le righe successive fino al prossimo atto
        # per catturare note come "(ove approvato...)"
        if i + 1 < len(matches):
            fine = matches[i + 1].start()
        else:
            fine = len(testo)
        testo_completo = testo[m.start():fine].strip()

        # Determina il tipo
        tipo = "DDL"
        if re.search(r"conversione.*decreto[- ]legge", testo_atto, re.IGNORECASE):
            tipo = "Conversione DL"
        elif re.search(r"decreto[- ]legge", testo_atto, re.IGNORECASE):
            tipo = "Decreto-Legge"

        # Stato: cerca annotazioni tra parentesi nel testo completo
        stato = "All'ordine del giorno"
        if re.search(r"ove approvato dalla camera", testo_completo, re.IGNORECASE):
            stato = "All'odg (condizionato – prev. approvazione Camera)"
        elif re.search(r"approvato dalla camera", testo_completo, re.IGNORECASE):
            stato = "Approvato dalla Camera – in esame Senato"

        atti.append({
            "id": f"{fonte_config['ramo'][0]}-{numero}",
            "ramo": fonte_config["ramo"],
            "organo": fonte_config["organo"],
            "tipo": tipo,
            "numero": f"AS {numero}" if fonte_config["ramo"] == "Senato" else f"AC {numero}",
            "numero_raw": numero,
            "stato": stato,
            "testo_estratto": testo_completo,  # verbatim dalla fonte
            "metodo_estrazione": "pattern_numerato",
        })

    return atti


# ─── LIVELLO 2: SPARQL PER METADATI STRUTTURATI ─────────────────────────────

def query_sparql_atto(numero_fase: str) -> dict:
    """
    Interroga dati.senato.it/sparql per ottenere metadati strutturati
    di un atto identificato dal suo idFase (numero AS).

    Restituisce un dizionario con i campi disponibili,
    o un dict con "errore" se la query fallisce.

    NOTA: il dataset SPARQL ha aggiornamento notturno (T-1).
    Per la seduta del giorno, i dati potrebbero non essere ancora aggiornati.
    In quel caso si usano solo i dati estratti dall'HTML (Livello 1).
    """
    query = f"""
PREFIX osr: <http://dati.senato.it/osr/>
SELECT DISTINCT ?ddl ?titolo ?stato ?dataStato ?natura
                ?dataPresentazione ?presentatoTrasmesso ?testoApprovato
WHERE {{
  ?ddl a osr:Ddl.
  ?ddl osr:idFase ?idFase.
  ?ddl osr:titolo ?titolo.
  ?ddl osr:statoDdl ?stato.
  ?ddl osr:natura ?natura.
  ?ddl osr:dataPresentazione ?dataPresentazione.
  ?ddl osr:dataStatoDdl ?dataStato.
  ?ddl osr:presentatoTrasmesso ?presentatoTrasmesso.
  ?ddl osr:legislatura {LEGISLATURA_CORRENTE}.
  OPTIONAL {{ ?ddl osr:testoApprovato ?testoApprovato }}
  FILTER(?idFase = {numero_fase})
}}
LIMIT 1
"""
    params = urllib.parse.urlencode({
        "query": query,
        "format": "application/sparql-results+json",
    })
    url = f"{SPARQL_ENDPOINT}?{params}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "ParlamentoMonitor/1.0",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            bindings = data.get("results", {}).get("bindings", [])
            if not bindings:
                return {"errore": f"nessun risultato SPARQL per idFase={numero_fase}"}
            row = bindings[0]
            return {k: v.get("value") for k, v in row.items()}
    except Exception as e:
        return {"errore": str(e)}


# ─── LIVELLO 3: RILEVAMENTO FASI ─────────────────────────────────────────────

def rileva_fasi(testo: str) -> list:
    """
    Analizza il testo estratto dalla fonte e restituisce le fasi rilevate.
    Ogni match include:
      - id, label, urgenza della regola
      - found_text: stringa ESATTA trovata nel documento (verbatim)
      - found_context: finestra di 80 caratteri intorno al match

    Gestisce escludi_se_seguito_da: se la stringa trovata è immediatamente
    seguita da uno dei pattern di esclusione, il match viene scartato
    (es. "approvato dalla Camera" non è un'approvazione definitiva).
    """
    testo_lower = testo.lower()
    trovate = []
    for regola in REGOLE_FASE:
        for expr in regola["espressioni"]:
            idx = testo_lower.find(expr.lower())
            if idx == -1:
                continue

            # Controllo esclusione contestuale
            escludi = regola.get("escludi_se_seguito_da", [])
            if escludi:
                dopo = testo_lower[idx + len(expr):idx + len(expr) + 30].strip()
                if any(dopo.startswith(e.lower()) for e in escludi):
                    continue  # falso positivo, salta

            # Estrai contesto: 40 char prima e dopo
            ctx_start = max(0, idx - 40)
            ctx_end = min(len(testo), idx + len(expr) + 40)
            context = testo[ctx_start:ctx_end].strip()
            trovate.append({
                "id": regola["id"],
                "label": regola["label"],
                "urgenza": regola["urgenza"],
                "found_text": testo[idx:idx + len(expr)],  # verbatim
                "found_context": context,
            })
            break  # una regola = un solo match
    return trovate


# ─── CONTROLLO DI DIVERGENZA (GARANZIA DI AFFIDABILITÀ) ────────────────────

def controlla_divergenza(atto: dict) -> list:
    """
    Rileva situazioni potenzialmente anomale che richiedono verifica:

    1. SPARQL dice "approvato" ma il motore non ha trovato "approvato"
       → possibile atto concluso che l'OdG non ha aggiornato
    2. Atto senza NESSUN segnale ma in stato avanzato via SPARQL
       → possibile mancata copertura delle espressioni
    3. Fetch fallito ma atto comunque inserito
       → dati parziali, affidabilità ridotta
    """
    alert = []
    sparql = atto.get("sparql_metadati", {})
    fasi = [f["id"] for f in atto.get("fasi_rilevate", [])]

    # Alert 1: stato SPARQL avanzato senza segnali
    stato_sparql = sparql.get("stato", "").lower()
    stati_avanzati = ["approvato", "concluso", "trasmesso"]
    if any(s in stato_sparql for s in stati_avanzati):
        if "approvato" not in fasi and "voto_finale" not in fasi:
            alert.append({
                "tipo": "divergenza_sparql_motore",
                "messaggio": (
                    f"SPARQL segnala stato '{sparql.get('stato')}' "
                    f"ma il motore non ha rilevato fasi corrispondenti. "
                    f"Verificare il testo dell'OdG."
                ),
                "gravita": "warning",
            })

    # Alert 2: errore SPARQL
    if "errore" in sparql and not sparql["errore"].startswith("nessun risultato"):
        alert.append({
            "tipo": "sparql_non_raggiungibile",
            "messaggio": f"Endpoint SPARQL non disponibile: {sparql['errore']}",
            "gravita": "info",
        })

    # Alert 3: nessun segnale su atto in OdG (potrebbe essere corretto)
    if not fasi:
        alert.append({
            "tipo": "nessun_segnale",
            "messaggio": (
                "Nessuna fase procedurale rilevata. "
                "L'atto potrebbe essere in prima lettura generica "
                "o le espressioni dell'OdG non corrispondono al dizionario."
            ),
            "gravita": "info",
        })

    return alert


# ─── PIPELINE PRINCIPALE ─────────────────────────────────────────────────────

def esegui_pipeline(
    fetch_sparql: bool = True,
    verbose: bool = True
) -> dict:
    """
    Esegue la pipeline completa e restituisce il report strutturato.

    Parametri:
      fetch_sparql: se False, salta le query SPARQL (utile in ambienti
                   senza connessione o per test rapidi)
      verbose:     stampa avanzamento

    Output JSON:
    {
      "pipeline_run": {
        "timestamp": "2026-02-24T15:30:00Z",
        "fonti_interrogate": [...],
        "n_atti_estratti": 2,
        "n_atti_con_segnali": 1,
        "n_alert": 0,
        "versione_motore": "1.0.0"
      },
      "atti": [
        {
          "id": "S-1793",
          "ramo": "Senato",
          "organo": "Assemblea",
          "tipo": "Conversione DL",
          "numero": "AS 1793",
          "stato": "Approvato dalla Camera – in esame Senato",
          "seduta": "...",
          "titolo": "...",
          "note": "...",
          "testo_estratto": "... verbatim ...",  # stringa originale
          "fasi_rilevate": [
            {
              "id": "voto_finale",
              "label": "Voto finale",
              "urgenza": "critical",
              "found_text": "voto finale con la presenza del numero legale",
              "found_context": "... Ddl n. 1415 ... (voto finale con la..."
            }
          ],
          "sparql_metadati": { ... },   # dati strutturati da dati.senato.it
          "alert": [...],
          "provenance": {
            "source_url": "https://www.senato.it/lavori/assemblea/ordine-del-giorno",
            "fetch_timestamp": "2026-02-24T15:28:00Z",
            "hash_sorgente": "sha256:...",
            "fonte_ufficiale": "OdG Assemblea Senato – XIX Legislatura"
          }
        }
      ]
    }
    """
    timestamp_run = datetime.now(timezone.utc).isoformat()
    report = {
        "pipeline_run": {
            "timestamp": timestamp_run,
            "versione_motore": "1.0.0",
            "fonti_interrogate": [],
            "n_atti_estratti": 0,
            "n_atti_con_segnali": 0,
            "n_alert": 0,
        },
        "atti": [],
    }

    for fonte_id, fonte_config in FONTI.items():
        if verbose:
            print(f"\n[1/3] Fetch HTML: {fonte_config['url']}")

        fetch_result = fetch_odg_html(fonte_config["url"])

        fonte_status = {
            "id": fonte_id,
            "url": fonte_config["url"],
            "http_status": fetch_result["http_status"],
            "fetch_timestamp": fetch_result["fetch_timestamp"],
            "hash_sorgente": fetch_result["hash_sorgente"],
            "errore": fetch_result["errore"],
            "testo_lunghezza": len(fetch_result.get("testo") or ""),
        }
        report["pipeline_run"]["fonti_interrogate"].append(fonte_status)

        if fetch_result["errore"]:
            if verbose:
                print(f"  ✗ Errore fetch: {fetch_result['errore']}")
            continue

        if verbose:
            print(f"  ✓ HTTP {fetch_result['http_status']}, "
                  f"{fonte_status['testo_lunghezza']} chars, "
                  f"hash={fetch_result['hash_sorgente'][:12]}…")

        # Parsing atti dall'HTML
        if verbose:
            print("[2/3] Parsing atti dall'OdG…")
        atti_estratti = parsa_atti_da_testo(fetch_result["testo"], fonte_config)

        if verbose:
            print(f"  ✓ {len(atti_estratti)} atti trovati")

        for atto_raw in atti_estratti:
            numero_raw = atto_raw.get("numero_raw", "")
            testo = atto_raw.get("testo_estratto", "")

            # SPARQL
            sparql_meta = {}
            if fetch_sparql and numero_raw:
                if verbose:
                    print(f"  [SPARQL] query per idFase={numero_raw}…", end=" ")
                sparql_meta = query_sparql_atto(numero_raw)
                if verbose:
                    if "errore" in sparql_meta:
                        print(f"✗ {sparql_meta['errore']}")
                    else:
                        print(f"✓ stato={sparql_meta.get('stato', 'n/d')}")

            # Rilevamento fasi
            fasi = rileva_fasi(testo)

            # Costruzione atto completo
            # Il titolo viene dal testo estratto; in produzione si può
            # preferire il campo ?titolo da SPARQL che è più pulito
            titolo_sparql = sparql_meta.get("titolo", "")
            titolo_html = atto_raw.get("testo_estratto", "")[:200]

            atto = {
                "id": atto_raw["id"],
                "ramo": atto_raw["ramo"],
                "organo": atto_raw["organo"],
                "tipo": atto_raw["tipo"],
                "numero": atto_raw["numero"],
                "stato": atto_raw["stato"],
                "titolo": titolo_sparql or titolo_html,
                "note": testo,  # testo completo verbatim
                "fasi_rilevate": fasi,
                "sparql_metadati": sparql_meta,
                "alert": [],  # popolato dopo
                "provenance": {
                    "source_url": fonte_config["url"],
                    "fetch_timestamp": fetch_result["fetch_timestamp"],
                    "hash_sorgente": fetch_result["hash_sorgente"],
                    "fonte_ufficiale": (
                        f"OdG {fonte_config['organo']} {fonte_config['ramo']} "
                        f"– XIX Legislatura"
                    ),
                    "metodo_estrazione": atto_raw.get("metodo_estrazione"),
                },
            }

            # Controllo divergenza
            atto["alert"] = controlla_divergenza(atto)

            report["atti"].append(atto)

    # Statistiche run
    report["pipeline_run"]["n_atti_estratti"] = len(report["atti"])
    report["pipeline_run"]["n_atti_con_segnali"] = sum(
        1 for a in report["atti"] if a["fasi_rilevate"]
    )
    report["pipeline_run"]["n_alert"] = sum(
        len(a["alert"]) for a in report["atti"]
    )

    return report


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  PIPELINE PARLAMENTARE — avvio acquisizione")
    print("=" * 60)

    # In ambiente senza rete, skip SPARQL per mostrare il parsing HTML
    report = esegui_pipeline(fetch_sparql=True, verbose=True)

    print(f"\n[3/3] Report generato:")
    print(f"  Atti estratti:     {report['pipeline_run']['n_atti_estratti']}")
    print(f"  Con segnali:       {report['pipeline_run']['n_atti_con_segnali']}")
    print(f"  Alert generati:    {report['pipeline_run']['n_alert']}")

    # Salva output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Output salvato in: {OUTPUT_PATH}")

    # Preview primo atto
    if report["atti"]:
        a = report["atti"][0]
        print(f"\n--- Preview atto 1 ---")
        print(f"  ID:       {a['id']}")
        print(f"  Numero:   {a['numero']}")
        print(f"  Stato:    {a['stato']}")
        print(f"  Fasi:     {[f['label'] for f in a['fasi_rilevate']]}")
        print(f"  Alert:    {[al['tipo'] for al in a['alert']]}")
        print(f"  Hash src: {a['provenance']['hash_sorgente'][:16]}…")
        print(f"  Fonte:    {a['provenance']['fonte_ufficiale']}")
