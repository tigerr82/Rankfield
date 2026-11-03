import { useState } from "react";
import { usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";
import {
  approxTokensK, companyPrompt, packMetricLines, packUrl, ROW_CHOICES, selectionPrompt, tablePrompt, TABLE_ROWS,
} from "../lib/aiExport";
import { loadMetricsCsv } from "../lib/pack";
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

  const segmentKey: SegmentKey = segment === "insufficient" ? "operating" : segment;
  const tableSize = scores?.segments[segmentKey]?.length ?? 0;
  const limit = rows === "all" ? null : Number(rows);
  const tableLabel = scores?.segments_meta.find((s) => s.key === segmentKey)?.label;

  const copyTable = async () => {
    if (!scores) return;
    const ok = await copy(tablePrompt(scores, segmentKey, limit));
    if (ok) countEvent("ai-copy-table");
    setNote(
      ok
        ? { text: `Copied ${limit == null || limit >= tableSize ? "all" : `the first ${limit}`} ${tableSize ? `of ${tableSize} ` : ""}companies in the ${tableLabel ?? segmentKey} table. Paste it into your assistant.`, ok }
        : { text: "Your browser did not allow copying.", ok },
    );
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
                Choose what to hand your assistant. Each copy includes the scores, the factors, the
                month, and a short explanation of how to read them. <strong>A table copy pastes the first companies in the ranking</strong>, from rank 1 down: {TABLE_ROWS} by default, or more if you choose.
              </p>
              <div className="aibtns">
                <select className="aitick aisel" value={rows} onChange={(e) => setRows(e.target.value)} aria-label="How many companies">
                  {ROW_CHOICES.filter((n) => !tableSize || n < tableSize).map((n) => (
                    <option key={n} value={n}>Top {n}</option>
                  ))}
                  <option value="all">{tableSize ? `All ${tableSize}` : "All"}</option>
                </select>
                <button type="button" className="aibtn" onClick={copyTable} disabled={!scores}>
                  Copy the open table{tableLabel ? ` (${tableLabel})` : ""}
                </button>
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
              <b>Paste into your chat</b>
              <p>Open your assistant in a new conversation and paste.</p>
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

        {rows === "all" && tableSize > 500 && (
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
