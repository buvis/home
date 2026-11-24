# Folio

Native, read-only Markdown preview with a Neovim round trip.
The preview uses Solarized Light independently of the surrounding Herdr theme.
Top-level fenced code blocks use Herdr's built-in syntax highlighter with a
Solarized palette. Add a language after the opening fence, such as `javascript`,
`python`, `rust`, `bash`, or `yaml`. Unknown or omitted languages stay plain text.
Code is read-only, selectable and copyable; large blocks scroll internally.
Nested and indented non-Mermaid blocks retain the native Markdown renderer.
Folio uses native Markdown for code after the first 128 highlighted fences.

**Cmd-click** a local Markdown path in a terminal. Folio opens that path in a
split beside the clicked terminal. A link such as `./README.md:42:8` also
passes the line and column to Neovim. Use Ctrl-click on Windows or Linux.

Right-click a terminal or press **Cmd-Shift-O**, then select a listed path.
Markdown (`.md`, `.markdown`, `.mdx`, case insensitive) defaults to **Preview
Markdown**. Other paths default to their system application. **Right**, **Below**
and **Tab** choose placement for previews and terminal editors; each menu starts
with Right selected. The menu lists paths found in the terminal text.
GUI applications always open externally.

**Contents** and same-file `#heading` links scroll to an ATX or Setext heading
in the full preview. Duplicate headings use `-1`, `-2`, and so on. The Neovim
button displays the selected source line. Click it to open that line in
Neovim. Select another heading to change the source line.

**Neovim** replaces the preview in the same region. Save and quit (`:wq`) to
restore the preview with edits, or quit without saving (`:q!`) to discard edits.
Ordinary `:q` retains Neovim's unsaved-change protection. Closing the terminal
pane or its tab does not reopen a preview. Neovim selected directly from the
menu also returns to a preview when editing Markdown. A source position
supplied by a diagnostic link or a heading is restored on return.

The preview follows file changes and has a Reload button. It never writes to
the file. Preview content is limited to 400,000 characters, and Herdr's text
reader has a 1 MiB limit; Neovim receives the original file. MDX is rendered as
Markdown, without evaluating components. Web links use Herdr's URL opener.

Top-level `mermaid` fences render locally in Solarized Light. Folio supports
flowchart, sequence, state, class and ER diagrams within the bundled renderer's
syntax. Invalid, unsupported or oversized diagrams show their source and an
error. The preview renders up to 12 diagrams, each up to 8,000 characters and
160 lines. Diagrams fit the preview width. Folio keeps the 24 most recent
diagram results in memory and keeps successful SVGs in `data/folio-diagrams/`
by content, theme and renderer version. The files persist across launches
and can be cleared while Herdr is closed. See [renderer notices](THIRD_PARTY.md).

`nvim.sh` requires `nvim`, `jq`, `hc`'s `HC_TERMINAL_ID`, and `herdr-app`. It adds
the usual local bin and mise shim directories to PATH for desktop launches.
It discovers its own pane by terminal address, never by current focus. A
replacement is split beside the old pane, swapped into its place, then the old
pane closes. Swapping first preserves sizes: Herdr gives a removed pane's share
to the preceding sibling. No core documents or layout state files are edited.

Validate with `herdr-app check mods/folio` and `herdr-app check mods/on-screen`.
Run regressions with `node --test mods/folio/*.test.mjs`.
In Herdr, check Cmd-click on a terminal with several paths, Contents and
fragment jumps, diagram and fallback rendering, and a Neovim save-and-return
cycle from a diagnostic link and heading.
