# Notifications

The shell is the notification daemon: `shell/plugins/notifications/Service.qml` hosts a Quickshell `NotificationServer` that claims `org.freedesktop.Notifications` on the session bus, so anything that speaks the freedesktop protocol (notify-send, libnotify apps, Chromium web apps, KDE Connect) is drawn as a card in a deck at the top-right corner. The end-user view is in `manual/10-notices.md`.

## Files

| File | Role |
|---|---|
| `Service.qml` | The daemon: admission, quiet rules, snoozes, the scene clock, click routing, replies, offers, IPC, one layer surface per output |
| `Toast.qml`, `DeedButton.qml` | One card and its buttons; a card is positioned by the service and animates nothing itself |
| `NotificationPanel.qml`, `Picker.qml` | The panel and its preferences page, opened from the bar's Dnd indicator (`shell/plugins/bar/indicators/Dnd.qml`) |
| `Store.js` | Notification snapshots, normalisation, persistence redaction, restore |
| `Markup.js` | Safe body markup, source lifting (`web:app.slack.com`), KDE Connect forwarding, one-line previews |
| `Detect.js` | Verification codes, links, meeting links and phone numbers |
| `Security.js` | URL policy, bounds, the `omarchy-exec-argv` and glyph checks |
| `Layout.js` | Pure deck layout: rows in, placements out |
| `Delivery.js` | Quiet rules, ephemeral rules, bar clearance |
| `Settings.js` | Defaults and validation for `notifications` in `shell.json` |
| `helpers/` | Python helpers: `run` (Bubblewrap launcher), `store`, `icon`, `kdeconnect` |

The JS modules also load in Node: `test/shell.d/notifications-test.sh` covers them without a compositor, and `test/shell.d/notification-helpers-test.sh` covers the helpers.

## Decks and the scene clock

Each notification gets its own key (`n…`); the sender's id names a slot that `replaces_id` reuses, not an event. Cards group by source: per site for browser notifications (the leading `<a href>` Chromium adds is lifted off and becomes the source, but only from a browser and only for an http(s) href that passes the URL policy), per forwarded app for KDE Connect (recognised by exact app name), per app name otherwise. `stacking: "all"` puts everything in one deck.

A collapsed deck draws its cards at the front card's height; hovering opens it. While the pointer is on an open deck or a reply is being typed, new cards are held back for at most 30 seconds. All positions, scales, opacities and heights come from one clock (`Service.at()`): a change snapshots the current state, recomputes the layout, and starts one move for every card. A leaving card keeps its model row until that move finishes.

Live `Notification` objects are kept in a plain JS map (`refs`), never a ListModel role, which would dangle once the server destroys the object. At most 100 are live.

The surface is one fixed-width `WlrLayer.Overlay` window per output (namespace `omarchy-notifications`), input-masked to the deck. It stays mapped while idle, because a layer surface coming and going makes Hyprland re-evaluate focus and drags a scrolling layout's viewport. The exception is `fullscreenOverlay` (default `all`), which unmaps it over a fullscreen window when nothing is showing so the window can be scanned out directly; the `-away` variants never cover a fullscreen window and send cards to another output or to Recent.

## Toast lifecycle

A card stays at least 5s (low), 8s (normal), or until dismissed (critical), stretched up to 30s by a longer `expire_timeout`. The countdown pauses while the deck is open or a reply is being typed; a content update restarts it. Left-click activates, middle-click dismisses, right-click opens the source menu (snooze, Do Not Disturb).

A click tries, in order: the card's `omarchy-exec-argv` command; the sender's `default` action (`allowDefaultActionOnCardClick`); the sender's window by pid; a window showing the source (exact class, then for a site a browser window whose title names it); the site itself; the first link in the text; `omarchy-hyprland-focus-app` by app name.

## Persistence

`helpers/store` keeps one file per notification under `~/.local/state/omarchy/notifications/`: `live/KEY.json` while on screen, moved to `history/<ms>-KEY.json` on close. History is capped at 100 entries and `historyHours` (default 24; `0` keeps none). Text with a verification code is redacted before writing. Rows keep `execArgv` and `glyph`, so a card restored after a shell restart clicks through like the live one; restored cards get a 20s grace. `quiet.json` holds Do Not Disturb, snoozes and the code exception; `icons/` is the icon helper's private cache, never read by the shell.

