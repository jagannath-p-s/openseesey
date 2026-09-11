# OpenSesame — "Sling Ring Cursor + Vanish Illusion" Implementation Plan
### For use with Cursor (Grok). Follow stages in strict order. Do not let the AI skip ahead — each stage has its own working checkpoint before you approve moving to the next.

---

## What we're actually building (read this before pasting anything into Cursor)

The previous version physically moved files via `gio set metadata::nautilus-icon-position`.
That caused DING repaint flicker and position-sync bugs. **This version does not move files
at all.** Instead:

1. When the app activates, the real OS cursor is hidden and replaced with a custom sprite —
   the sling ring image — that follows the mouse.
2. A sparkling "portal opening" burst animates once around the cursor at activation.
3. When the user circles an icon, instead of relocating it, the app makes that icon
   **invisible and unclickable in place** — a controlled illusion, not a real move. The
   underlying file is never touched, renamed, or deleted.
4. Pressing **Esc** reverses every hidden icon back to normal and exits sling mode.

This is a deliberately simpler and more robust mechanism than real repositioning — fewer
moving parts, nothing that can desync with DING's own layout state.

### The hide/unhide mechanism (the one non-obvious technical decision — lock this in now)

Use the `.hidden` file convention: GNOME's `glib`/`gio` layer (not just Nautilus — this is
implemented in `glocalfileinfo.c` itself) reads a plain text file named `.hidden` inside a
directory, one filename per line, and marks any listed file as `is_hidden`. File managers —
including DING, since it enumerates via GIO — skip rendering hidden files by default.

- **To hide an icon:** append its filename to `~/Desktop/.hidden`, then touch/refresh so DING
  re-enumerates the directory.
- **To restore it:** remove that line from `.hidden` and refresh again.
- The real file at `~/Desktop/<name>` is never renamed, moved, or modified. Only a small
  sidecar text file changes.
- This also solves "unclickable" for free — if DING doesn't render the icon, there is nothing
  there to click.

**Fallback if Stage 4's checkpoint shows DING does NOT respect `.hidden`:** displace the icon
off the visible desktop area via `gio set metadata::nautilus-icon-position "-9999,-9999"` (you
already have this mechanism from the old build) and restore the original position on Esc.
Only fall back to this if `.hidden` genuinely fails testing — it's a worse mechanism (still a
real position write, still float-based).

---

## How to work through this with Cursor/Grok

For each stage below:
1. Paste **only that stage's prompt block** into Cursor. Don't paste the whole document at once.
2. Run the "Checkpoint" test yourself before telling the AI to continue.
3. If the checkpoint fails, tell the AI exactly what you observed (not just "it's broken") —
   copy the relevant log lines or the exact visual symptom.
4. Only paste the next stage's prompt once the current checkpoint passes.

This keeps Grok's context small and focused per stage, which matters — a huge combined prompt
increases the odds it hallucinates an API or skips a step.

---

## STAGE 0 — Baseline confirmation (no code changes)

**Prompt for Cursor:**
> Before writing any code, print the following so I can confirm the environment: output of
> `echo $XDG_SESSION_TYPE`, `gnome-shell --version`, `python3 --version`, and check whether
> `PySide6` and `python3-gi` (PyGObject, for `Gio`/`GLib`) are importable. Do not write any
> feature code yet — just this diagnostic script.

**Checkpoint:** Confirm session type is `wayland`, PySide6 imports, and `from gi.repository
import Gio, GLib` imports without error. Don't proceed until both import cleanly.

---

## STAGE 1 — Custom cursor sprite (no portal, no gestures yet)

**Prompt for Cursor:**
> Build a minimal standalone PySide6 script, `stage1_cursor.py`, that:
> - Creates a fullscreen, frameless, translucent/transparent `QWidget` that stays on top of
>   all other windows (`Qt.WindowStaysOnTopHint`, `Qt.FramelessWindowHint`,
>   `Qt.WA_TranslucentBackground`, click-through disabled for now).
> - On show, calls `QGuiApplication.setOverrideCursor(Qt.BlankCursor)` to hide the real
>   system cursor while this widget is active.
> - Tracks real mouse position via `mouseMoveEvent` (enable `setMouseTracking(True)`).
> - In `paintEvent`, draws the image at `appicon.png` (I will supply this file) as a small
>   sprite (~48x48px, scaled) centered on the current tracked mouse position.
> - On pressing `Esc`, calls `QGuiApplication.restoreOverrideCursor()` and closes the widget.
> Do not add gesture detection, portal effects, or icon logic yet — this stage is only:
> real cursor hidden, custom sprite follows mouse, Esc restores everything.

