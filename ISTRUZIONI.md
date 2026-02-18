# Istruzioni di Deploy
## Monitor Parlamentare — dalla pipeline al team

---

## Cosa ottieni alla fine

Un sistema che si aggiorna **da solo** prima di ogni seduta:

```
GitHub Actions (pipeline)
        ↓  ogni giorno feriale alle 15, 16, 17
GitHub Pages (JSON dati)
        ↓  in tempo reale
Vercel (dashboard)
        ↓  accessibile dal team con password
```

---

## FASE 1 — Crea il repository su GitHub

1. Vai su **github.com** ed esegui il login
2. Clicca sul pulsante verde **"New"** in alto a sinistra
3. Dai un nome al repository, ad esempio: `monitor-parlamentare`
4. Lascia tutte le altre impostazioni come stanno
5. Clicca **"Create repository"**

---

## FASE 2 — Carica i file nel repository

Una volta creato il repository, vedrai una pagina vuota con scritto "Quick setup".

Clicca su **"uploading an existing file"** (link piccolo nella pagina).

Trascina questi file nella finestra che si apre, rispettando la struttura:

```
.github/
  workflows/
    pipeline.yml          ← workflow di aggiornamento automatico

src/
  pipeline.py             ← il codice della pipeline

public/
  atti_estratti.json      ← file dati iniziale (vuoto)
```

> **Come creare le cartelle durante l'upload:**
> Nella finestra di upload, quando trascini un file, puoi rinominarlo
> includendo il percorso completo. Ad esempio rinomina `pipeline.yml`
> in `.github/workflows/pipeline.yml` — GitHub creerà automaticamente
> le cartelle.

Scrivi un messaggio nel campo "Commit changes" (es. "primo caricamento")
e clicca **"Commit changes"**.

---

## FASE 3 — Attiva GitHub Pages

1. Nel tuo repository, clicca su **"Settings"** (tab in alto)
2. Nel menu a sinistra clicca **"Pages"**
3. Sotto "Source", seleziona **"Deploy from a branch"**
4. Seleziona il branch **"gh-pages"** (se non esiste ancora, comparirà
   dopo la prima esecuzione della pipeline — torna qui dopo la Fase 4)
5. Clicca **Save**

Dopo l'attivazione, il tuo JSON sarà disponibile all'indirizzo:
```
https://TUO_USERNAME.github.io/monitor-parlamentare/atti_estratti.json
```
Segna questo URL — ti servirà nella Fase 5.

---

## FASE 4 — Prima esecuzione manuale della pipeline

1. Nel repository, clicca sulla tab **"Actions"**
2. Vedrai il workflow "Aggiornamento dati parlamentari"
3. Clicca su di esso, poi clicca il pulsante **"Run workflow"**
4. Clicca **"Run workflow"** nel menu a tendina verde

La pipeline girerà per circa 1-2 minuti. Se va a buon fine vedrai
una spunta verde ✓. Se c'è un errore vedrai una X rossa — in quel caso
clicca sul workflow fallito per leggere il log e identificare il problema.

> Dopo la prima esecuzione torna alla **Fase 3** per attivare GitHub Pages
> sul branch gh-pages appena creato.

---

## FASE 5 — Configura l'URL del feed nella dashboard

Apri il file `src/dashboard-parlamentare.jsx` e trova questa riga:

```javascript
const FEED_URL = "https://TUO_USERNAME.github.io/TUO_REPO/atti_estratti.json";
```

Sostituisci `TUO_USERNAME` e `TUO_REPO` con i tuoi valori reali.
Ad esempio se il tuo username GitHub è `mariorossi` e il repository
si chiama `monitor-parlamentare`:

```javascript
const FEED_URL = "https://mariorossi.github.io/monitor-parlamentare/atti_estratti.json";
```

Salva il file e caricalo di nuovo nel repository (sostituendo quello vecchio).

---

## FASE 6 — Deploy della dashboard su Vercel

1. Vai su **vercel.com** e crea un account gratuito (puoi usare "Continue with GitHub")
2. Clicca **"Add New Project"**
3. Seleziona il repository `monitor-parlamentare` dalla lista
4. Nella sezione "Framework Preset" seleziona **"Create React App"** o **"Vite"**
   (se non sai quale scegliere, lascia "Other")
5. In "Root Directory" scrivi `src`
6. Clicca **"Deploy"**

Vercel creerà automaticamente un URL del tipo:
```
https://monitor-parlamentare-xyz.vercel.app
```

---

## FASE 7 — Proteggi la dashboard con password (accesso interno)

Su Vercel, una volta deployata la dashboard:

1. Clicca sul progetto
2. Vai in **"Settings"** → **"Password Protection"**
3. Attiva la protezione e imposta una password
4. Condividi l'URL e la password con il tuo team

---

## Come funziona una volta in produzione

**Aggiornamento automatico:**
La pipeline gira da sola ogni giorno feriale alle 15:00, 16:00 e 17:00 (ora italiana).
Scarica l'OdG dal sito del Senato, estrae gli atti, rileva le fasi procedurali,
pubblica il JSON aggiornato. La dashboard lo legge in tempo reale.

**Esecuzione manuale:**
Se hai bisogno di un aggiornamento immediato (es. l'OdG è cambiato),
vai su GitHub → Actions → "Run workflow".

**Notifiche in caso di errore:**
GitHub invia automaticamente una email all'owner del repository
se la pipeline fallisce. Configura le notifiche in:
Settings → Notifications → Actions.

**Monitoraggio:**
La dashboard mostra nell'angolo in basso a destra lo stato del feed:
- ✓ verde: dati aggiornati, con timestamp dell'ultimo fetch
- ⚠ giallo: alert generati dalla pipeline (divergenze da verificare)
- ✗ rosso: feed non raggiungibile

---

## Troubleshooting

**La pipeline fallisce con "403 Forbidden":**
Il sito del Senato potrebbe bloccare temporaneamente le richieste automatiche.
La pipeline riproverà al ciclo successivo. Se il problema persiste
verificare che l'User-Agent in `pipeline.py` sia aggiornato.

**Il JSON è vuoto o contiene 0 atti:**
La pipeline ha girato ma non ha trovato atti nell'OdG. Probabile che
l'OdG non sia stato ancora pubblicato (normale prima delle 14:00)
o che il layout della pagina sia cambiato. Verificare il log
della pipeline in GitHub → Actions.

**La dashboard mostra "Feed non disponibile":**
Verificare che FEED_URL in `dashboard-parlamentare.jsx` sia corretto
e che GitHub Pages sia attivo. Aprire l'URL del JSON direttamente
nel browser per controllare.

**Voglio aggiungere fonti (commissioni, Camera):**
In `pipeline.py`, nella sezione `FONTI`, decommentare e configurare
le fonti aggiuntive. Ricaricare il file nel repository.
