#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor Parlamentare - STRATO 1: iter dei disegni di legge (Senato, dati aperti).

Cosa fa:
  1. Si collega all'archivio dati ufficiale del Senato (dati.senato.it).
  2. Chiede i disegni di legge che hanno cambiato stato di recente.
  3. Scrive il risultato in "dati.json", che la dashboard legge.

Questo script SI AUTO-COLLAUDA: qualunque cosa succeda scrive sempre
"dati.json" con un messaggio in italiano che spiega com'e' andata.
La dashboard non resta mai muta.
"""

import json
import sys
from datetime import datetime, timezone

import requests

ENDPOINT = "https://dati.senato.it/sparql"
FILE_USCITA = "dati.json"
MAX_ATTI = 60
TIMEOUT = 40

INTESTAZIONI = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MonitorParlamentare/2.0 (uso personale, non commerciale)",
}

# Query minima: "il rubinetto e' aperto?"
QUERY_VITALE = """
SELECT ?ddl WHERE { ?ddl a <http://dati.senato.it/osr/Ddl> . } LIMIT 1
"""

# Query principale: DDL ordinati per data dell'ultimo cambio di stato.
# OPTIONAL sui campi che potrebbero mancare, cosi' un atto incompleto
# non svuota tutta la query.
QUERY_AGGIORNAMENTI = """
PREFIX osr: <http://dati.senato.it/osr/>
SELECT ?ddl ?titolo ?stato ?data ?numeroFase WHERE {
  ?ddl a osr:Ddl ;
       osr:dataStatoDdl ?data .
  OPTIONAL { ?ddl osr:titolo ?titolo . }
  OPTIONAL { ?ddl osr:statoDdl ?stato . }
  OPTIONAL { ?ddl osr:numeroFase ?numeroFase . }
}
ORDER BY DESC(?data)
LIMIT %d
""" % MAX_ATTI


def adesso_iso():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def esegui_query(query):
    risposta = requests.get(
        ENDPOINT,
        params={"query": query},
        headers=INTESTAZIONI,
        timeout=TIMEOUT,
    )
    risposta.raise_for_status()
    return risposta.json()["results"]["bindings"]


def valore(riga, campo):
    if campo in riga and "value" in riga[campo]:
        return riga[campo]["value"].strip()
    return ""


def scrivi_uscita(stato, messaggio, atti):
    contenuto = {
        "stato": stato,
        "messaggio": messaggio,
        "aggiornato_il": adesso_iso(),
        "numero_atti": len(atti),
        "atti": atti,
    }
    with open(FILE_USCITA, "w", encoding="utf-8") as f:
        json.dump(contenuto, f, ensure_ascii=False, indent=2)
    print("[%s] %s (atti: %d)" % (stato, messaggio, len(atti)))


def main():
    # PASSO 1 - La fonte risponde?
    try:
        prova = esegui_query(QUERY_VITALE)
    except requests.exceptions.RequestException as e:
        scrivi_uscita(
            "FONTE_NON_RAGGIUNGIBILE",
            "Non sono riuscito a collegarmi all'archivio del Senato. "
            "Dettaglio tecnico: %s" % e,
            [],
        )
        return
    except (ValueError, KeyError) as e:
        scrivi_uscita(
            "RISPOSTA_NON_VALIDA",
            "La fonte ha risposto ma non nel formato atteso. "
            "Probabile cambio del servizio. Dettaglio: %s" % e,
            [],
        )
        return

    if not prova:
        scrivi_uscita(
            "NESSUN_DATO",
            "Il collegamento funziona, ma l'archivio non ha restituito "
            "alcun disegno di legge. Probabile cambio della struttura dati.",
            [],
        )
        return

    # PASSO 2 - Gli aggiornamenti veri.
    try:
        righe = esegui_query(QUERY_AGGIORNAMENTI)
    except Exception as e:
        scrivi_uscita(
            "QUERY_VUOTA",
            "La fonte e' raggiungibile, ma la richiesta degli aggiornamenti "
            "ha dato errore. Forse e' cambiato il nome di un campo. "
            "Dettaglio: %s" % e,
            [],
        )
        return

    if not righe:
        scrivi_uscita(
            "QUERY_VUOTA",
            "La fonte risponde, ma nessun atto risulta con una data di stato. "
            "Possibile cambio nei nomi dei campi (dataStatoDdl/statoDdl).",
            [],
        )
        return

    # PASSO 3 - Tutto bene.
    atti = []
    for r in righe:
        atti.append({
            "titolo": valore(r, "titolo") or "(senza titolo)",
            "stato": valore(r, "stato"),
            "data": valore(r, "data"),
            "fase": valore(r, "numeroFase"),
            "link": valore(r, "ddl"),
        })

    scrivi_uscita(
        "OK",
        "Aggiornamento riuscito: %d atti con cambio di stato recente." % len(atti),
        atti,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERRORE IMPREVISTO:", e, file=sys.stderr)
        sys.exit(1)
