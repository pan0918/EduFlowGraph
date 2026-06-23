/**
 * Format a backend UTC timestamp (ISO 8601, e.g. "2026-06-22T12:21:04+00:00")
 * into Beijing time (Asia/Shanghai, UTC+8), 24-hour clock, minute precision.
 *
 * Returns "YYYY-MM-DD HH:mm" by default, or "YYYY-MM-DD" when withTime is false.
 * Returns null for empty/invalid input so callers can fall back gracefully.
 */
export function formatBeijingTime(
  value?: string | null,
  withTime = true,
): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);

  const get = (type: string) =>
    parts.find((part) => part.type === type)?.value ?? "";

  const ymd = `${get("year")}-${get("month")}-${get("day")}`;
  if (!withTime) return ymd;

  // Some engines emit "24" for midnight under hour12:false.
  const hour = get("hour") === "24" ? "00" : get("hour");
  return `${ymd} ${hour}:${get("minute")}`;
}
