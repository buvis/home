export function paneTitle(pane) {
  const program = pane.program;
  if (pane.name) return pane.name;
  if (!program?.agent) return (program?.shell && program.name) || pane.title || program?.name || "shell";
  const title = pane.title?.replace(/^[\u2800-\u28ff⏺✻✳]+\s*/u, "").trim();
  if (!title || title === pane.terminal || /^(?:t\d[0-9a-z]*$|\d+$|[~/]|[A-Za-z]:[\\/]|\S+@\S+:|(?:bash|zsh|fish|sh|pwsh|login)(?:\s|$))/i.test(title)) {
    return program.name || "Agent";
  }
  return title;
}
