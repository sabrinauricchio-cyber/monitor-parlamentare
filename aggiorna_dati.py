#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor Parlamentare - STRATO 1: iter degli atti, da ENTRAMBI i rami.

Cosa fa:
  1. Interroga l'archivio dati aperti del Senato (dati.senato.it).
  2. Interroga l'archivio dati aperti della Camera (dati.camera.it).
  3. Fonde i risultati in un unico "dati.json" che la dashboard legge,
     con l'indicazione del ramo per ogni atto.

Le due fonti sono indipendenti: se una non risponde, l'altra continua
a funzionare, e la dashboard mostra la diagnosi di ciascuna.
"""

import json
import re
import sys
from datetime import datetime, timezone, date, timedelta

import requests

FILE_USCITA = "dati.json"
MAX_ATTI_PER_FONTE = 50
TIMEOUT = 60

INTESTAZIONI = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MonitorParlamentare/2.0 (uso personale, non commerciale)",
}

# ---------------------------------------------------------------- SENATO ----

SENATO = {
    "nome": "Senato",
    "endpoint": "https://dati.senato.it/sparql",
    "vitale": "SELECT ?d WHERE { ?d a <http://dati.senato.it/osr/Ddl> . } LIMIT 1",
    "query": """
PREFIX osr: <http://dati.senato.it/osr/>
SELECT ?atto ?titolo ?stato ?data WHERE {
  ?atto a osr:Ddl ;
        osr:dataStatoDdl ?data .
  OPTIONAL { ?atto osr:titolo ?titolo . }
  OPTIONAL { ?atto osr:statoDdl ?stato . }
}
ORDER BY DESC(?data)
LIMIT %d
""" % MAX_ATTI_PER_FONTE,
}

# ---------------------------------------------------------------- CAMERA ----
# Nomi dei campi presi dalla documentazione ufficiale dell'ontologia OCD
# (dati.camera.it): l'atto (ocd:atto) e' legato tramite ocd:rif_statoIter
# a un nodo che porta il titolo della fase (dc:title) e la data (dc:date).
# La legislatura corrente e' la XIX: repubblica_19.

CAMERA = {
    "nome": "Camera",
    "endpoint": "https://dati.camera.it/sparql",
    # Il portale della Camera (software Virtuoso) vuole il formato di
    # risposta come parametro esplicito, non solo nell'intestazione.
    "parametri": {"format": "application/sparql-results+json"},
    "vitale": ("PREFIX ocd: <http://dati.camera.it/ocd/> "
               "SELECT ?a WHERE { ?a a ocd:atto . } LIMIT 1"),
    "query": """
