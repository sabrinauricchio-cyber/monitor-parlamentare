#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor Parlamentare - STRATO 2: feed RSS di Camera e Senato.

Cosa fa:
  1. Legge il file "feeds.txt", dove tu incolli gli indirizzi dei feed
     ufficiali (ordini del giorno, comunicati di fine seduta, ecc.).
  2. Scarica ogni feed e ne estrae le voci (titolo, link, data).
  3. Scrive tutto in "feed.json", che la dashboard legge.

Anche questo script SI AUTO-COLLAUDA, e lo fa FEED PER FEED:
se un indirizzo e' sbagliato o bloccato, gli altri continuano a
funzionare, e la dashboard ti dice esattamente quale feed ha problemi.

Capisce i tre formati usati dai siti istituzionali:
RSS 2.0, RSS 1.0 (RDF) e Atom.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

FILE_CONFIG = "feeds.txt"
FILE_USCITA = "feed.json"
TIMEOUT = 30
MAX_VOCI_PER_FEED = 25

INTESTAZIONI = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Spazi dei nomi XML che i feed istituzionali usano.
NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss1": "http://purl.org/rss/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
}


def adesso_iso():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def leggi_config():
    """
    Legge feeds.txt. Formato di ogni riga:  Etichetta | https://indirizzo
    Le righe vuote e quelle che iniziano con # vengono ignorate.
    """
    feeds = []
    try:
        with open(FILE_CONFIG, encoding="utf-8") as f:
            for n, riga in enumerate(f, 1):
                riga = riga.strip()
                if not riga or riga.startswith("#"):
                    continue
                if "|" in riga:
                    etichetta, url = riga.split("|", 1)
                else:
                    etichetta, url = "Feed riga %d" % n, riga
                etichetta = etichetta.strip()
                url = url.strip()
                if url.startswith("http"):
                    feeds.append({"etichetta": etichetta, "url": url})
                else:
                    feeds.append({"etichetta": etichetta, "url": url,
                                  "errore_config": "L'indirizzo non inizia con http"})
    except FileNotFoundError:
        return None
    return feeds


def testo(elem):
    if elem is not None and elem.text:
        return re.sub(r"\s+", " ", elem.text).strip()
    return ""


