import { useState } from "react";
import { usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";
import {
  ALL_TABLES, approxTokensK, companyPrompt, tableKeys, packMetricLines, packUrl, ROW_CHOICES, selectionPrompt, tablePrompt, TABLE_ROWS,
} from "../lib/aiExport";
import { loadMetricsCsv, loadPackTexts, zipTexts } from "../lib/pack";
import { subsetPack } from "../lib/packSubset";
import { countEvent } from "../lib/track";
import { useApp } from "../state/AppState";
import type { SegmentKey, StockRow } from "../data/types";

async function copy(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Hand the rankings to the reader's own assistant: copy a prompt (the data, a short note on
 * how to read it) and paste it into any chat. Nothing is sent from here, and the page never
 * sees the question that is asked afterwards.
 */
export function AiPage() {
  const { scores, history } = usePayload();
  const { segment } = useApp();
  const scrollRef = useScrollRef();
  const [ticker, setTicker] = useState("");
  const [rows, setRows] = useState<string>(String(TABLE_ROWS));
  const [picked, setPicked] = useState("");
  const [span, setSpan] = useState("all");
  const [depth, setDepth] = useState<"scores" | "latest" | "full">("scores");
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);

  // Which table to copy: starts on the one open in the ranking, and can be any table or all of them.
  const [tableChoice, setTableChoice] = useState<SegmentKey | typeof ALL_TABLES>(segment === "insufficient" ? "operating" : segment);
  const keys = scores ? tableKeys(scores) : [];
  const allTables = tableChoice === ALL_TABLES;
  const segmentKey: SegmentKey = allTables ? "operating" : tableChoice;
  const sizeOf = (key: SegmentKey) => scores?.segments[key]?.length ?? 0;
  const tableSize = allTables ? keys.reduce((n, k) => n + sizeOf(k), 0) : sizeOf(segmentKey);
  const biggest = allTables ? Math.max(0, ...keys.map(sizeOf)) : tableSize;
  const limit = rows === "all" ? null : Number(rows);
  const tableLabel = allTables ? "all tables" : scores?.segments_meta.find((s) => s.key === segmentKey)?.label;

  const copyTable = async () => {
    if (!scores) return;
    const ok = await copy(tablePrompt(scores, tableChoice, limit));
    if (ok) countEvent("ai-copy-table");
    const copied = allTables
      ? keys.reduce((n, k) => n + (limit == null ? sizeOf(k) : Math.min(limit, sizeOf(k))), 0)
      : limit == null ? tableSize : Math.min(limit, tableSize);
    setNote(
      ok
        ? { text: `Copied ${copied} of ${tableSize} companies (${tableLabel}). Paste it into your assistant.`, ok }
        : { text: "Your browser did not allow copying.", ok },
    );
  };

  // The chosen table(s) as a ZIP of the data-pack files, every month and every metric. An
  // assistant that analyses files reads only what a question needs, so size costs few tokens.
  const downloadTables = async () => {
    if (!scores) return;
    setNote({ text: "Preparing the file...", ok: true });
    try {
      const chosen = allTables ? keys : [segmentKey];
      const label = (k: SegmentKey) => scores.segments_meta.find((s) => s.key === k)?.label ?? k;
      const keep: Record<string, Set<string>> = {};
      if (limit != null) {
        for (const k of chosen) {
          keep[label(k)] = new Set([...(scores.segments[k] ?? [])].sort((a, b) => a.rank - b.rank).slice(0, limit).map((r) => r.ticker));
        }
      }
      const names = chosen.map(label);
      const text = await loadPackTexts();
      const subset = subsetPack(text, {
        tables: names, keep,
        note: `${names.join(", ")}; ${limit == null ? "every company ever ranked in them" : `the top ${limit} of each by rank in ${scores.meta.scoring_date.slice(0, 7)}, over every month`}.`,
      });
      const blob = await zipTexts(subset);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `rankfield_${allTables ? "all_tables" : segmentKey}_${scores.meta.scoring_date.slice(0, 7)}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 10000);
      countEvent("ai-download-pack");
      setNote({ text: `Downloaded ${names.join(", ")}. Upload the ZIP to your assistant.`, ok: true });
    } catch (error) {
      setNote({ text: `Could not prepare the file: ${(error as Error).message}.`, ok: false });
    }
  };

  const copyCompany = async () => {
    if (!scores) return;
    const wanted = ticker.trim().toUpperCase();
    const row: StockRow | undefined = (Object.values(scores.segments) as StockRow[][])
      .flat()
      .find((r) => r.ticker.toUpperCase() === wanted);
    if (!row) {
      setNote({ text: wanted ? `${wanted} is not in the ranked tables.` : "Enter a ticker first.", ok: false });
      return;
    }
    const ok = await copy(companyPrompt(scores, row));
    if (ok) countEvent("ai-copy-company");
    setNote(
      ok
        ? { text: `Copied ${row.ticker}. Paste it into your assistant.`, ok }
        : { text: "Your browser did not allow copying.", ok },
    );
  };

  const selection = () => ({
    tickers: picked.split(/[\s,;]+/).filter(Boolean).slice(0, 20),
    months: span === "all" ? null : Number(span),
    depth,
  });
  const selectionText =
    scores && picked.trim() && depth !== "full" ? selectionPrompt(scores, history, selection()) : "";
  const copySelection = async () => {
    if (!scores) return;
    const sel = selection();
    if (!sel.tickers.length) {
      setNote({ text: "Enter at least one ticker.", ok: false });
      return;
    }
    let text = selectionText;
    if (sel.depth === "full") {
      setNote({ text: "Reading the data pack...", ok: true });
      try {
        const csv = await loadMetricsCsv();
        const all = history?.months ?? [];
        const months = sel.months == null ? null : all.slice(-sel.months);
        text = selectionPrompt(scores, history, sel, packMetricLines(csv, scores, sel.tickers, months));
      } catch (error) {
        setNote({ text: `Could not read the data pack: ${(error as Error).message}.`, ok: false });
        return;
      }
    }
    const ok = await copy(text);
    if (ok) countEvent("ai-copy-selection");
    setNote(
      ok
        ? { text: `Copied ${sel.tickers.length} companies, about ${approxTokensK(text)}k tokens. Paste it into your assistant.`, ok }
        : { text: "Your browser did not allow copying.", ok },
    );
  };

  return (
    <Shell scrollRef={scrollRef}>
      <div className="prose" style={{ maxWidth: "88ch" }}>
        <h1>Use Rankfield with your AI</h1>
        <p className="lede">
          Ask Claude, ChatGPT, Gemini, Grok or any other assistant to compare companies, explain a
          score or screen a table. Rankfield prepares the data and the method note; you only paste.
        </p>

        <div className="aisteps">
          <div className="aistep">
            <span className="num">1</span>
            <div>
              <b>Copy</b>
              <p>
                Choose a table, or all tables together, and how many companies from the top of each.
                <strong> Download</strong> gives a ZIP with every month and every metric for them; upload it
                to an assistant that can analyse files, which reads only what your question needs, so even
                all tables cost few tokens. <strong>Copy as text</strong> (one table at a time) pastes the first companies in the ranking, from rank 1
                down ({TABLE_ROWS} by default), with the month and a short note on how to read them; the whole text counts
                toward your chat's limit.
              </p>
              <div className="aibtns">
                <select className="aitick aisel" value={tableChoice} onChange={(e) => setTableChoice(e.target.value as SegmentKey | typeof ALL_TABLES)} aria-label="Which table">
                  {keys.map((k) => (
                    <option key={k} value={k}>{scores?.segments_meta.find((s) => s.key === k)?.label ?? k}</option>
                  ))}
                  <option value={ALL_TABLES}>All tables together</option>
                </select>
                <select className="aitick aisel" value={rows} onChange={(e) => setRows(e.target.value)} aria-label="How many companies">
                  {ROW_CHOICES.filter((n) => !biggest || n < biggest).map((n) => (
                    <option key={n} value={n}>{allTables ? `Top ${n} of each` : `Top ${n}`}</option>
                  ))}
                  <option value="all">{tableSize ? `All ${tableSize}` : "All"}</option>
                </select>
                <button type="button" className="aibtn" onClick={downloadTables} disabled={!scores}>
                  {allTables ? "Download all tables (ZIP)" : "Download the table (ZIP)"}
                </button>
                {!allTables && (
                  <button type="button" className="aibtn alt" onClick={copyTable} disabled={!scores}>
                    Copy as text
                  </button>
                )}
                <input
                  className="aitick"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                  placeholder="Ticker"
                  aria-label="Ticker"
                  maxLength={8}
                />
                <button type="button" className="aibtn alt" onClick={copyCompany} disabled={!scores}>
                  Copy a company
                </button>
                {note && <span className={note.ok ? "aidone" : "aiwarn"}>{note.text}</span>}
              </div>
            </div>
          </div>
          <div className="aistep">
            <span className="num">2</span>
            <div>
              <b>Upload or paste into your chat</b>
              <p>Open your assistant in a new conversation and upload the ZIP, or paste the text.</p>
            </div>
          </div>
          <div className="aistep">
            <span className="num">3</span>
            <div>
              <b>Ask</b>
              <p>Add your question below the pasted text.</p>
            </div>
          </div>
        </div>

        {!allTables && rows === "all" && tableSize > 500 && (
          <p className="muted">
            A whole table of {tableSize} companies is about {Math.round(tableSize * 0.03)}k tokens. Some
            assistants, mainly free plans, may refuse or cut a paste that long; if yours does, choose a
            shorter list.
          </p>
        )}

        <h2>Every month, every metric</h2>
        <div className="aistep">
          <div>
            <b>Download the full data pack</b>
            <p>
              Every month Rankfield has scored: each company's rank, composite and four factor scores,
              and every metric behind them with its raw value and sector percentile. Upload the ZIP to
              an assistant that can analyse files (Claude, ChatGPT, Gemini) and ask about any company,
              metric or month. It is rebuilt with every monthly and weekly update.
            </p>
            <div className="aibtns">
              <a className="aibtn" href={packUrl()} download onClick={() => countEvent("ai-download-pack")}>
                Download rankfield_data_pack.zip
              </a>
              <span className="muted">{scores ? `Through ${scores.meta.scoring_date}` : ""}</span>
            </div>
            <p className="muted">
              <strong>Why a file and not a paste?</strong> Everything at once - every company, every month,
              every metric - is hundreds of thousands of words, and grows every month: far more than a chat accepts as pasted text. As an
              uploaded file the assistant does not read it all: it runs code on it and looks up only what
              your question needs. That works in assistants that can analyse files (Claude, ChatGPT,
              Gemini). If yours cannot, or it only reads pasted text, use the selection copy below.
            </p>
          </div>
        </div>

        <h2>Copy a selection</h2>
        <div className="aistep">
          <div>
            <p>
              A few companies over time, pasted as text: rank, composite and the four factor scores for
              each month. "Plus latest metrics" adds every metric behind the latest month; "every metric,
              every month" adds all of them for each month, so trends can be followed (it reads the
              data pack in your browser, a few seconds the first time). The text can be long: check the
              size shown before pasting.
            </p>
            <div className="aibtns">
              <input
                className="aitick"
                style={{ width: "22ch" }}
                value={picked}
                onChange={(e) => setPicked(e.target.value)}
                placeholder="MU, NVDA, AMD"
                aria-label="Tickers"
              />
              <select className="aitick aisel" value={span} onChange={(e) => setSpan(e.target.value)} aria-label="Months">
                <option value="all">All months</option>
                <option value="6">Last 6 months</option>
                <option value="3">Last 3 months</option>
                <option value="1">Last month only</option>
              </select>
              <select
                className="aitick aisel"
                value={depth}
                onChange={(e) => setDepth(e.target.value as "scores" | "latest" | "full")}
                aria-label="Depth"
              >
                <option value="scores">Scores by month</option>
                <option value="latest">Scores plus latest metrics</option>
                <option value="full">Scores plus every metric, every month</option>
              </select>
              <button type="button" className="aibtn" onClick={copySelection} disabled={!scores}>
                Copy selection
              </button>
              {selectionText && <span className="muted">about {approxTokensK(selectionText)}k tokens</span>}
            </div>
          </div>
        </div>

        <h2>Questions that work well</h2>
        <ul>
          <li>Compare MU and NVDA: which is stronger on value, and why?</li>
          <li>From this table, which five companies combine high Quality with a low Value score, and what do they have in common?</li>
          <li>Explain why this company's rank changed since last month.</li>
          <li>Which sectors in this table have the widest spread of scores?</li>
        </ul>

        <h2>What the assistant receives</h2>
        <pre>{`Rankfield - sector-relative equity scores, month 2026-10-31.
Scores are percentiles (0-100) within a company's own
sector or peer group, so they are relative, not absolute.
Four equal factors: Quality, Growth, Value, Health.
Not investment advice.

[the table or company data]

Method: https://tigerr82.github.io/Rankfield/#/methodology`}</pre>

        <div className="callout">
          <b>Read this first.</b> Rankfield scores are relative rankings, not recommendations. An
          assistant can misread numbers or sound more certain than the data allows; check anything
          that matters against the Methodology page. <b>Nothing here is investment advice.</b>
        </div>
        <p className="muted">
          The site counts page views and clicks on the copy buttons, without cookies or personal
          data. It never sees what you ask your assistant.
        </p>
      </div>
    </Shell>
  );
}
