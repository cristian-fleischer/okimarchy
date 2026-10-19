// Whether a notification reaches the screen, and what it leaves behind when it
// does not. Pure functions over a snapshot row (Store.snapshot), so the rules
// can be exercised from Node without a compositor.
.pragma library

var CRITICAL = 2

// Omarchy's own user-action toasts ("Theme changed") and bare-CLI critical
// alerts get through Do Not Disturb and every snooze. The user just did
// something, or a script is shouting on their behalf. Critical alone is not
// enough: chat apps send critical to force visibility, and they set app_name
// to their brand, which fails the notify-send half of this rule.
function bypassesQuiet(row) {
  var app = String((row && row.app) || "")
  if (app === "omarchy-action") return true
  return app === "notify-send" && Number(row.urgency) === CRITICAL
}

// A notification nobody looks back at: the freedesktop `transient` hint, or a
// sender that did not bother naming itself. Silenced, these are dropped rather
// than recorded as held.
function isEphemeral(row) {
  if (row && row.transient === true) return true
  var app = String((row && row.app) || "")
  return app === "notify-send" || app === "omarchy-action"
}

// Why this row is being kept off the screen: "silenced" under Do Not Disturb,
// "snoozed" when everything or its source is snoozed, "" when it shows. A
// verification code may be let through either, because it was asked for a
// moment ago and expires in minutes.
function quietReason(row, state) {
  var reason = state.doNotDisturb ? "silenced"
             : (state.globalSnoozed || state.sourceSnoozed) ? "snoozed" : ""
  if (!reason) return ""
  if (bypassesQuiet(row)) return ""
  if (state.codesBypassQuiet && String((row && row.code) || "")) return ""
  return reason
}

// A summary that opens with its own glyph ("󰂚  Silenced") already carries its
// mark, so the card leaves the icon slot out rather than showing two. Two
// spaces after the first code point is the convention Omarchy's senders use.
function summaryStartsWithGlyph(summary) {
  var text = String(summary || "").replace(/^\s+/, "")
  if (!text) return false
  var offset = 1
  var first = text.charCodeAt(0)
  if (first >= 0xd800 && first <= 0xdbff && text.length > 1) offset = 2
  var spaces = 0
  while (offset < text.length && text.charAt(offset) === " ") {
    spaces++
    offset++
  }
  return spaces >= 2
}

// How thick the bar is on one screen (a notch floor can make a top bar thicker
// on one screen only), or nothing when it is hidden. A bar without per-screen
// sizes counts its configured size; a missing one, the default.
function barThickness(bar, screenName, defaultBarSize) {
  if (!bar) return Number(defaultBarSize) || 0
  if (bar.barHidden) return 0
  var size = Number(typeof bar.barSizeFor === "function" ? bar.barSizeFor(screenName) : bar.barSize)
  if (!isFinite(size) || size <= 0) size = Number(defaultBarSize) || 0
  return Math.max(0, size)
}

// The deck hangs from the top-right corner, so it clears the bar only on the
// two edges it touches. Everything else keeps the plain edge gap.
function deckMargins(barPosition, thickness, gap) {
  var position = String(barPosition || "top")
  var edge = Number(gap)
  if (!isFinite(edge)) edge = 0
  var bar = Number(thickness)
  if (!isFinite(bar)) bar = 0
  return {
    top: (position === "top" ? bar : 0) + edge,
    right: (position === "right" ? bar : 0) + edge
  }
}