def interpreta_data(grezzo):
    """Prova i formati di data piu' comuni nei feed. Restituisce ISO o ''. """
    if not grezzo:
        return ""
    grezzo = grezzo.strip()
    # Formato email (RSS 2.0): Tue, 10 Jun 2026 18:30:00 +0200
    try:
        return parsedate_to_datetime(grezzo).isoformat()
    except (ValueError, TypeError):
        pass
    # Formato ISO (RSS 1.0 / Atom): 2026-06-10T18:30:00+02:00
    try:
        return datetime.fromisoformat(grezzo.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass
    return grezzo  # meglio mostrarla com'e' che perderla


def estrai_riferimenti_atti(testo_voce):
    """Trova nel testo i numeri di atto (es. A.C. 2911, A.S. 1852, DDL 1234)."""
    trovati = re.findall(
        r"\b(?:A\.?\s?C\.?|A\.?\s?S\.?|C\.|S\.|DDL|ddl)\s?n?\.?\s?(\d{1,5})",
        testo_voce)
    return sorted(set(trovati))


def analizza_xml(contenuto):
    """
    Estrae le voci da un feed, qualunque sia il dialetto:
    RSS 2.0 (<rss><channel><item>), RSS 1.0 (<rdf:RDF><item>), Atom (<feed><entry>).
    """
    radice = ET.fromstring(contenuto)
    tag = radice.tag.lower()
    voci = []

    if tag.endswith("rss"):                      # RSS 2.0
        for item in radice.iter("item"):
            voci.append({
                "titolo": testo(item.find("title")),
                "link": testo(item.find("link")),
                "data": interpreta_data(testo(item.find("pubDate"))
                                        or testo(item.find("dc:date", NS))),
                "descrizione": testo(item.find("description")),
            })
    elif tag.endswith("rdf"):                    # RSS 1.0
        for item in radice.findall("rss1:item", NS):
            voci.append({
                "titolo": testo(item.find("rss1:title", NS)),
                "link": testo(item.find("rss1:link", NS)),
                "data": interpreta_data(testo(item.find("dc:date", NS))),
                "descrizione": testo(item.find("rss1:description", NS)),
            })
    elif tag.endswith("feed"):                   # Atom
        for entry in radice.findall("atom:entry", NS):
            link = entry.find("atom:link", NS)
            voci.append({
                "titolo": testo(entry.find("atom:title", NS)),
                "link": link.get("href", "") if link is not None else "",
                "data": interpreta_data(testo(entry.find("atom:updated", NS))
                                        or testo(entry.find("atom:published", NS))),
                "descrizione": testo(entry.find("atom:summary", NS)),
            })
    return voci


def scarica_feed(feed):
    """Scarica e analizza un singolo feed. Restituisce (esito, messaggio, voci)."""
    if "errore_config" in feed:
        return "ERRORE", feed["errore_config"], []
    try:
        r = requests.get(feed["url"], headers=INTESTAZIONI, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        return "ERRORE", "Indirizzo non raggiungibile: %s" % e, []

    contenuto = r.content
    # Alcuni siti, invece del feed, restituiscono la pagina anti-bot in HTML.
    inizio = contenuto.lstrip()[:200].lower()
    if inizio.startswith(b"<!doctype html") or b"<html" in inizio:
        if b"<rss" not in contenuto[:2000].lower() and b"<rdf" not in contenuto[:2000].lower():
            return ("ERRORE",
                    "Il sito ha risposto con una pagina web invece del feed "
                    "(probabile blocco anti-bot o indirizzo sbagliato).", [])
    try:
        voci = analizza_xml(contenuto)
    except ET.ParseError as e:
        return "ERRORE", "Il contenuto non e' XML valido: %s" % e, []

    if not voci:
        return ("VUOTO",
                "Il feed risponde ed e' valido, ma non contiene voci "
                "(formato non riconosciuto o feed momentaneamente vuoto).", [])

    voci = voci[:MAX_VOCI_PER_FEED]
    for v in voci:
        v["fonte"] = feed["etichetta"]
        v["atti"] = estrai_riferimenti_atti(v["titolo"] + " " + v["descrizione"])
        # La descrizione integrale puo' essere lunga: ne teniamo un estratto.
        v["descrizione"] = v["descrizione"][:300]
    return "OK", "%d voci" % len(voci), voci


def main():
    feeds = leggi_config()

    if feeds is None:
        risultato = {
            "stato": "NON_CONFIGURATO",
            "messaggio": "Il file feeds.txt non esiste nel repository.",
            "aggiornato_il": adesso_iso(),
            "feed": [], "voci": [],
        }
    elif not feeds:
        risultato = {
            "stato": "NON_CONFIGURATO",
            "messaggio": ("Il file feeds.txt esiste ma non contiene ancora "
                          "indirizzi. Apri il file e incolla gli indirizzi dei "
                          "feed seguendo le istruzioni al suo interno."),
            "aggiornato_il": adesso_iso(),
            "feed": [], "voci": [],
        }
    else:
        diagnostica = []
        tutte_le_voci = []
        for feed in feeds:
            esito, msg, voci = scarica_feed(feed)
            diagnostica.append({"etichetta": feed["etichetta"],
                                "esito": esito, "dettaglio": msg})
            tutte_le_voci.extend(voci)
            print("[%s] %s - %s" % (esito, feed["etichetta"], msg))

        # Ordino tutte le voci per data, dalla piu' recente.
        tutte_le_voci.sort(key=lambda v: v.get("data", ""), reverse=True)

        ok = sum(1 for d in diagnostica if d["esito"] == "OK")
        if ok == len(diagnostica):
            stato, messaggio = "OK", "Tutti i %d feed funzionano." % ok
        elif ok > 0:
            stato = "PARZIALE"
            messaggio = ("%d feed su %d funzionano. Controlla il dettaglio "
                         "di quelli con errore." % (ok, len(diagnostica)))
        else:
            stato = "ERRORE"
            messaggio = ("Nessun feed risponde correttamente. Controlla gli "
                         "indirizzi in feeds.txt.")

        risultato = {
            "stato": stato,
            "messaggio": messaggio,
            "aggiornato_il": adesso_iso(),
            "feed": diagnostica,
            "voci": tutte_le_voci,
        }

    with open(FILE_USCITA, "w", encoding="utf-8") as f:
        json.dump(risultato, f, ensure_ascii=False, indent=2)
    print("[%s] %s (voci totali: %d)" % (
        risultato["stato"], risultato["messaggio"], len(risultato["voci"])))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERRORE IMPREVISTO:", e, file=sys.stderr)
        sys.exit(1)
