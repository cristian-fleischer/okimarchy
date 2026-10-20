// Notification preferences from the `notifications` object in shell.json.
// Every key is optional; a missing or invalid value falls back to its default.
.pragma library

var DEFAULTS = {
  stacking: "source",
  displayMode: "active",
  displayName: "",
  fullscreenOverlay: "all",
  edgeSpacing: null,
  showCountdown: false,
  offerSnoozeWhenSharing: true,
  fontScale: 100,
  actionsAlign: "right",
  hideSettingsAction: true,
  snoozeDurations: ["30", "60", "240", "tomorrow"],
  wakeHour: 8,
  smartRaise: true,
  codesBypassQuiet: null,
  timeFormat: "system",
  sourceLimit: 8,
  heldPerSource: 10,
  recentCount: 5,
  allowDefaultActionOnCardClick: true,
  historyHours: 24,
  clipboardTimeout: 60
}

var SNOOZE_CHOICES = ["15", "30", "60", "120", "240", "480", "tomorrow"]
var FULLSCREEN_MODES = ["off", "all", "steam", "all-away", "steam-away"]

function oneOf(value, options, fallback) {
  return options.indexOf(value) >= 0 ? value : fallback
}

function integer(value, min, max, fallback) {
  var n = Number(value)
  if (value === null || value === undefined || value === "" || !isFinite(n)) return fallback
  return Math.max(min, Math.min(max, Math.round(n)))
}

function flag(value, fallback) {
  return typeof value === "boolean" ? value : fallback
}

function resolve(raw) {
  var given = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? raw : {}
  var d = DEFAULTS
  var snooze = []
  if (Array.isArray(given.snoozeDurations)) {
    for (var i = 0; i < given.snoozeDurations.length; i++) {
      var choice = String(given.snoozeDurations[i])
      if (SNOOZE_CHOICES.indexOf(choice) >= 0 && snooze.indexOf(choice) < 0) snooze.push(choice)
    }
  }
  // Empty means "none chosen": an empty snooze menu is a dead end.
  if (!snooze.length) snooze = d.snoozeDurations.slice()

  return {
    stacking: oneOf(given.stacking, ["source", "all"], d.stacking),
    displayMode: oneOf(given.displayMode, ["active", "specific", "all"], d.displayMode),
    displayName: typeof given.displayName === "string" ? given.displayName.slice(0, 128) : d.displayName,
    fullscreenOverlay: oneOf(given.fullscreenOverlay, FULLSCREEN_MODES, d.fullscreenOverlay),
    // Unset follows the theme's outer gap, like every other shell surface.
    edgeSpacing: integer(given.edgeSpacing, 0, 64, d.edgeSpacing),
    showCountdown: flag(given.showCountdown, d.showCountdown),
    offerSnoozeWhenSharing: flag(given.offerSnoozeWhenSharing, d.offerSnoozeWhenSharing),
    fontScale: integer(given.fontScale, 75, 200, d.fontScale),
    actionsAlign: oneOf(given.actionsAlign, ["right", "left"], d.actionsAlign),
    hideSettingsAction: flag(given.hideSettingsAction, d.hideSettingsAction),
    snoozeDurations: snooze,
    wakeHour: integer(given.wakeHour, 0, 23, d.wakeHour),
    smartRaise: flag(given.smartRaise, d.smartRaise),
    codesBypassQuiet: flag(given.codesBypassQuiet, d.codesBypassQuiet),
    timeFormat: oneOf(given.timeFormat, ["system", "24h", "12h"], d.timeFormat),
    sourceLimit: integer(given.sourceLimit, 2, 20, d.sourceLimit),
    heldPerSource: integer(given.heldPerSource, 3, 25, d.heldPerSource),
    recentCount: integer(given.recentCount, 1, 20, d.recentCount),
    allowDefaultActionOnCardClick: flag(given.allowDefaultActionOnCardClick, d.allowDefaultActionOnCardClick),
    historyHours: oneOf(Number(given.historyHours), [0, 1, 24, 168], d.historyHours),
    clipboardTimeout: oneOf(Number(given.clipboardTimeout), [30, 60, 90], d.clipboardTimeout)
  }
}

// Seconds a snooze choice lasts. "tomorrow" means the next wake hour, at
// least ten minutes away.
function snoozeSeconds(choice, wakeHour, now) {
  var value = String(choice || "")
  if (value === "tomorrow") {
    var wake = new Date(now)
    wake.setDate(wake.getDate() + 1)
    wake.setHours(Math.max(0, Math.min(23, Number(wakeHour) || 0)), 0, 0, 0)
    return Math.max(600, Math.round((wake.getTime() - now) / 1000))
  }
  var minutes = Number(value)
  return minutes > 0 ? Math.round(minutes * 60) : 0
}
