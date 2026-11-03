import { useState } from "react";
import { usePayload } from "../data/usePayload";
import { Shell, useScrollRef } from "../components/Shell";
import { companyPrompt, tablePrompt, TABLE_ROWS } from "../lib/aiExport";
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
  const { scores } = usePayload();
  const { segment } = useApp();
  const scrollRef = useScrollRef();
  const [ticker, setTicker] = useState("");
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);

  const segmentKey: SegmentKey = segment === "insufficient" ? "operating" : segment;
  const tableLabel = scores?.segments_meta.find((s) => s.key === segmentKey)?.label;

  const copyTable = async () => {
    if (!scores) return;
    const ok = await copy(tablePrompt(scores, segmentKey));
    if (ok) countEvent("ai-copy-table");
    setNote(
      ok
        ? { text: `Copied the top ${TABLE_ROWS} of the ${tableLabel ?? segmentKey} table. Paste it into your assistant.`, ok }
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
                month, and a short explanation of how to read them. <b>A table copy pastes the first{" "}
                {TABLE_ROWS} companies in the ranking</b>, from rank 1 down.
              </p>
              <div className="aibtns">
                <button type="button" className="aibtn" onClick={copyTable} disabled={!scores}>
                  Copy the top {TABLE_ROWS} of the open table{tableLabel ? ` (${tableLabel})` : ""}
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
