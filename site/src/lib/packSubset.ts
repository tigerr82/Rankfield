/**
 * A smaller data pack for the tables a reader chose, cut from the full pack in the browser: the
 * same files and columns, every month, every metric, but only the chosen tables and, when a limit
 * is set, only the companies in each table's top N today. Uploaded as a file, an assistant reads
 * what a question needs rather than the whole table, so it costs few tokens however large it is.
 */

export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i += 1; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cell); cell = "";
      rows.push(row); row = [];
    } else cell += c;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

const quote = (v: string) => (/[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
export const toCsv = (rows: string[][]) => rows.map((r) => r.map(quote).join(",")).join("\n") + "\n";

export interface SubsetOptions {
  /** Table labels as they appear in scores_monthly.csv (column "table"). */
  tables: string[];
  /** Per table label, the tickers kept; a table missing here keeps every company. */
  keep: Record<string, Set<string>>;
  note: string;
}

/** `files`: file name -> text of the full pack. Returns the same names with only the chosen rows. */
export function subsetPack(files: Record<string, string>, opts: SubsetOptions): Record<string, string> {
  const out: Record<string, string> = { ...files };
  const wanted = new Set(opts.tables);

  const scores = parseCsv(files["scores_monthly.csv"] ?? "");
  const head = scores[0] ?? [];
  const iTable = head.indexOf("table"), iTicker = head.indexOf("ticker"), iMonth = head.indexOf("month");
  const kept = scores.slice(1).filter((r) => {
    const table = r[iTable];
    if (!wanted.has(table)) return false;
    const only = opts.keep[table];
    return !only || only.has(r[iTicker]);
  });
  out["scores_monthly.csv"] = toCsv([head, ...kept]);
  const present = new Set(kept.map((r) => `${r[iMonth]}|${r[iTicker]}`));
  const tickers = new Set(kept.map((r) => r[iTicker]));

  const metrics = parseCsv(files["metrics_monthly.csv"] ?? "");
  const mHead = metrics[0] ?? [];
  const mMonth = mHead.indexOf("month"), mTicker = mHead.indexOf("ticker");
  out["metrics_monthly.csv"] = toCsv([mHead, ...metrics.slice(1).filter((r) => present.has(`${r[mMonth]}|${r[mTicker]}`))]);

  const companies = parseCsv(files["companies.csv"] ?? "");
  const cHead = companies[0] ?? [];
  const cTicker = cHead.indexOf("ticker");
  out["companies.csv"] = toCsv([cHead, ...companies.slice(1).filter((r) => tickers.has(r[cTicker]))]);

  const notRanked = parseCsv(files["not_ranked_monthly.csv"] ?? "");
  const nHead = notRanked[0] ?? [];
  const nTable = nHead.indexOf("table");
  out["not_ranked_monthly.csv"] = toCsv([nHead, ...notRanked.slice(1).filter((r) => wanted.has(r[nTable]))]);

  out["README.txt"] = `SUBSET OF THE FULL DATA PACK: ${opts.note}\nThe files below use the same columns as the full pack; only these tables' rows are kept.\n\n${files["README.txt"] ?? ""}`;
  return out;
}
