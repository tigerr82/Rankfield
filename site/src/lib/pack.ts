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

let cachedAll: Promise<Record<string, string>> | null = null;

/** Every text file of the data pack, by name. Fetched once per visit, like the metrics file. */
export function loadPackTexts(): Promise<Record<string, string>> {
  if (!cachedAll) {
    cachedAll = (async () => {
      const [response, { unzipSync, strFromU8 }] = await Promise.all([fetch(packUrl()), import("fflate")]);
      if (!response.ok) throw new Error(`the data pack could not be loaded (${response.status})`);
      const files = unzipSync(new Uint8Array(await response.arrayBuffer()));
      return Object.fromEntries(Object.entries(files).map(([name, bytes]) => [name, strFromU8(bytes)]));
    })();
    cachedAll.catch(() => { cachedAll = null; });
  }
  return cachedAll;
}

/** Zips text files into one downloadable blob. */
export async function zipTexts(files: Record<string, string>): Promise<Blob> {
  const { zipSync, strToU8 } = await import("fflate");
  const zipped = zipSync(Object.fromEntries(Object.entries(files).map(([name, text]) => [name, strToU8(text)])), { level: 9 });
  return new Blob([zipped as BlobPart], { type: "application/zip" });
}
