import type { HistoryPoint } from "../data/types";

/** The price to compare across months: adjusted when the payload carries it, else the recorded one.
 *  A recorded price sits on the basis of its own run, so a split reads as a collapse. */
export function comparablePrice(p: HistoryPoint): number | null {
  return p.price_adj !== undefined ? p.price_adj : p.price;
}
