export function contextRemaining(labels, now) {
  if (labels?.["revive.agent"] !== "claude" || !labels["revive.session"]) return null;
  const reading = labels["herdr.context"];
  if (typeof reading !== "string") return null;
  const [session, remaining, at, extra] = reading.split("|");
  if (extra !== undefined || session !== labels["revive.session"] || !/^(100|[1-9]?\d)$/.test(remaining) || !/^\d+$/.test(at)) return null;
  const age = now - Number(at) * 1000;
  return age >= 0 && age < 10 * 60_000 ? Number(remaining) : null;
}