## Helper sandbox

Helpers run under Bubblewrap when it works. Without a working sandbox, `store` and `kdeconnect` run directly as the user unless `requireSandbox` is set, in which case they are blocked; `icon` never runs unsandboxed, so cards fall back to a letter tile. `omarchy-shell notifications probe` reports the mode, and the preferences page says when icons are off.

Icons resolve once per source: the sender's image, then a local or themed icon, then, with `fetchRemoteIcons`, the site's icon over HTTPS from a public address. User overrides go in `~/.config/omarchy/notifications/icons/`.

- Lookup, download and decode are separate sandboxes. Lookup has no network and only names the site. Download is the only one with a network: it fetches up to two candidates, keeps bodies whose signature is a supported format, decodes nothing, writes nowhere, and cannot create Unix sockets (seccomp). Decode has no network.
- Decoders are chosen by content signature, never name, extension or Content-Type. ImageMagick (`helpers/notification_images.py`) runs under `helpers/policy.xml`, which allows only PNG, JPEG, WebP and ICO (at most 64 frames) with memory, size and time limits. Local SVGs go through librsvg from stdin, so external references resolve to nothing; no SVG reaches Qt.
- A sender's image file is read by a forked child of the launcher under a 5s deadline and refused if empty, oversized, not a regular file, or on `/proc`, `/sys` or `/dev` (by path and filesystem type). The helper decodes a sealed memfd copy.
- Helpers return raw pixels, never files. The launcher (`helpers/run`, outside the sandbox) reads at most one 128px RGBA image, encodes the PNG itself, and publishes `~/.cache/omarchy/notification-icons/<sha256>[-mono].png` (mounted by no sandbox) or, for a sender's image, a `data:image/png` URL. The shell accepts only a digest-named path in that directory or a data URL with a PNG header, from a launcher that exited cleanly.
- Favicon pages are parsed with the stdlib HTML parser (linear time); one icon job gets 20s.

## Silencing and snoozing

Do Not Disturb is a boolean in `quiet.json`, toggled via `omarchy-shell notifications toggleDnd` / `setDnd` / `dndState`; `omarchy-toggle-notification-silencing` wraps the toggle. A snooze is the same quiet with an end time, per source (`groupKey`) or for everything (key `*`, which replaces Do Not Disturb).

Three kinds of notification get through every kind of quiet:

- `app_name` = `omarchy-action`: Omarchy's own confirmation toasts for something the user just did.
- urgency critical *and* `app_name` = `notify-send`: bare-CLI emergency alerts. Critical alone is not enough, because chat apps use it to force visibility under their own app name.
- a detected verification code, while `codesBypassQuiet` is on.

Quieted notifications are recorded as held and listed by source in the panel. Ephemeral ones (the `transient` hint, or `app_name` `notify-send`/`omarchy-action`) are dropped.

When the Hyprland portal starts a screen-share stream, the bell offers a timed snooze; nothing is muted automatically.

## Preferences

Preferences live in the `notifications` object of `~/.config/omarchy/shell.json`; every key is optional, and `Settings.js` holds defaults and valid values. The preferences page writes `displayMode`/`displayName`, `fullscreenOverlay`, `stacking`, `showCountdown` and `offerSnoozeWhenSharing`. Hand-edited keys: `edgeSpacing` (unset follows the theme's outer gap), `fontScale`, `actionsAlign`, `hideSettingsAction`, `snoozeDurations`, `wakeHour`, `smartRaise`, `codesBypassQuiet`, `timeFormat`, `sourceLimit`, `heldPerSource`, `recentCount`, `fetchRemoteIcons`, `requireSandbox`, `allowDefaultActionOnCardClick`, `historyHours`, `clipboardTimeout`. Colours come from the theme: `[notifications]` in `shell.toml` for cards, `[popups]` for the panel, Hyprland's `decoration:rounding` for corners.

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

The `notifications` IPC target also answers `dismissStack`, `count`, `expand`, `snooze <minutes>`, `snoozeAll <minutes>`, `unsnooze <key>`, `snoozes`, `codes <on|off>`, `act <identifier>`, `offer <code|link|phone>`, `reply <text>`, `togglePanel`, `openPanel`, `openSettings`, `closePanel`, `probe`, and `clear` (forget history). `omarchy-dev-notification-demo` sends test scenes through it.

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
