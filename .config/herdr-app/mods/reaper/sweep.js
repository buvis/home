// Moshi sessions the phone has left: osewa holders running `hc attach` with no
// viewer. `sessions` is `osewa local ls` .sessions, `holders` is
// `pgrep -lf "osewa holder"` output (the only place the holder's command shows).
export function detachedAttachIds(sessions, holders) {
  const attachIds = new Set(
    holders
      .split("\n")
      .filter((line) => line.includes(" hc attach"))
      .map((line) => line.match(/--id ([0-9a-f]+)/)?.[1])
      .filter(Boolean),
  );
  return sessions.filter((s) => s.attached === 0 && attachIds.has(s.id)).map((s) => s.id);
}