**Checkpoint:** Launch `stage1_cursor.py`. Move the mouse around the whole screen (not just
inside one app window) — the ring sprite should follow smoothly everywhere, the real arrow
cursor should be gone the whole time. Press Esc — real cursor must return immediately. If the
sprite lags or only works inside part of the screen, the overlay isn't actually fullscreen /
isn't receiving move events outside its own bounds — fix that before continuing.

---

## STAGE 2 — Portal "opening" burst effect

**Prompt for Cursor:**
> Extend `stage1_cursor.py` (or create `stage2_portal.py` building on it) to add a one-shot
> "portal opening" animation that plays once when the overlay first activates:
> - A ring/sparkle burst that expands outward from the initial cursor position over ~400-600ms
>   (e.g. an expanding, fading circle with small particle dots rotating outward — simple
>   `QPainter` arcs/ellipses with opacity animated via `QVariantAnimation` or a `QTimer`-driven
>   frame counter; no external animation library needed).
> - After the burst finishes, transition to a subtler continuous idle sparkle around the
>   cursor sprite (a few small dots orbiting slowly) for as long as the overlay is active.
> - Keep this purely visual — no gesture logic yet.

**Checkpoint:** Launch it. Confirm the burst plays once at startup, settles into a subtle
idle sparkle, and doesn't visibly stutter or drop frames on this machine. If it stutters,
reduce particle count before moving on — don't add more features onto a janky base.

---

## STAGE 3 — Wire into the real overlay (merge with existing gesture capture)

**Prompt for Cursor:**
> Now integrate the cursor sprite + portal effect from Stage 2 into the existing
> `overlay.py` (the real gesture-capturing overlay from the main app). Do not rewrite the
> existing gesture detection logic — only add: cursor hiding/sprite rendering, and the portal
> burst-then-idle-sparkle effect, layered into the existing `paintEvent`. Confirm afterward
> that stroke capture for circle-gesture detection still works exactly as before — the cursor
> visual change must not interfere with mouse event handling used for gestures.

**Checkpoint:** Run the full app. Draw a circle gesture as before (on empty space) — confirm
the ring-move behavior from the old build still works, *and* the cursor now shows the sling
ring sprite with idle sparkle throughout. If gesture detection breaks, the sprite rendering is
likely intercepting/consuming mouse events it shouldn't — check event propagation before
continuing.

---

## STAGE 4 — Hide/unhide mechanism, tested standalone first

**Do this stage's testing manually in a terminal before writing any app code**, so you know
the mechanism works on this system before wiring it to gestures.

**Manual test (you run this yourself, not Grok):**
```bash
cd ~/Desktop
echo "knf" >> .hidden          # replace 'knf' with a real desktop icon's filename
# Refresh: click on empty desktop, or briefly switch workspaces, or:
touch .                        # bump directory mtime to encourage a re-enumeration
```
Look at the desktop. Does `knf` disappear? If yes, `.hidden` works on this DING version —
proceed with the primary plan. If it does NOT disappear after a few seconds, note that and
tell the AI to use the off-screen-displacement fallback instead (Stage 4 prompt below has
both variants — tell Grok which one you confirmed).

