# Folio

Native, read-only Markdown preview with a Neovim round trip. Opened by the
`on-screen` terminal menu with `props: {path: "/absolute/file.md"}`.
The preview uses Solarized Light independently of the surrounding Herdr theme.
Top-level fenced code blocks use Herdr's built-in syntax highlighter with a
Solarized palette. Add a language after the opening fence, such as `javascript`,
`python`, `rust`, `bash`, or `yaml`. Unknown or omitted languages stay plain text.
Code is read-only, selectable and copyable; large blocks scroll internally.
Indented and quoted blocks retain the native Markdown renderer. To bound native
resources, blocks after the first 128 fences also use plain Markdown rendering.

Right-click a terminal or press **Cmd-Shift-O**, then select a listed path.
Markdown (`.md`, `.markdown`, `.mdx`, case insensitive) defaults to **Preview
Markdown**. Other paths default to their system application. **Right**, **Below**
and **Tab** choose placement for previews and terminal editors; each menu starts
with Right selected. GUI applications always open externally.

**Neovim** replaces the preview in the same region. Save and quit (`:wq`) to
restore the preview with edits, or quit without saving (`:q!`) to discard edits.
Ordinary `:q` retains Neovim's unsaved-change protection. Closing the terminal
pane or its tab does not reopen a preview. Neovim selected directly from the
menu also returns to a preview when editing Markdown.

The preview follows file changes and has a Reload button. It never writes to
the file. Preview content is limited to 400,000 characters, and Herdr's text
reader has a 1 MiB limit; Neovim receives the original file. MDX is rendered as
Markdown, without evaluating components. Links use Herdr's standard URL opener.

The existing menu scans local terminal text, not the exact word under the
pointer. Its path filters still apply. Cmd-click and Shift-Cmd-click remain
native Herdr behavior and do not invoke this menu.

`nvim.sh` requires `nvim`, `jq`, `hc`'s `HC_TERMINAL_ID`, and `herdr-app`. It adds
the usual local bin and mise shim directories to PATH for desktop launches.
It discovers its own pane by terminal address, never by current focus. A
replacement is split beside the old pane, swapped into its place, then the old
pane closes. Swapping first preserves sizes: Herdr gives a removed pane's share
to the preceding sibling. No core documents or layout state files are edited.

Validate with `herdr-app check mods/folio` and `herdr-app check mods/on-screen`.
Run parser regressions with `node --test mods/folio/content.test.mjs`.
In the app, check all three placements, a Neovim save-and-return cycle, a path
containing spaces and an apostrophe, and a non-Markdown file's default action.