PREFIX ocd: <http://dati.camera.it/ocd/>
PREFIX dc:  <http://purl.org/dc/elements/1.1/>
SELECT DISTINCT ?atto ?titolo ?stato ?data WHERE {
  ?atto a ocd:atto ;
        ocd:rif_leg <http://dati.camera.it/ocd/legislatura.rdf/repubblica_19> ;
        ocd:rif_statoIter ?statoIter .
  ?statoIter dc:date ?data .
  OPTIONAL { ?statoIter dc:title ?stato . }
  OPTIONAL { ?atto dc:title ?titolo . }
}
ORDER BY DESC(?data)
LIMIT %d
""" % MAX_ATTI_PER_FONTE,
}


def adesso_iso():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def esegui_query(endpoint, query, parametri_extra=None):
    parametri = {"query": query}
    if parametri_extra:
        parametri.update(parametri_extra)
    r = requests.get(endpoint, params=parametri,
                     headers=INTESTAZIONI, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def valore(riga, campo):
    if campo in riga and "value" in riga[campo]:
        return riga[campo]["value"].strip()
    return ""


def normalizza_data(grezza):
    """La Camera usa spesso il formato AAAAMMGG: lo rendo leggibile (AAAA-MM-GG)."""
    if re.fullmatch(r"\d{8}", grezza):
        return "%s-%s-%s" % (grezza[0:4], grezza[4:6], grezza[6:8])
    return grezza


def pulisci(atti):
    """
    Scarta i doppioni e gli atti con date impossibili (nell'archivio
    ufficiale esistono refusi come l'anno 2996): una data di iter non
    puo' essere oltre dopodomani.
    """
    soglia = (date.today() + timedelta(days=2)).isoformat()
    visti = set()
    puliti = []
    scartati = 0
    for a in atti:
        chiave = (a["link"], a["data"], a["stato"])
        if chiave in visti:
            scartati += 1
            continue
        visti.add(chiave)
        if a["data"][:10] > soglia:
            scartati += 1
            continue
        puliti.append(a)
    return puliti, scartati


def interroga_fonte(fonte):
    """Interroga una fonte. Restituisce (esito, dettaglio, lista_atti)."""
    parametri = fonte.get("parametri")
    # Passo 1: la fonte risponde?
    try:
        prova = esegui_query(fonte["endpoint"], fonte["vitale"], parametri)
    except requests.exceptions.RequestException as e:
        return "ERRORE", "Fonte non raggiungibile: %s" % e, []
    except (ValueError, KeyError) as e:
        return "ERRORE", "La fonte risponde ma non nel formato atteso: %s" % e, []
    if not prova:
        return ("ERRORE",
                "Il collegamento funziona ma l'archivio non restituisce atti: "
                "probabile cambio della struttura dati.", [])

    # Passo 2: gli aggiornamenti veri.
    try:
        righe = esegui_query(fonte["endpoint"], fonte["query"], parametri)
    except Exception as e:
        return ("ERRORE",
                "Fonte raggiungibile ma la query degli aggiornamenti fallisce "
                "(forse e' cambiato il nome di un campo): %s" % e, [])
    if not righe:
        return ("VUOTO",
                "La fonte risponde ma nessun atto risulta con data di stato: "
                "possibile cambio nei nomi dei campi.", [])

    atti = []
    for r in righe:
        atti.append({
            "ramo": fonte["nome"],
            "titolo": valore(r, "titolo") or "(senza titolo)",
            "stato": valore(r, "stato"),
            "data": normalizza_data(valore(r, "data")),
            "link": valore(r, "atto"),
        })
    atti, scartati = pulisci(atti)
    dettaglio = "%d atti" % len(atti)
    if scartati:
        dettaglio += " (scartate %d righe con date anomale o duplicate)" % scartati
    return "OK", dettaglio, atti


def main():
    diagnostica = []
    tutti = []
    for fonte in (SENATO, CAMERA):
        esito, dettaglio, atti = interroga_fonte(fonte)
        diagnostica.append({"fonte": fonte["nome"],
                            "esito": esito, "dettaglio": dettaglio})
        tutti.extend(atti)
        print("[%s] %s - %s" % (esito, fonte["nome"], dettaglio))

    # Ordino tutti gli atti per data, dal piu' recente.
    tutti.sort(key=lambda a: a.get("data", ""), reverse=True)

    ok = sum(1 for d in diagnostica if d["esito"] == "OK")
    if ok == 2:
        stato, messaggio = "OK", "Entrambe le fonti (Senato e Camera) funzionano."
    elif ok == 1:
        quale = next(d["fonte"] for d in diagnostica if d["esito"] == "OK")
        stato = "PARZIALE"
        messaggio = ("Funziona solo la fonte %s: controlla il dettaglio "
                     "dell'altra qui sotto." % quale)
    else:
        stato = "ERRORE"
        messaggio = "Nessuna delle due fonti risponde correttamente."

    contenuto = {
        "stato": stato,
        "messaggio": messaggio,
        "aggiornato_il": adesso_iso(),
        "fonti": diagnostica,
        "numero_atti": len(tutti),
        "atti": tutti,
    }
    with open(FILE_USCITA, "w", encoding="utf-8") as f:
        json.dump(contenuto, f, ensure_ascii=False, indent=2)
    print("[%s] %s (atti totali: %d)" % (stato, messaggio, len(tutti)))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERRORE IMPREVISTO:", e, file=sys.stderr)
        sys.exit(1)
