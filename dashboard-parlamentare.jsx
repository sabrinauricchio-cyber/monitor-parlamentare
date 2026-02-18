import { useState, useMemo, useEffect } from "react";

// ─── MOTORE DI RILEVAMENTO FASI PROCEDURALI ───────────────────────────────────
// Ogni regola ha: espressioni da cercare (case-insensitive), etichetta breve,
// livello di urgenza (critical / warning / info / done), e configurazione cromatica.

const REGOLE_FASE = [
  {
    id: "approvato",
    label: "Approvato",
    urgenza: "done",
    espressioni: [
      "Approvato testo",
      "Testo approvato",
      "Approvato",
      "concluso l'esame",
      "conclusione esame",
      "Seguito e conclusione della discussione",
      "Seguito e conclusione esame",
      "Seguito e conclusione",
    ],
  },
  {
    id: "voto_finale",
    label: "Voto finale",
    urgenza: "critical",
    espressioni: [
      "voto finale con la presenza del numero legale",
      "Previsto voto finale",
      "Voto finale",
      "voto finale",
    ],
  },
  {
    id: "votazioni",
    label: "Votazioni previste",
    urgenza: "critical",
    espressioni: ["Previste votazioni"],
  },
  {
    id: "emendamenti_approvati",
    label: "Emendamenti approvati",
    urgenza: "warning",
    espressioni: [
      "Approvati emendamenti",
      "approvati emendamenti",
      "approvazione emendamenti",
    ],
  },
  {
    id: "emendamenti_presentati",
    label: "Emendamenti presentati",
    urgenza: "warning",
    espressioni: [
      "Presentati 254 emendamenti",
      "Presentati emendamenti",
      "presentati emendamenti",
    ],
  },
  {
    id: "termine_emendamenti",
    label: "Termine emendamenti",
    urgenza: "warning",
    espressioni: [
      "Fissato termine per la presentazione degli emendamenti",
      "termine per la presentazione degli emendamenti",
      "termine per la presentazione di emendamenti",
    ],
  },
  {
    id: "mandato_relatore",
    label: "Mandato relatore",
    urgenza: "info",
    espressioni: [
      "Conferito mandato al relatore a riferire favorevolmente",
      "Conferito mandato alla relatrice a riferire favorevolmente",
      "Conferito mandato al relatore",
      "Conferito mandato alla relatrice",
      "mandato al relatore a riferire favorevolmente",
    ],
  },
  {
    id: "testo_base",
    label: "Testo base adottato",
    urgenza: "info",
    espressioni: [
      "Adottato testo base testo unificato",
      "Adottato testo base",
      "proposto testo unificato",
    ],
  },
  {
    id: "sede",
    label: "Sede referente/redigente",
    urgenza: "info",
    espressioni: ["Sede referente", "Sede redigente"],
  },
  {
    id: "coordinamento",
    label: "Coordinamento formale",
    urgenza: "info",
    espressioni: ["coordinamento formale"],
  },
];

const URGENZA_CONFIG = {
  critical: { bg: "#fef2f2", border: "#fca5a5", text: "#991b1b", dot: "#dc2626" },
  done:     { bg: "#f0fdf4", border: "#86efac", text: "#14532d", dot: "#16a34a" },
  warning:  { bg: "#fffbeb", border: "#fcd34d", text: "#78350f", dot: "#d97706" },
  info:     { bg: "#eff6ff", border: "#93c5fd", text: "#1e3a8a", dot: "#3b82f6" },
};

// Ordine di priorità per l'urgenza massima
const URGENZA_ORDER = ["critical", "done", "warning", "info"];

function rilevaFasi(atto) {
  const testo = `${atto.titolo} ${atto.note} ${atto.stato}`.toLowerCase();
  const trovate = [];
  for (const regola of REGOLE_FASE) {
    for (const expr of regola.espressioni) {
      if (testo.includes(expr.toLowerCase())) {
        trovate.push({ ...regola, match: expr });
        break; // una regola = un match
      }
    }
  }
  return trovate;
}

function urgenzaMassima(fasi) {
  for (const u of URGENZA_ORDER) {
    if (fasi.some(f => f.urgenza === u)) return u;
  }
  return null;
}

// ─── CONFIGURAZIONE FEED LIVE ─────────────────────────────────────────────────
// URL del JSON prodotto dalla pipeline e pubblicato su GitHub Pages.
// SOSTITUIRE con l'URL reale del proprio repository GitHub Pages.
// Formato: https://<username>.github.io/<repository>/atti_estratti.json
const FEED_URL = "https://TUO_USERNAME.github.io/TUO_REPO/atti_estratti.json";