**Prompt for Cursor (primary variant — `.hidden` confirmed working):**
> Create `vanish.py` with two functions:
> - `hide_icon(desktop_dir: Path, filename: str) -> None` — appends `filename` to
>   `desktop_dir / ".hidden"` if not already present (create the file if it doesn't exist,
>   avoid duplicate lines), then triggers a refresh DING will notice (e.g. touch the
>   directory or the `.hidden` file itself — test both, use whichever reliably triggers
>   DING's file monitor without needing a manual workspace switch).
> - `reveal_icon(desktop_dir: Path, filename: str) -> None` — removes that exact line from
>   `.hidden` (exact match, preserve other entries), then triggers the same refresh.
> - `reveal_all(desktop_dir: Path) -> None` — removes every entry this app added (track
>   which filenames *this session* hid, in an in-memory set — never blindly wipe `.hidden`,
>   since the user or another tool might have unrelated entries in it already).
> Write a tiny manual test at the bottom of the file (`if __name__ == "__main__":`) that
> hides one icon, waits for Enter keypress, then reveals it — so I can verify each direction
> independently.

**Prompt for Cursor (fallback variant — only if `.hidden` did not work):**
> Create `vanish.py` using the existing `icon_registry.set_icon_position()` mechanism instead:
> `hide_icon()` reads and stores the icon's current gio position in memory keyed by filename,
> then writes an off-screen position like `(-9999, -9999)`. `reveal_icon()` writes back the
> stored original position and forgets it. `reveal_all()` restores every currently-displaced
> icon. Same manual test pattern as above.

**Checkpoint:** Run `vanish.py` directly. Confirm the icon disappears on hide and reappears
in its *original* location on reveal — not a new/different location. Confirm the actual file
still exists untouched (`ls ~/Desktop/knf` should still show it) throughout — this is the
whole point, nothing is actually being deleted or moved.

---

## STAGE 5 — Wire vanish into the sling gesture

**Prompt for Cursor:**
> Replace the old "move icon to ring" sling behavior with the vanish illusion. When
> `hit_tester` resolves a gesture to a specific icon (not empty space):
> - Copy the file path to clipboard (keep existing behavior).
> - Play a quick sprite animation: capture the icon's current on-screen rect as a `QPixmap`
>   snapshot (same capture approach as before), animate that snapshot flying from the icon's
>   position to the ring's current position over ~200-300ms on the overlay.
> - The instant the fly-animation completes, call `vanish.hide_icon()` for that file and log
>   `VANISH_OK name=... path=...`.
> - Track which icons are currently hidden this session in a list visible to the overlay (for
>   Stage 6's Esc handling).
> Empty-space circles still just move the ring, unchanged.

**Checkpoint:** Circle a real desktop icon. Confirm: clipboard gets the path, a sprite flies
from the icon to the ring, and the icon vanishes right as the sprite animation finishes (not
before, not with a visible flicker/gap). Circle a second, different icon — confirm the first
one stays hidden and the second also vanishes correctly.

---

## STAGE 6 — Esc restores everything and exits cleanly

**Prompt for Cursor:**
> Wire the Esc key (already used to exit the cursor override in Stage 1) to also call
> `vanish.reveal_all()` for every icon hidden during this session, in addition to restoring
> the real OS cursor and closing the overlay. Order matters: reveal icons first, then restore
> cursor, then close — so the user visually sees their desktop return to normal before the
> ring cursor disappears, not after.

**Checkpoint:** Hide two or three icons via slings, then press Esc. Confirm all of them
reappear in their original positions, the real cursor returns, and the overlay closes — with
no icon left permanently hidden. Then relaunch the app fresh and confirm none of those icons
are still listed in `.hidden` from the previous session (i.e. the restore actually persisted,
it wasn't just visual).

---

## STAGE 7 — Crash safety net (do this before calling it done)

**Prompt for Cursor:**
> Add a startup check: on app launch, before doing anything else, read
> `~/Desktop/.hidden` (or the fallback's persisted-displacement file) and if any icon this
> app previously hid is still hidden from an earlier session that didn't exit cleanly (e.g.
> a crash before Esc), automatically reveal it and log a `RECOVERED_ORPHAN name=...` line.
> To distinguish "our" hidden entries from unrelated ones the user may have added manually,
> prefix or track app-managed entries separately — e.g. maintain a small
> `~/.local/share/opensesame/hidden_by_app.json` listing exactly which filenames this app is
> responsible for, and only auto-reveal those on next launch.

**Checkpoint:** Hide an icon, then force-kill the app (don't press Esc — simulate a crash,
e.g. `kill -9`). Relaunch the app. Confirm the previously-hidden icon is automatically
restored on startup, and the `RECOVERED_ORPHAN` log line appears. This is the difference
between "cute trick" and "thing that quietly eats a user's desktop icon forever" — don't skip
this stage.

---

## Stage order summary (for reference)

| Stage | What it proves works | Don't move on until |
|---|---|---|
| 0 | Environment is sane | Both key libraries import |
| 1 | Custom cursor sprite tracks mouse everywhere | Sprite follows smoothly, Esc restores real cursor |
| 2 | Portal burst + idle sparkle | Animation plays once, no stutter |
| 3 | Cursor/portal merged into real overlay | Old gesture detection still works |
| 4 | Hide/unhide mechanism, standalone | Icon vanishes and reappears in place, file untouched |
| 5 | Vanish wired to sling gesture | Fly animation + vanish, timed correctly, repeatable |
| 6 | Esc restores everything | No icon left hidden after Esc, confirmed on relaunch |
| 7 | Crash recovery | Force-kill test auto-recovers hidden icons on next launch |

Do not let Grok combine stages "to save time" — the whole point of this structure is that
each stage is small enough to verify and cheap to fix before the next one builds on it.