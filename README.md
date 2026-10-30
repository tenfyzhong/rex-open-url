# rex-open-url

Pick URLs from the current Rex terminal and open them in your browser.
Inspired by rmux-open-url. Uses Rex's embedded Lua and Python 3.9+ standard
library (including curses). No Rust build, fzf, pip packages, or standalone Lua
runtime is required. macOS is live-tested; Linux needs a URL opener and clipboard
utility, such as xdg-open and wl-copy.

## Install with rexpack

Add `~/.config/rex/plugins/rex-open-url.lua`:

```lua
return {
    "tenfyzhong/rex-open-url",
}
```

Run `rexpack install`, then `rex config reload`. No build hook is needed.
With `dev = { path = "dev" }` in rexpack's setup, a checkout at
`~/.config/rex/dev/rex-open-url` is used automatically.

The plugin registers its action and bindings when loaded, so keep the default
eager loading (`lazy = false`). Rex's Lua API and floating layers are required:
[Lua reference](https://www.superlogical.com/rex/docs/reference/lua).

## Use

Press **prefix + u** (also available in terminal_prefix), or choose
**Open URL: Pick from Current Pane** in the command palette.

- Type to fuzzy-filter, ignoring case.
- Up/Down, Ctrl-k/j, or Ctrl-p/n move the cursor; Ctrl-a/e go first/last.
- Tab toggles selection. Selected URLs remain selected when filtering.
- Enter opens selected URLs, or the current URL if nothing is selected.
- Ctrl-y copies the same selection and keeps the picker open.
- Ctrl-u clears the query; Esc or Ctrl-c cancels.

The picker uses a floating layer over the window, leaving the original tiled
layout and terminal size unchanged. Closing it restores the previous pane.
URLs come from the source pane, even when another pane has focus later.
An empty result is shown as an empty list; no browser is opened automatically.

Recognizes http/https/ftp/file URLs, Git SSH URLs (converted to HTTPS without
a trailing .git), www domains and IPv4 addresses (prefixed with http://), and
standalone `owner/repo` GitHub shorthand. Results are deduplicated in screen
order. Surrounding quotes and unmatched closing brackets are excluded.
Bare GitHub shorthand is intentionally heuristic; disable ambiguity by using
full URLs in terminal output.

## Configure

```lua
return {
    "tenfyzhong/rex-open-url",
    config = function()
        require("rex-open-url").setup({
            -- python = "/absolute/path/to/python3",
            -- rex = "/absolute/path/to/rex",
            -- history_limit = 2000,
            -- open_command = {"open", "-a", "Google Chrome"},
            -- copy_command = {"pbcopy"},
            -- custom_pattern = "[A-Z]+-[0-9]+",
            -- custom_sub = "https://jira.example.com/browse/\\g<0>",
        })
        -- Optional replacement for the default binding:
        -- rex.unbind("prefix/u")
        -- rex.bind("prefix/o", "open_url")
    end,
}
```

Python must be available on the Rex server. Rex is found through the installed
macOS application bundle, falling back to PATH; explicit paths override this.
Open/copy commands run on that server, so remote servers need suitable commands.

By default only the visible screen is searched. `history_limit` searches the last
N exported lines instead. Rex's capture CLI retrieves screen and scrollback before
the picker selects that tail, so very large scrollback can take longer.
Soft-wrapped URLs are joined using Rex's VT export. Visible-screen boundaries
are reconstructed using terminal columns and Unicode character widths; unusual
emoji sequences or custom terminal width rules can make that boundary approximate.

Custom patterns use Python regular expressions and replacement syntax:
`\\g<0>` in Lua represents the complete match; numbered groups are supported.
Command options are argv arrays, never shell command strings. The URL is appended
as a single argument to the opener; copied URLs are joined with newlines and
written to the clipboard command's stdin. Errors stay visible in the picker.

## Development

```sh
make test
REX=/absolute/path/to/rex make integration
```

Unit tests use Python unittest and a Lua interpreter (Lua 5.1 or newer).
GitHub Actions runs these tests. Integration tests require a running Rex;
they create and remove their own test session, exercise selection, filtering,
copy/open command delivery and cancellation, and check layout/focus restoration.
They use temporary recording commands instead of launching browsers or replacing
your clipboard. They do not reload your configuration.
