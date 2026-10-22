# Notices

Notifications land in the top-right corner of the focused display. You can also quickly access the date and time, battery status, and current weather using the hotkey notices.

## Notifications

Notifications from the same app or site stack into a deck, so a chatty Slack channel doesn't push your build failure off the screen. Hover a deck to fan it out; nothing new slides in under your pointer while you're reading. Click a card to jump to where it came from, middle-click or hit the ✕ to dismiss it.

Cards offer what they carry: _Copy code_ for verification codes (kept out of [clipboard history](08-unified-clipboard-history.md) and cleared after a minute), plus any buttons the app provides. Links in a notification's text open when clicked.

Right-click a card to snooze its source or turn on Do Not Disturb. Snoozed notifications are held back, not thrown away.

Right-click the bell in the bar (hover the middle of the bar to reveal it) to open the notification panel: what's been held back, recent notifications, and the past day's history. From there you can snooze everything, wake a snoozed source, or choose whether verification codes get through while you're quiet (they do by default). The cog opens preferences for which display to use, stepping aside for fullscreen games, stacking by source, and a countdown bar. When you share your screen, the bell offers a timed snooze; nothing is muted until you pick one.

More preferences live in the `notifications` section of `~/.config/omarchy/shell.json`, for example `"notifications": { "fontScale": 120, "historyHours": 168 }`. Set `historyHours` to `0` to keep no history on disk.

## Hotkey notices

### Date & Time

`Super + Ctrl + Alt + T`

 ![notice-datetime](images/notice-datetime.webp)

### Weather

`Super + Ctrl + Alt + W`

 ![notice-weather](images/notice-weather.webp)

The location is detected from your IP address, which is usually close enough, but not always. You can pin it down with `omarchy weather location --set Malibu`, or be exact about it by adding coordinates: `omarchy weather location --set Malibu 34.0259,-118.7798`. Run `omarchy weather location` on its own to see where it thinks you are, and `--clear` to go back to auto-detection.

### Battery

`Super + Ctrl + Alt + B`

 ![notice-battery](images/notice-battery.webp)
