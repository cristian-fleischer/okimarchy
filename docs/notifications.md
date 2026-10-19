# Notifications

The shell is the notification daemon: `shell/plugins/notifications/Service.qml` hosts a Quickshell `NotificationServer` that claims `org.freedesktop.Notifications` on the session bus. There is no dunst or mako — anything that speaks the freedesktop notification protocol (notify-send, libnotify apps, Chromium web apps, KDE Connect) lands in the shell, which draws it as a card in a deck hanging from the top-right corner. The engine began as the Omapager plugin by Neil Jagdish Patel (MIT, https://github.com/omacom/omapager) and moved into core; `migrations/1792376022.sh` carries Omapager's state and settings across.

The end-user view is in `manual/10-notices.md`; this document is the system shape behind it.

## Files

| File | Role |
|---|---|
| `Service.qml` | The daemon: admission, quiet rules, snoozes, the scene clock, routing a click, replies, offers, IPC, and one layer surface per output |
| `Toast.qml`, `DeedButton.qml` | One card and its buttons. A card is told where it is; it animates nothing of its own position |
| `NotificationPanel.qml`, `Picker.qml` | The panel and its preferences page, hosted by the bar's Dnd indicator (`shell/plugins/bar/indicators/Dnd.qml`) |
| `Store.js` | Snapshot of a notification, normalisation, persistence redaction, restore |
| `Markup.js` | Body markup: the safe subset, source lifting ("web:app.slack.com"), KDE Connect forwarding, one-line previews |
| `Detect.js` | Verification codes, links, meeting links and phone numbers in the text |
| `Security.js` | URL policy, bounds, the `omarchy-exec-argv` structural check, glyph check |
| `Layout.js` | Pure deck layout: rows in, placements out |
| `Delivery.js` | Quiet rules, ephemeral rules, bar clearance |
| `Settings.js` | Defaults and validation for the `notifications` object in `shell.json` |
| `helpers/` | Python helpers: `run` (Bubblewrap launcher), `store`, `icon`, `kdeconnect` |

The JS modules load in Node as well as QML, so `test/shell.d/notifications-test.sh` exercises them (and the admission and close functions lifted out of `Service.qml`) without a compositor. `test/shell.d/notification-helpers-test.sh` covers the helpers.

## Decks and the scene clock

Each notification gets a key of our own (`n…`), because the sender's id identifies a slot that `replaces_id` reuses, not an event. Cards group by source: per site for anything arriving through a browser (the leading `<a href>` Chromium puts on every web notification is lifted off and becomes the source), per forwarded app for KDE Connect, per app name otherwise. `stacking: "all"` puts everything in one deck instead.

A collapsed deck draws its cards at the front card's height, peeking out beneath it; hovering a deck opens it. While the pointer is on an open deck, or a reply is being typed, a genuinely new card is held back rather than inserted under the pointer, for at most 30 seconds. Every card's position, scale, opacity and height come from one clock (`Service.at()`): a change snapshots where everything is, recomputes the layout, and starts one move for all cards from that instant. A leaving card keeps its model row until that move finishes, so its fade and the gap closing are one motion.

The live `Notification` objects stay in a plain JS map (`refs`), never in a ListModel role, which would become a dangling pointer when the server destroys the object. At most 100 notifications are live at once.

The surface is one fixed-width `WlrLayer.Overlay` window per output under the namespace `omarchy-notifications`, masked to the deck so everything else stays click-through. It stays mapped while idle — a layer surface coming and going makes Hyprland re-evaluate focus, which drags a scrolling layout's viewport — except that `fullscreenOverlay` (default `all`) unmaps it under a fullscreen window when there is nothing to show, so the window can be scanned out directly. The `-away` variants never cover a fullscreen window: cards go to another output, or wait in Recent.

## Toast lifecycle

A card lives on screen for at least 5s (low), 8s (normal), or forever (critical), stretched up to 30s if the sender asked for a longer `expire_timeout`. The countdown pauses while the deck is open or a reply is being typed, and a content update restarts it. Left-click activates (see below), middle-click dismisses, right-click opens the source menu (snooze lengths, Do Not Disturb).

A click runs, in order: the card's `omarchy-exec-argv` command; the sender's `default` action (`allowDefaultActionOnCardClick`, on by default); the sender's own window, found by the sender's pid; a window showing the source (an exact class match, then, for a site, a browser window whose title names it); the site itself; the first link in the text; and finally `omarchy-hyprland-focus-app` by app name.

## Persistence

The store (`helpers/store`) keeps one file per notification under `~/.local/state/omarchy/notifications/`: `live/KEY.json` while a card is on screen (or was, when the shell went down), moved to `history/<ms>-KEY.json` when it closes. History is trimmed to 100 entries and `historyHours` (default 24, `0` keeps none). A notification whose text carries a verification code is redacted before it is written. Rows carry `execArgv` and `glyph`, so a card restored after a shell restart — `omarchy update` restarts the shell under its own installer toasts — clicks through exactly like the live one. Restored cards get a 20s grace rather than their original timeout. `quiet.json` holds Do Not Disturb, snoozes and the code exception; `icons/` is the icon helper's own working cache (fetched site icons and their index), which the shell never reads.

The helpers run under Bubblewrap when it works. Without a working sandbox the store and KDE Connect helpers run directly as the user, unless `requireSandbox` is set, in which case they are blocked too; the icon helper never runs unsandboxed, because decoding images from websites and senders is the riskiest thing the helpers do, so cards fall back to a letter tile. `omarchy-shell notifications probe` reports the mode, and the panel's preferences say when icons are off.

Icons resolve per source, once: a sender's own image wins, then a local or themed icon, then, with `fetchRemoteIcons` on, the site's own icon fetched over HTTPS from a public address. Every image the helpers read, local, fetched or sent, is decoded by ImageMagick (`helpers/notification_images.py`) under the bundled `helpers/policy.xml`, which denies every coder, delegate, filter and `@file` read except the few below. The format is sniffed from its signature first, so only PNG, JPEG, WebP and ICO (at most 64 frames) reach their own coder, with memory, size and time limits. Local SVG icons are rasterised by librsvg from stdin, where an `<image>` or entity naming another file has nothing to resolve against; no SVG ever reaches Qt. A sender's own image file is opened and read by a forked child of the launcher under a 5-second deadline, so a stalled mount cannot hold the launcher, and is refused if it is empty, oversized, not a regular file, or lives on a kernel filesystem (`/proc`, `/sys`, `/dev`, checked by path and by filesystem type); the helper decodes a sealed in-memory copy. The helper hands back raw pixels, never a file: the launcher (`helpers/run`, outside the sandbox) reads at most one 128px RGBA image from its pipe, builds the PNG itself, and publishes it as `~/.cache/omarchy/notification-icons/<sha256>[-mono].png`, a directory no sandbox mounts, or, for a sender's image, as a `data:image/png` URL. The shell reads that answer through a capped parser and takes only a digest-named path in that directory, from a launcher that exited cleanly, or a data URL that starts with a PNG header, so nothing a decoder wrote is ever opened by Qt. Favicon pages are read with the stdlib HTML parser, which is linear in the page, and one icon job gets 20 seconds. User overrides go in `~/.config/omarchy/notifications/icons/`.

## Silencing and snoozing

Do Not Disturb is a boolean persisted in `quiet.json` and toggled via shell IPC (`omarchy-shell notifications toggleDnd` / `setDnd` / `dndState`). `omarchy-toggle-notification-silencing` wraps the toggle. A snooze is the same quiet with an end time, per source (`groupKey`) or for everything (key `*`); snoozing everything replaces Do Not Disturb.

Three kinds of notification punch through every kind of quiet, chosen to be intentional and rare:

- `app_name` = `omarchy-action` — Omarchy's own user-action confirmation toasts ("Theme changed"). The user just did something; their feedback shows.
- urgency critical *and* `app_name` = `notify-send` — bare-CLI emergency alerts. Critical alone is not enough, because chat apps abuse it to force visibility; they set `app_name` to their brand, which fails this rule.
- a detected verification code, while `codesBypassQuiet` is on (the panel's key button).

A quieted notification that anyone might look back at is recorded as held, which the panel lists by source. Ephemeral ones (the freedesktop `transient` hint, or an `app_name` of `notify-send`/`omarchy-action`) are dropped entirely.

When the Hyprland portal starts a screen-share stream, the bell offers a timed snooze. It never mutes anything by itself.

## Preferences

Preferences live in the `notifications` object of `~/.config/omarchy/shell.json`; every key is optional and `Settings.js` holds the defaults. The panel's preferences page writes `displayMode`/`displayName`, `fullscreenOverlay`, `stacking`, `showCountdown` and `offerSnoozeWhenSharing`. The rest are hand-edited: `edgeSpacing` (unset follows the theme's outer gap), `fontScale`, `actionsAlign`, `hideSettingsAction`, `snoozeDurations`, `wakeHour`, `smartRaise`, `codesBypassQuiet`, `timeFormat`, `sourceLimit`, `heldPerSource`, `recentCount`, `fetchRemoteIcons`, `requireSandbox`, `allowDefaultActionOnCardClick`, `historyHours`, `clipboardTimeout`. Colours, borders and corner rounding come from the theme like every other shell surface: `[notifications]` in `shell.toml` for cards, `[popups]` for the panel, Hyprland's `decoration:rounding` for corners.

## The sender contract

`bin/omarchy-notification-send` is the one way Omarchy code sends
notifications — never raw `notify-send`. It calls
`org.freedesktop.Notifications.Notify` directly over the session bus (via
`busctl --user`), so each value is one typed D-Bus parameter and there is no
argv layer that could reinterpret a relayed headline as an option or a hint. Its
flags map onto that call:

| Flag | Becomes | Meaning |
|---|---|---|
| `-g` / `--glyph` | hint `omarchy-glyph` | Nerd Font glyph for the icon slot when no image icon resolves |
| `--exec <program> [args…]` | hint `omarchy-exec-argv` | the click command; consumes the rest of the line, so it comes last. Each word is a discrete argument the shell runs without re-parsing (see below) |
| `--image` | hint `image-path` | the standard freedesktop image hint |
| `-i` / `--icon` | `app_icon` | themed icon name for the toast |
| `--app-name` | `app_name` | defaults to `omarchy-action` |
| `-u` / `--urgency` | hint `urgency` (byte) | `low`/`normal`/`critical`; defaults to `low` |
| `-t` / `--expire-time` | `expire_timeout` | milliseconds on screen; server default otherwise |

Unknown flags are a hard error, not a silent pass-through: `--exec` is the only
door to a click command, and there is no generic option pass-through to smuggle
one through.

The defaults are the point: an unadorned `omarchy-notification-send "Done"`
is a low-urgency user-action toast that pops through DND and is treated as
ephemeral noise when silenced.

The click command is deliberately not a libnotify action. An action keeps the
sender blocked waiting for `ActionInvoked`, and dies unanswered whenever the
shell restarts underneath it — the installer toasts restart the shell as their
first act. Carrying the command as a hint means the shell executes the click
itself (detached, so the command outlives the shell process) from the copy it
keeps with the popup, which the persistence files preserve: a restored toast
clicks through exactly like a live one, and oneshot senders can exit
immediately. For third-party clients the click falls back to the libnotify
`default` action while the sender is alive, then to focusing the sender's
window by class via `omarchy-hyprland-focus-app` — chat apps rarely register
an action and just expect click-to-jump.

### Click commands are argv, never shell strings

`--exec` consumes the rest of the line as the click command:

```bash
omarchy-notification-send "Download complete" "$title" --exec mpv -- "$file"
```

The caller's shell has already split those words into discrete arguments, and a
quoted argument (`"$file"`) stays one argument even with spaces. On the shell
side they are run through `Util.execArgv`, which invokes `bash -lc 'exec "$@"'`
with the arguments as **positional parameters** — never interpolated into the
script text. bash expands `"$@"` without re-tokenizing or re-evaluating it, so a
value carrying data an attacker controls — a downloaded video's title, a
received filename, a crashed process's name — is only ever a single argument and
can never be reparsed as a command. The login shell keeps the PATH and session
environment that GUI click targets (the screenshot editor, mpv, xdg-open) expect.

The critical rule: **the splitting must happen at the call site, not inside the
tool.** Passing a single quoted string (`--exec "mpv $title"`) and letting the
tool whitespace-split it would hand argument boundaries to whoever controls the
string's content — a title with a space could inject an extra option or program.
So `--exec` refuses a lone quoted-string argument and points at the unquoted
form. There is no "take a command string and sanitize it" path; that is the
escaping trap (string-concatenated SQL) the yt-dlp title RCE exploited.

The shell fails closed on a malformed argv hint (it must be a JSON array of
strings whose program is present and not a leading-dash option) rather than
running anything it can't validate. A caller can still deliberately name a shell
as the program (`--exec sh -c …`), but that runs code because the *developer*
wrote it, not because attacker data became a command — a reviewable red flag
(greppable as `--exec sh`/`--exec bash`), not an injection. Insulating against a
native same-user process is out of scope: it already runs with your privileges
and needs no notification to execute code. What is fully closed is untrusted
*content* — web notifications can't set the exec hint at all, and any relayed
title/filename is confined to inert argument data.

The sender keeps that last part true structurally rather than leaving it to each
caller. Because it calls `Notify` directly, the headline and description are
typed string parameters — a relayed value like `--hint=…` or `-rf` is the
summary or body, never an option or a hint, and there is no argv/option layer
(no `notify-send`) left to reinterpret it. `--exec` is the only thing that can
build the `omarchy-exec-argv` hint. (The leading `--` on the `busctl` call is a
belt for `busctl`'s own getopt, which would otherwise read a dash-leading value
as a `busctl` option; the summary/body themselves are never parsed as options.)

## Helper commands

- `omarchy-notification-wait [timeout]` — polls until the shell answers IPC
  *and* has claimed the bus name. Anything sending near session start or a
  shell restart uses it, or the toast is sent into the void.
- `omarchy-notification-dismiss <summary>` — dismiss by summary substring,
  used by the first-run toasts once their action has been clicked.
- `omarchy-notification-time` / `-battery` — the hotkey notices: one-line
  low-urgency glyph toasts wrapping `date` and `omarchy-battery-status`.
- `omarchy-notification-weather` — despite the name, not a sender: it toggles
  the `omarchy.weather` shell panel.

Keybindings live in `default/hypr/bindings/utilities.lua`: `Super+comma`
variants map to the IPC methods `dismissOne`, `dismissAll`, `invokeLast`,
`showHistory` (put the last few back on screen), and the silencing toggle.

The `notifications` IPC target also answers `dismissStack`, `count`, `expand`,
`snooze <minutes>`, `snoozeAll <minutes>`, `unsnooze <key>`, `snoozes`,
`codes <on|off>`, `act <identifier>`, `offer <code|link|phone>`,
`reply <text>`, `togglePanel`, `openPanel`, `openSettings`, `closePanel`,
`probe`, and `clear` (forget recorded history). `omarchy-dev-notification-demo`
sends realistic scenes through all of it for testing.

## How subsystems plug in

Everything goes through the same sender contract, so the pieces are small:

- **Low battery** — `omarchy-battery-low` sends a critical toast and runs the
  `battery-low` hook.
- **Crash capture** — `omarchy-crash-watch` follows the systemd-coredump
  journal stream and announces each crashed program (deduped per minute) as a
  critical toast whose click runs `omarchy-agent-crash` (via `--exec`, so a
  hostile process name stays a discrete argument). It waits for the
  server first: a shell crash takes the notification server down with it, and
  that crash is the one most worth reporting.
- **Pending migrations** — `omarchy-migrate-notify` (from its user service
  after `graphical-session.target`) waits for the server, then sends a
  critical toast whose click opens a terminal running `omarchy-migrate`,
  falling back to printing in the terminal if the hand-off fails.

## Reminders

Reminders ride on notifications rather than being their own daemon.
`bin/omarchy-reminder <minutes> [message]` creates a transient systemd user
timer via `systemd-run --user --collect --on-active=<minutes>m` under the
unit name `omarchy-reminder-<minutes>m-<epoch>`; the timer's payload sends the
reminder toast, deletes its message file, and refreshes the bar indicator.
Custom messages are stashed in `$XDG_RUNTIME_DIR/omarchy-reminders/<unit>.message`
since a unit name cannot carry arbitrary text. `--collect` means fired timers
leave nothing behind.

The state therefore lives entirely in systemd: `show` and `clear` enumerate
`systemctl --user list-timers "omarchy-reminder-*.timer"` — `show` as a
summary toast, `show --json` as the JSON the bar's Reminder indicator polls
(refreshed by the same `omarchy-shell -q omarchy.indicators refresh` call the
timers and mutations make). `omarchy-reminder -i` summons the
`omarchy.reminders` overlay (`shell/plugins/reminders/ReminderFlow.qml`), a
two-step minutes/message prompt that shells back out to `omarchy-reminder` to
do the setting.
