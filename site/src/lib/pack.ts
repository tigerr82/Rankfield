import { packUrl } from "./aiExport";

/**
 * Opens the data pack in the browser and returns the one file the selection copy needs. The ZIP
 * is fetched once per visit and the unzip library is loaded only here, so a reader who never asks
 * for every month's metrics downloads neither.
 */
let cached: Promise<string> | null = null;

export function loadMetricsCsv(): Promise<string> {
  if (!cached) {
    cached = (async () => {
      const [response, { unzipSync, strFromU8 }] = await Promise.all([fetch(packUrl()), import("fflate")]);
      if (!response.ok) throw new Error(`the data pack could not be loaded (${response.status})`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      const files = unzipSync(bytes, { filter: (f) => f.name === "metrics_monthly.csv" });
      const file = files["metrics_monthly.csv"];
      if (!file) throw new Error("the data pack has no metrics file");
      return strFromU8(file);
    })();
    cached.catch(() => { cached = null; });
  }
  return cached;
}
