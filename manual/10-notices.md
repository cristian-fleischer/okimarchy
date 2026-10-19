# Notices

Notifications land in the top-right corner of the focused display. You can also quickly access the date and time, battery status, and current weather using the hotkey notices.

## Notifications

Notifications from the same app or site stack together into a deck, so a chatty Slack channel doesn't push your build failure off the screen. Hover a deck to fan it out and read each card in full; nothing new slides in under your pointer while you're reading. Click a card to jump to the window it came from (a web app, a browser tab showing that site, or the terminal that raised it), middle-click to dismiss it, or hover and hit the ✕.

Cards offer what they carry. A verification code gets a _Copy code_ button, and the copied code is kept out of [clipboard history](08-unified-clipboard-history.md) and cleared again after a minute if it's still on the clipboard. Links get _Open link_, meeting invites get _Join_, phone numbers get _Copy number_, and any buttons the app itself provides (_Mark as read_, _Reply_) show up when you hover. Messages forwarded from your phone by KDE Connect can be answered right in the card.

Right-click a card to snooze its source for 30 minutes, an hour, four hours, or until tomorrow morning, or to turn on Do Not Disturb. Snoozed notifications aren't thrown away: they're held back, and you can read them later.

Right-click the bell in the bar (hover the middle of the bar to reveal it) to open the notification panel. It shows what's been held back while you were snoozed or silenced, the last few notifications you saw, and up to 100 closed ones from the past day under _History_. From there you can snooze everything for a while, wake a snoozed source early, or choose whether verification codes still get through while you're quiet (they do by default). The cog opens the preferences: which display notifications use, whether they step aside for fullscreen games so those run at full speed, whether to stack by source, and a countdown bar. When you start sharing your screen, the bell offers a timed snooze so a call doesn't show everyone your messages. Nothing is muted until you pick one.

The rest of the preferences live in the `notifications` section of `~/.config/omarchy/shell.json`, for example `"notifications": { "fontScale": 120, "historyHours": 168 }`. Set `historyHours` to `0` to keep no history on disk at all. Website icons are fetched from the site itself when no local icon matches; set `fetchRemoteIcons` to `false` to stop that.

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