// Normalizza un atto proveniente dal JSON della pipeline
function normalizzaAtto(a) {
  return {
    id: a.id,
    ramo: a.ramo,
    organo: a.organo,
    tipo: a.tipo,
    titolo: a.titolo || a.testo_estratto?.slice(0, 120) || a.numero,
    numero: a.numero,
    stato: a.stato,
    seduta: a.provenance?.fonte_ufficiale || "–",
    dataOra: a.provenance?.fetch_timestamp || new Date().toISOString(),
    note: a.note || a.testo_estratto || "",
    link: a.link || "https://www.senato.it/lavori/assemblea/ordine-del-giorno",
    fonteUfficiale: a.provenance?.fonte_ufficiale || "–",
    hashSorgente: a.provenance?.hash_sorgente || null,
    alert: a.alert || [],
    fasiPipeline: a.fasi_rilevate || [],
  };
}

// ─── UTILITY ─────────────────────────────────────────────────────────────────
function formatDataOra(iso) {
  const d = new Date(iso);
  const data = d.toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
  const ora = d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  return { data: data.charAt(0).toUpperCase() + data.slice(1), ora: `Ore ${ora}` };
}

// ─── APP ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [filtroRamo, setFiltroRamo] = useState("Tutti");
  const [filtroFase, setFiltroFase] = useState("Tutti");
  const [cerca, setCerca] = useState("");
  const [seguiti, setSeguiti] = useState(new Set());
  const [dettaglio, setDettaglio] = useState(null);
  const [mounted, setMounted] = useState(false);

  // Stato feed live
  const [feedStato, setFeedStato] = useState("caricamento"); // caricamento | ok | errore
  const [feedMeta, setFeedMeta] = useState(null);
  const [attiRaw, setAttiRaw] = useState([]);

  useEffect(() => {
    setTimeout(() => setMounted(true), 50);
    // Carica dati dalla pipeline
    fetch(FEED_URL)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(json => {
        setAttiRaw(json.atti || []);
        setFeedMeta(json.pipeline_run || null);
        setFeedStato("ok");
      })
      .catch(err => {
        console.error("Feed non disponibile:", err);
        setFeedStato("errore");
      });
  }, []);

  const ATTI = useMemo(() =>
    attiRaw.map(a => {
      const norm = normalizzaAtto(a);
      // Usa le fasi già calcolate dalla pipeline server-side,
      // poi arricchisce con il rilevamento client-side sul testo completo
      const fasiClient = rilevaFasi(norm);
      const fasiIds = new Set(norm.fasiPipeline.map(f => f.id));
      // Merge: pipeline ha priorità, client aggiunge eventuali match aggiuntivi
      const fasiMerged = [
        ...norm.fasiPipeline.map(f => ({ ...f, match: f.found_text || f.label })),
        ...fasiClient.filter(f => !fasiIds.has(f.id)),
      ];
      return { ...norm, fasiRilevate: fasiMerged };
    }),
  [attiRaw]);

  const attiFiltrati = useMemo(() => ATTI.filter(a => {
    if (filtroRamo !== "Tutti" && a.ramo !== filtroRamo) return false;
    if (filtroFase !== "Tutti" && !a.fasiRilevate.some(f => f.id === filtroFase)) return false;
    if (cerca && !`${a.titolo} ${a.numero} ${a.note}`.toLowerCase().includes(cerca.toLowerCase())) return false;
    return true;
  }), [ATTI, filtroRamo, filtroFase, cerca]);

  const fasiPresenti = useMemo(() => {
    const ids = new Set(ATTI.flatMap(a => a.fasiRilevate.map(f => f.id)));
    return REGOLE_FASE.filter(r => ids.has(r.id));
  }, [ATTI]);

  const nConSegnali = ATTI.filter(a => a.fasiRilevate.length > 0).length;

  function toggleSeguito(id) {
    setSeguiti(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  const dettaglioObj = dettaglio ? ATTI.find(a => a.id === dettaglio.id) : null;

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=EB+Garamond:ital,wght@0,400;0,500;1,400&family=Roboto+Mono:wght@400;500&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
          --ivory: #f7f4ef; --cream: #ede8df; --parchment: #d9d0be;
          --navy: #0f1e3c; --navy-mid: #1a3260; --navy-light: #2a4a8a;
          --gold: #b8922a; --gold-light: #d4a93c; --gold-pale: #f0e6c8;
          --text: #1a1612; --text-mid: #4a3f2f; --text-light: #7a6f5f;
        }
        body { background: var(--ivory); font-family: 'EB Garamond', Georgia, serif; color: var(--text); }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .app {
          min-height: 100vh; background: var(--ivory);
          background-image:
            radial-gradient(ellipse at 20% 0%, rgba(184,146,42,0.06) 0%, transparent 60%),
            radial-gradient(ellipse at 80% 100%, rgba(15,30,60,0.05) 0%, transparent 60%);
        }

        .top-rule { height: 4px; background: linear-gradient(90deg, var(--navy) 0%, var(--gold) 50%, var(--navy) 100%); }

        /* MASTHEAD */
        .masthead { background: var(--navy); padding: 0 48px; display: flex; align-items: stretch;
          justify-content: space-between; opacity: 0; transform: translateY(-8px);
          transition: opacity 0.6s ease, transform 0.6s ease; }
        .masthead.visible { opacity: 1; transform: translateY(0); }
        .masthead-brand { padding: 28px 48px 28px 0; border-right: 1px solid rgba(255,255,255,0.1); }
        .masthead-eyebrow { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 3px; color: var(--gold); text-transform: uppercase; margin-bottom: 6px; }
        .masthead-title { font-family: 'Playfair Display', serif; font-size: 26px; font-weight: 700; color: #fff; letter-spacing: -0.5px; line-height: 1.1; }
        .masthead-title span { color: var(--gold-light); font-style: italic; }
        .masthead-stats { display: flex; align-items: center; }
        .stat-block { padding: 28px 32px; border-left: 1px solid rgba(255,255,255,0.1); text-align: center; }
        .stat-num { font-family: 'Playfair Display', serif; font-size: 30px; font-weight: 700; color: var(--gold-light); line-height: 1; margin-bottom: 4px; }
        .stat-label { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 2px; color: rgba(255,255,255,0.4); text-transform: uppercase; }

        /* SESSION BANNER */
        .session-banner { background: var(--gold); padding: 10px 48px; display: flex; align-items: center; justify-content: space-between; }
        .session-text { font-family: 'EB Garamond', serif; font-size: 14px; color: var(--navy); font-style: italic; }
        .session-text strong { font-style: normal; font-weight: 600; }
        .session-badge { font-family: 'Roboto Mono', monospace; font-size: 10px; letter-spacing: 2px; color: var(--navy); background: rgba(15,30,60,0.15); padding: 4px 12px; border-radius: 2px; }

        /* LAYOUT */
        .layout { display: grid; grid-template-columns: 300px 1fr; max-width: 1440px; margin: 0 auto; }

        /* SIDEBAR */
        .sidebar { border-right: 1px solid var(--parchment); padding: 36px 26px; background: var(--cream);
          min-height: calc(100vh - 110px); opacity: 0; transform: translateX(-12px);
          transition: opacity 0.6s ease 0.2s, transform 0.6s ease 0.2s; }
        .sidebar.visible { opacity: 1; transform: translateX(0); }
        .sidebar-section { margin-bottom: 32px; }
        .sidebar-label { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 3px; text-transform: uppercase; color: var(--text-light); margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--parchment); }

        .search-input { width: 100%; background: white; border: 1px solid var(--parchment); border-radius: 2px; padding: 10px 14px; font-family: 'EB Garamond', serif; font-size: 15px; color: var(--text); outline: none; transition: border-color 0.2s; }
        .search-input::placeholder { color: var(--text-light); font-style: italic; }
        .search-input:focus { border-color: var(--gold); }

        .filter-group { display: flex; flex-direction: column; gap: 3px; }
        .filter-btn { background: none; border: none; padding: 8px 12px; font-family: 'EB Garamond', serif; font-size: 14px; color: var(--text-mid); cursor: pointer; text-align: left; border-radius: 2px; transition: all 0.15s; display: flex; align-items: center; gap: 10px; }
        .filter-btn:hover { background: var(--ivory); }
        .filter-btn.active { background: var(--navy); color: white; }
        .filter-btn .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; opacity: 0.5; flex-shrink: 0; }
        .filter-btn.active .dot { opacity: 1; background: var(--gold-light); }

        /* FILTRO FASI */
        .fase-tutti-btn { width: 100%; background: none; border: 1px solid var(--parchment); padding: 7px 10px; font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--text-mid); cursor: pointer; text-align: left; border-radius: 2px; transition: all 0.15s; display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
        .fase-tutti-btn:hover { border-color: var(--gold); }
        .fase-tutti-btn.active { background: var(--navy); color: white; border-color: var(--navy); }

        .fase-btn { width: 100%; background: none; padding: 7px 10px; font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; cursor: pointer; text-align: left; border-radius: 2px; transition: all 0.15s; display: flex; align-items: center; gap: 8px; margin-bottom: 4px; border: 1px solid; }
        .fase-btn:hover { filter: brightness(0.95); }
        .fase-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }

        .coverage-list { display: flex; flex-direction: column; gap: 8px; }
        .coverage-item { display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--text-mid); }
        .coverage-item .check { color: var(--gold); }
        .coverage-item.empty { opacity: 0.35; }
        .source-box { background: white; border: 1px solid var(--parchment); border-left: 3px solid var(--gold); padding: 14px 16px; border-radius: 2px; }
        .source-title { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: var(--gold); margin-bottom: 8px; }
        .source-text { font-size: 13px; color: var(--text-mid); line-height: 1.5; margin-bottom: 10px; }
        .source-link { font-family: 'Roboto Mono', monospace; font-size: 11px; color: var(--navy-light); text-decoration: none; }
        .source-link:hover { text-decoration: underline; }

        /* MAIN */
        .main { padding: 40px 44px; opacity: 0; transition: opacity 0.6s ease 0.3s; }
        .main.visible { opacity: 1; }
        .page-header { border-bottom: 2px solid var(--navy); padding-bottom: 18px; margin-bottom: 28px; }
        .page-kicker { font-family: 'Roboto Mono', monospace; font-size: 10px; letter-spacing: 3px; text-transform: uppercase; color: var(--text-light); margin-bottom: 6px; }
        .page-heading { font-family: 'Playfair Display', serif; font-size: 28px; font-weight: 600; color: var(--navy); letter-spacing: -0.5px; }

        /* CARD */
        .atti-grid { display: flex; flex-direction: column; }
        .atto-card { background: white; border: 1px solid var(--parchment); border-bottom: none; padding: 22px 26px; cursor: pointer; transition: all 0.2s; position: relative; display: grid; grid-template-columns: 50px 1fr auto; gap: 18px; align-items: start; }
        .atto-card:last-child { border-bottom: 1px solid var(--parchment); }
        .atto-card:hover { background: var(--gold-pale); z-index: 1; box-shadow: 0 4px 24px rgba(15,30,60,0.1); }
        .atto-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--parchment); }
        .atto-card.u-critical::before { background: #dc2626; }
        .atto-card.u-done::before     { background: #16a34a; }
        .atto-card.u-warning::before  { background: #d97706; }
        .atto-card.u-info::before     { background: #3b82f6; }

        .atto-index { font-family: 'Playfair Display', serif; font-size: 36px; font-weight: 400; color: var(--parchment); line-height: 1; padding-top: 4px; font-style: italic; text-align: center; transition: color 0.2s; }
        .atto-card:hover .atto-index { color: var(--gold); }

        .atto-tags { display: flex; gap: 5px; margin-bottom: 8px; flex-wrap: wrap; align-items: center; }
        .tag { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; padding: 3px 7px; border-radius: 1px; }
        .tag-tipo     { background: var(--navy); color: white; }
        .tag-verified { background: var(--gold-pale); color: var(--gold); border: 1px solid var(--gold); }

        .atto-title-link { display: inline; text-decoration: none; color: inherit; }
        .atto-title-link:hover .atto-title { color: var(--navy-light); text-decoration: underline; text-underline-offset: 3px; }
        .atto-link-icon { display: inline-block; margin-left: 5px; font-family: 'Roboto Mono', monospace; font-size: 11px; color: var(--gold); opacity: 0; transition: opacity 0.2s, transform 0.2s; vertical-align: middle; transform: translate(-2px, -2px); }
        .atto-title-link:hover .atto-link-icon { opacity: 1 !important; transform: translate(1px, -4px); }
        .atto-card:hover .atto-link-icon { opacity: 0.3; }

        .atto-title { font-family: 'Playfair Display', serif; font-size: 16px; font-weight: 400; color: var(--text); line-height: 1.5; display: inline; }
        .atto-meta { display: flex; gap: 16px; margin-top: 8px; flex-wrap: wrap; }
        .atto-meta-item { font-family: 'EB Garamond', serif; font-size: 13px; color: var(--text-light); font-style: italic; }
        .atto-meta-item strong { font-style: normal; color: var(--text-mid); }

        /* SEGNALI sulla card */
        .atto-segnali { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 9px; }
        .segnale-pill { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 1px; text-transform: uppercase; padding: 3px 9px; border-radius: 10px; display: inline-flex; align-items: center; gap: 5px; border: 1px solid; }
        .segnale-more { background: var(--cream); border-color: var(--parchment); color: var(--text-light); }

        .atto-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; padding-top: 2px; }
        .star-btn { width: 32px; height: 32px; background: none; border: 1px solid var(--parchment); border-radius: 2px; cursor: pointer; font-size: 15px; color: var(--text-light); transition: all 0.2s; display: flex; align-items: center; justify-content: center; }
        .star-btn:hover { border-color: var(--gold); color: var(--gold); }
        .star-btn.active { background: var(--gold); border-color: var(--gold); color: white; }
        .atto-number { font-family: 'Roboto Mono', monospace; font-size: 10px; color: var(--text-light); letter-spacing: 1px; }

        .empty-state { text-align: center; padding: 80px 40px; background: white; border: 1px solid var(--parchment); }
        .empty-icon { font-family: 'Playfair Display', serif; font-size: 60px; color: var(--parchment); margin-bottom: 16px; font-style: italic; }
        .empty-title { font-family: 'Playfair Display', serif; font-size: 22px; color: var(--text-mid); margin-bottom: 8px; }
        .empty-sub { font-size: 15px; color: var(--text-light); font-style: italic; }

        /* MODAL */
        .modal-overlay { position: fixed; inset: 0; background: rgba(15,30,60,0.7); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 24px; animation: fadeIn 0.2s ease; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        .modal { background: var(--ivory); max-width: 700px; width: 100%; max-height: 90vh; overflow: auto; box-shadow: 0 32px 80px rgba(0,0,0,0.4); animation: slideUp 0.25s ease; }
        .modal-header { background: var(--navy); padding: 26px 30px; position: relative; }
        .modal-header::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--gold) 0%, transparent 100%); }
        .modal-close { position: absolute; top: 16px; right: 16px; width: 30px; height: 30px; background: rgba(255,255,255,0.1); border: none; color: white; font-size: 17px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background 0.2s; border-radius: 2px; }
        .modal-close:hover { background: rgba(255,255,255,0.2); }
        .modal-eyebrow { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 3px; text-transform: uppercase; color: var(--gold); margin-bottom: 10px; }
        .modal-title-link { text-decoration: none; color: inherit; }
        .modal-title-link:hover .modal-title { text-decoration: underline; text-underline-offset: 4px; }
        .modal-title { font-family: 'Playfair Display', serif; font-size: 19px; font-weight: 600; color: white; line-height: 1.4; padding-right: 40px; }
        .modal-link-icon { display: inline-block; margin-left: 8px; font-family: 'Roboto Mono', monospace; font-size: 12px; color: var(--gold-light); opacity: 0; transition: opacity 0.2s; }
        .modal-title-link:hover .modal-link-icon { opacity: 1; }

        .modal-body { padding: 26px 30px; }
        .modal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 22px; }
        .modal-field { padding: 13px 16px; background: white; border: 1px solid var(--parchment); border-radius: 2px; }
        .modal-field.highlight { border-color: var(--gold); background: var(--gold-pale); }
        .modal-field-label { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: var(--text-light); margin-bottom: 5px; }
        .modal-field-value { font-family: 'Playfair Display', serif; font-size: 14px; color: var(--text); }
        .modal-field.highlight .modal-field-value { color: var(--navy); font-weight: 600; }

        .modal-date-block { background: var(--navy); color: white; padding: 16px 20px; margin-bottom: 18px; display: flex; gap: 24px; align-items: center; }
        .modal-date-text { font-family: 'Playfair Display', serif; font-size: 15px; font-style: italic; }
        .modal-date-ora { font-family: 'Roboto Mono', monospace; font-size: 13px; color: var(--gold-light); }

        /* SEZIONE SEGNALI nel modal */
        .modal-segnali-section { margin-bottom: 20px; }
        .modal-segnali-label { font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: var(--text-light); margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--parchment); }
        .modal-segnale-row { display: flex; align-items: flex-start; gap: 12px; padding: 11px 14px; border-radius: 2px; border-left: 3px solid; margin-bottom: 6px; }
        .modal-segnale-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 2px; }
        .modal-segnale-label { font-family: 'Roboto Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; font-weight: 500; margin-bottom: 3px; }
        .modal-segnale-match { font-size: 13px; font-style: italic; opacity: 0.8; }

        .modal-note { border-left: 3px solid var(--gold); padding: 14px 16px; background: white; margin-bottom: 18px; font-size: 15px; color: var(--text-mid); line-height: 1.7; font-style: italic; }
        .modal-note-label { font-style: normal; font-family: 'Roboto Mono', monospace; font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: var(--gold); margin-bottom: 8px; }
        .modal-source { background: var(--cream); border: 1px solid var(--parchment); padding: 12px 16px; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; }
        .modal-source-check { font-size: 15px; color: var(--gold); }
        .modal-source-text { font-family: 'Roboto Mono', monospace; font-size: 11px; color: var(--text-mid); }
        .modal-actions { display: flex; gap: 12px; }
        .btn-primary { flex: 1; background: var(--navy); color: white; border: none; padding: 13px 16px; font-family: 'EB Garamond', serif; font-size: 15px; cursor: pointer; text-decoration: none; text-align: center; display: block; transition: background 0.2s; }
        .btn-primary:hover { background: var(--navy-mid); }
        .btn-secondary { flex: 1; background: white; color: var(--navy); border: 2px solid var(--navy); padding: 13px 16px; font-family: 'EB Garamond', serif; font-size: 15px; cursor: pointer; transition: all 0.2s; }
        .btn-secondary:hover { background: var(--navy); color: white; }
        .btn-secondary.active { background: var(--gold); border-color: var(--gold); color: var(--navy); font-weight: 600; }
      `}</style>

      <div className="app">
        <div className="top-rule" />

        {/* Masthead */}
        <div className={`masthead ${mounted ? "visible" : ""}`}>
          <div className="masthead-brand">
            <div className="masthead-eyebrow">Repubblica Italiana</div>
            <div className="masthead-title">Parlamento <span>Monitor</span></div>
          </div>
          <div className="masthead-stats">
            <div className="stat-block">
              <div className="stat-num">{ATTI_RAW.length}</div>
              <div className="stat-label">Atti monitorati</div>
            </div>
            <div className="stat-block">
              <div className="stat-num">{nConSegnali}</div>
              <div className="stat-label">Con segnali</div>
            </div>
            <div className="stat-block">
              <div className="stat-num">{seguiti.size}</div>
              <div className="stat-label">Seguiti</div>
            </div>
            <div className="stat-block">
              <div className="stat-num">XIX</div>
              <div className="stat-label">Legislatura</div>
            </div>
          </div>
        </div>

        {/* Session banner */}
        <div className="session-banner">
          <div className="session-text">
            <strong>392ª Seduta Pubblica</strong> — Assemblea del Senato della Repubblica
            &nbsp;·&nbsp; Martedì 24 febbraio 2026, ore 16:30
          </div>
          <div className="session-badge">● LIVE</div>
        </div>

        <div className="layout">
          {/* Sidebar */}
          <aside className={`sidebar ${mounted ? "visible" : ""}`}>

            <div className="sidebar-section">
              <div className="sidebar-label">Ricerca</div>
              <input className="search-input" placeholder="Cerca atti, note…"
                value={cerca} onChange={e => setCerca(e.target.value)} />
            </div>

            <div className="sidebar-section">
              <div className="sidebar-label">Ramo</div>
              <div className="filter-group">
                {["Tutti", "Camera", "Senato"].map(r => (
                  <button key={r} className={`filter-btn ${filtroRamo === r ? "active" : ""}`}
                    onClick={() => setFiltroRamo(r)}>
                    <span className="dot" />{r}
                  </button>
                ))}
              </div>
            </div>

            <div className="sidebar-section">
              <div className="sidebar-label">Fase procedurale</div>

              <button
                className={`fase-tutti-btn ${filtroFase === "Tutti" ? "active" : ""}`}
                onClick={() => setFiltroFase("Tutti")}
              >
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: filtroFase === "Tutti" ? "white" : "#aaa", display: "inline-block", flexShrink: 0 }} />
                Tutti gli atti
              </button>

              {fasiPresenti.map(f => {
                const cfg = URGENZA_CONFIG[f.urgenza];
                const isActive = filtroFase === f.id;
                return (
                  <button key={f.id} className="fase-btn"
                    style={{
                      borderColor: isActive ? cfg.dot : cfg.border,
                      background: isActive ? cfg.bg : "transparent",
                      color: cfg.text,
                    }}
                    onClick={() => setFiltroFase(f.id)}
                  >
                    <span className="fase-dot" style={{ background: cfg.dot }} />
                    {f.label}
                  </button>
                );
              })}
            </div>

            <div className="sidebar-section">
              <div className="sidebar-label">Copertura attuale</div>
              <div className="coverage-list">
                <div className="coverage-item"><span className="check">✓</span><span>OdG Assemblea Senato</span></div>
                <div className="coverage-item"><span className="check">✓</span><span>OdG Commissioni Senato</span></div>
                <div className="coverage-item empty"><span>○</span><span>OdG Assemblea Camera</span></div>
                <div className="coverage-item empty"><span>○</span><span>OdG Commissioni Camera</span></div>
              </div>
            </div>

            <div className="sidebar-section">
              <div className="sidebar-label">Fonte</div>
              <div className="source-box">
                <div className="source-title">Verificato</div>
                <div className="source-text">Dati estratti da ordini del giorno ufficiali pubblicati.</div>
                <a href="https://www.senato.it/lavori/assemblea/ordine-del-giorno"
                  target="_blank" rel="noopener" className="source-link">senato.it →</a>
              </div>
            </div>
          </aside>

          {/* Main content */}
          <main className={`main ${mounted ? "visible" : ""}`}>
            <div className="page-header">
              <div className="page-kicker">
                {filtroFase !== "Tutti"
                  ? `Fase: ${REGOLE_FASE.find(r => r.id === filtroFase)?.label} — `
                  : ""}
                {attiFiltrati.length} {attiFiltrati.length === 1 ? "atto" : "atti"} in agenda
              </div>
              <div className="page-heading">Atti parlamentari</div>
            </div>

            <div className="atti-grid">
              {attiFiltrati.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">∅</div>
                  <div className="empty-title">Nessun atto trovato</div>
                  <div className="empty-sub">Modifica i filtri o attendi la pubblicazione di nuovi ordini del giorno</div>
                </div>
              ) : (
                attiFiltrati.map((atto, i) => {
                  const maxU = urgenzaMassima(atto.fasiRilevate);
                  const fasiCard = atto.fasiRilevate.slice(0, 3);
                  const extra = atto.fasiRilevate.length - 3;
                  return (
                    <div key={atto.id}
                      className={`atto-card${maxU ? ` u-${maxU}` : ""}`}
                      onClick={() => setDettaglio(atto)}
                    >
                      <div className="atto-index">{String(i + 1).padStart(2, "0")}</div>

                      <div className="atto-body">
                        <div className="atto-tags">
                          <span className="tag tag-tipo">{atto.tipo}</span>
                          <span className="tag tag-verified">✓ Verificato</span>
                        </div>
                        <a href={atto.link} target="_blank" rel="noopener noreferrer"
                          className="atto-title-link" onClick={e => e.stopPropagation()}
                          title="Vai alla fonte istituzionale">
                          <span className="atto-title">{atto.titolo}</span>
                          <span className="atto-link-icon">↗</span>
                        </a>
                        <div className="atto-meta">
                          <div className="atto-meta-item"><strong>{atto.numero}</strong></div>
                          <div className="atto-meta-item">{atto.organo} · {atto.ramo}</div>
                          <div className="atto-meta-item">{atto.seduta}</div>
                        </div>
                        {fasiCard.length > 0 && (
                          <div className="atto-segnali">
                            {fasiCard.map(f => {
                              const cfg = URGENZA_CONFIG[f.urgenza];
                              return (
                                <span key={f.id} className="segnale-pill"
                                  style={{ background: cfg.bg, borderColor: cfg.border, color: cfg.text }}>
                                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: cfg.dot, display: "inline-block", flexShrink: 0 }} />
                                  {f.label}
                                </span>
                              );
                            })}
                            {extra > 0 && (
                              <span className="segnale-pill segnale-more">+{extra}</span>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="atto-actions">
                        <button className={`star-btn ${seguiti.has(atto.id) ? "active" : ""}`}
                          onClick={e => { e.stopPropagation(); toggleSeguito(atto.id); }}
                          title="Segui atto">
                          {seguiti.has(atto.id) ? "★" : "☆"}
                        </button>
                        <div className="atto-number">{atto.id}</div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </main>
        </div>

        {/* Banner stato feed */}
        {feedStato === "caricamento" && (
          <div style={{
            position: "fixed", bottom: 24, right: 24, zIndex: 500,
            background: "var(--navy)", color: "white", padding: "12px 20px",
            fontFamily: "'Roboto Mono', monospace", fontSize: 11,
            letterSpacing: 2, borderRadius: 2, display: "flex", alignItems: "center", gap: 10
          }}>
            <span style={{animation: "spin 1s linear infinite", display: "inline-block"}}>⟳</span>
            Caricamento dati in corso…
          </div>
        )}
        {feedStato === "errore" && (
          <div style={{
            position: "fixed", bottom: 24, right: 24, zIndex: 500,
            background: "#991b1b", color: "white", padding: "12px 20px",
            fontFamily: "'Roboto Mono', monospace", fontSize: 11,
            letterSpacing: 1, borderRadius: 2, maxWidth: 320
          }}>
            <div style={{marginBottom: 4, fontWeight: 600}}>⚠ Feed non disponibile</div>
            <div style={{opacity: 0.8, fontSize: 10}}>
              Verificare che la pipeline sia configurata e che FEED_URL sia corretto.
            </div>
          </div>
        )}
        {feedStato === "ok" && feedMeta && (
          <div style={{
            position: "fixed", bottom: 24, right: 24, zIndex: 500,
            background: "rgba(15,30,60,0.92)", color: "white", padding: "10px 16px",
            fontFamily: "'Roboto Mono', monospace", fontSize: 10,
            letterSpacing: 1, borderRadius: 2, lineHeight: 1.8
          }}>
            <div style={{color: "var(--gold)", marginBottom: 2}}>✓ Dati aggiornati</div>
            <div style={{opacity: 0.6}}>{feedMeta.timestamp?.slice(0,16).replace("T"," ")} UTC</div>
            {feedMeta.n_alert > 0 && (
              <div style={{color: "#fcd34d", marginTop: 4}}>
                ⚠ {feedMeta.n_alert} alert da verificare
              </div>
            )}
          </div>
        )}

        {/* Modal */}
        {dettaglioObj && (
          <div className="modal-overlay" onClick={() => setDettaglio(null)}>
            <div className="modal" onClick={e => e.stopPropagation()}>
              <div className="modal-header">
                <button className="modal-close" onClick={() => setDettaglio(null)}>✕</button>
                <div className="modal-eyebrow">Dettaglio atto · {dettaglioObj.ramo}</div>
                <a href={dettaglioObj.link} target="_blank" rel="noopener noreferrer" className="modal-title-link">
                  <div className="modal-title">
                    {dettaglioObj.titolo}
                    <span className="modal-link-icon">↗</span>
                  </div>
                </a>
              </div>

              <div className="modal-body">
                <div className="modal-grid">
                  <div className="modal-field">
                    <div className="modal-field-label">Numero atto</div>
                    <div className="modal-field-value">{dettaglioObj.numero}</div>
                  </div>
                  <div className="modal-field">
                    <div className="modal-field-label">Tipo</div>
                    <div className="modal-field-value">{dettaglioObj.tipo}</div>
                  </div>
                  <div className="modal-field">
                    <div className="modal-field-label">Seduta</div>
                    <div className="modal-field-value">{dettaglioObj.seduta}</div>
                  </div>
                  <div className="modal-field highlight">
                    <div className="modal-field-label">Stato</div>
                    <div className="modal-field-value">{dettaglioObj.stato}</div>
                  </div>
                </div>

                <div className="modal-date-block">
                  <div className="modal-date-text">{formatDataOra(dettaglioObj.dataOra).data}</div>
                  <div className="modal-date-ora">{formatDataOra(dettaglioObj.dataOra).ora}</div>
                </div>

                {/* Segnali procedurali rilevati */}
                {dettaglioObj.fasiRilevate.length > 0 && (
                  <div className="modal-segnali-section">
                    <div className="modal-segnali-label">
                      Segnali procedurali rilevati ({dettaglioObj.fasiRilevate.length})
                    </div>
                    {dettaglioObj.fasiRilevate.map(f => {
                      const cfg = URGENZA_CONFIG[f.urgenza];
                      return (
                        <div key={f.id} className="modal-segnale-row"
                          style={{ background: cfg.bg, borderLeftColor: cfg.dot }}>
                          <span className="modal-segnale-dot" style={{ background: cfg.dot }} />
                          <div>
                            <div className="modal-segnale-label" style={{ color: cfg.text }}>{f.label}</div>
                            <div className="modal-segnale-match" style={{ color: cfg.text }}>
                              Trovato: «{f.match}»
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="modal-note">
                  <div className="modal-note-label">Note</div>
                  {dettaglioObj.note}
                </div>

                <div className="modal-source">
                  <div className="modal-source-check">✓</div>
                  <div className="modal-source-text">{dettaglioObj.fonteUfficiale}</div>
                </div>

                <div className="modal-actions">
                  <a href={dettaglioObj.link} target="_blank" rel="noopener noreferrer" className="btn-primary">
                    Documento ufficiale →
                  </a>
                  <button className={`btn-secondary ${seguiti.has(dettaglioObj.id) ? "active" : ""}`}
                    onClick={() => { toggleSeguito(dettaglioObj.id); setDettaglio(null); }}>
                    {seguiti.has(dettaglioObj.id) ? "★ Seguito" : "☆ Segui atto"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
