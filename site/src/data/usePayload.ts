import { useEffect, useState } from "react";
import { loadCoverage, loadHistoryIndex, loadScores } from "./repository";
import type { CoverageReport, HistoryIndex, ScoresPayload } from "./types";

interface PayloadState {
  scores?: ScoresPayload;
  history?: HistoryIndex;
  loading: boolean;
  error?: string;
}

/** Components read data only through the repository; this hook wraps the two
 *  payloads the table needs so every screen shares one request each. */
export function usePayload(): PayloadState {
  const [state, setState] = useState<PayloadState>({ loading: true });

  useEffect(() => {
    let live = true;
    Promise.all([loadScores(), loadHistoryIndex()])
      .then(([scores, history]) => {
        if (live) setState({ scores, history, loading: false });
      })
      .catch((err: Error) => {
        if (live) setState({ loading: false, error: err.message });
      });
    return () => {
      live = false;
    };
  }, []);

  return state;
}

export function useCoverage(): { coverage?: CoverageReport; loading: boolean; error?: string } {
  const [state, setState] = useState<{ coverage?: CoverageReport; loading: boolean; error?: string }>({
    loading: true,
  });
  useEffect(() => {
    let live = true;
    loadCoverage()
      .then((coverage) => live && setState({ coverage, loading: false }))
      .catch((err: Error) => live && setState({ loading: false, error: err.message }));
    return () => {
      live = false;
    };
  }, []);
  return state;
}

/** Share of applicable metrics actually resolved across every scored stock. */
export function metricCoverage(scores?: ScoresPayload): number | undefined {
  if (!scores) return undefined;
  let total = 0;
  let resolved = 0;
  for (const rows of Object.values(scores.segments)) {
    for (const row of rows) {
      for (const cell of Object.values(row.metrics)) {
        total += 1;
        if (cell.pct != null) resolved += 1;
      }
    }
  }
  return total ? resolved / total : undefined;
}
