# chess-tui

A terminal client for **Chess.com** with **Vimium-style move hints**, **multi-account login support**, **official PubAPI integration**, and **deep customization**.

---

## Features

### 1. Vimium-Style Move Input
Play chess without touching the mouse or memorizing algebraic coordinates:
1. Every movable piece on your turn gets a crisp hint badge (e.g. `AB`, `CD`, ...).
2. Type `AB` -> immediately selects that piece.
3. Every legal destination square immediately receives a fresh hint badge (e.g. `BC`, `DE`, ...).
4. Type `BC` -> executes the move!

Supports **4 hint modes**:
- **`dynamic`** *(default)*: Only movable pieces get hints, then only legal destination squares get hints.
- **`static`**: Persistent 64-square Vimium grid (with `AB` / `BC` style coordinates or your own custom 64-square mapping in `config.toml`) for pure muscle memory.
- **`smart`**: Classic Vimium shortest prefix-free tree (1-key moves when targets fit in your alphabet).
- **`coordinate`**: Type algebraic coordinates (`e2` -> `e4`) directly.

Also supports `h/j/k/l` Vim cursor navigation (`Enter`/`Space` to select/move, works on the board & inside all menus), `/Nf3` or `/e2e4` SAN/UCI quick-entry, arrow keys, and terminal mouse clicks.

---

### 2. Login to Any Chess.com Account (Multi-Account Bridge)
Chess.com's official public REST API (`api.chess.com/pub`) is read-only and does not offer an open self-serve live play API. To let you log in securely to **any** Chess.com account (including passwords, 2FA, Google/Apple SSO, and human verification) and play live games from your terminal:

- **Managed Isolated Browser Profiles (CDP Bridge — Low-RAM Headless after Login)**:
  - Run `chess-tui` and press `Ctrl+A` (or `chess-tui account add main --login`).
  - Each account gets its own persistent browser profile directory (`~/.local/share/chess-tui/profiles/<alias>`).
  - First login opens a visible Chromium window to `chess.com/login` so you sign in normally once (passwords, 2FA, Google/Apple SSO, or human verification).
  - Once logged in, `browser_mode = "auto"` switches to a **stripped low-RAM headless Chromium** (`--headless=new`, GPU disabled, single renderer process, images disabled, ad/analytics URLs blocked) and **automatically stops Chromium on exit** (`auto_close_browser_on_exit = true`). You can also stop or switch modes anytime via `Ctrl+A` or `:headless` / `:showbrowser` / `:stopbrowser`.
  - Moves typed in the TUI dispatch trusted pointer events onto `<wc-chess-board>`, while clocks, opponent ratings, move list, and game results sync live back to the terminal.
- **Standalone Browser Extension (`extension/`)**:
  - Prefer your existing Firefox, Chrome, or Brave session? Load the unpacked extension from `extension/` — it connects to `ws://127.0.0.1:8765` inside `chess-tui`.

> **Fair Play Note:** Local UCI engine support (`bridge.uci_engine_path`) is strictly restricted to offline/local games and never runs during live Chess.com games.

---

### 3. Customizable AF
Customize everything live in-app (`Ctrl+S`), via Vim commands (`:`), or in `~/.config/chess-tui/config.toml`:
- **14 Built-in Color Themes**: `chesscom-green`, `chesscom-brown`, `chesscom-icy`, `catppuccin-mocha`, `catppuccin-latte`, `tokyo-night`, `gruvbox-dark`, `dracula`, `nord`, `rose-pine`, `solarized-dark`, `monokai-pro`, `cyberpunk-neon`, `minimal-mono` — plus hex overrides for any element.
- **7 Piece Styles**: `unicode-filled`, `unicode-dual`, `block` (multi-line 5×3 / 7×3 Unicode block-art silhouettes!), `ascii`, `ascii-upper`, `nerd`, and `custom`.
- **5 Square Sizes**: `auto` (responsive), `compact` (5×1), `medium` (7×3), `large` (9×4), `huge` (11×5).
- **Board & Hint Tuning**: Borders (`rounded`, `double`, `heavy`, `ascii`, `none`), coordinates (`outside`, `inside`, `none`), legal move indicators (`dot`, `ring`, `tint`, `both`, `none`), hint alphabet (`ASDFGHJKL`, `ABCDEFGH`, etc.), hint badge position, case sensitivity, Zen mode, Blindfold mode, sidebar position (`left`, `right`, `none`), and fully remappable keybindings.
- **Named Presets**: `:preset save blitz-block` / `:preset load blitz-block`.

---

### 4. Built-in Chess.com PubAPI Features
- **Today's Daily Puzzle & Random Puzzles** (`Ctrl+P` or `chess-tui --puzzle`): Fetch and solve official Chess.com puzzles right in the TUI.
- **Player Stats & Game Archive Replay** (`Ctrl+G`): Look up any Chess.com player's ratings and step through their recent games move by move.
- **Offline Modes**: Local 2-player, Custom FEN sandbox, and optional local UCI engine (`stockfish`).

---

## Installation

Using [`uv`](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/Rutytoi220/chess-tui.git
cd chess-tui
uv sync
uv run chess-tui doctor
uv run chess-tui
```

Or install globally as a tool:

```bash
uv tool install .
chess-tui
```

---

## Quick Controls

| Key | Action |
| --- | --- |
| `AB` -> `BC` | Select piece by Vimium hint, then move to target hint |
| `Esc` / `Backspace` | Cancel selection / edit hint buffer |
| `:` | Open Vim command bar (`:theme`, `:set`, `:pieces`, `:hints`, `:fen`, ...) |
| `/` | Quick SAN or UCI move input (`/Nf3`, `/O-O`, `/e2e4`) |
| `Ctrl+A` | Chess.com Multi-Account Manager |
| `Ctrl+S` | Interactive Customizer (Themes, Hints, Pieces, Layout, Presets) |
| `Ctrl+P` | Play Menu (Chess.com Online, Daily Puzzle, Local 2P, UCI, FEN) |
| `Ctrl+G` | Chess.com Player Stats & Archive Replay |
| `Ctrl+F` | Flip Board |
| `Ctrl+H` | Toggle Vimium Hints |
| `Ctrl+T` | Cycle Themes |
| `Ctrl+Y` | Cycle Board Sizes |
| `Ctrl+Z` | Toggle Zen Mode |
| `Ctrl+B` | Toggle Blindfold Mode |
| `?` | Help & Command Reference |
| `Ctrl+Q` | Quit |

---

## CLI Usage

```bash
chess-tui                          # Launch TUI
chess-tui --account main           # Connect/launch saved account 'main'
chess-tui --theme catppuccin-mocha # Launch with specific theme
chess-tui --puzzle                 # Open today's Chess.com Daily Puzzle
chess-tui account add main --login # Create profile 'main' & open login browser
chess-tui account list             # List saved accounts
chess-tui config themes            # List built-in themes
chess-tui doctor                   # Check browser, extension & paths
```

---

## License

MIT
