// Pure functions over notifications: what to keep from one, how to write it
// out, how to read it back.
.pragma library
.import "Security.js" as Security
.import "Markup.js" as Markup
.import "Detect.js" as Detect

var QSIMAGE = /^image:\/\/qsimage\/[0-9]+\/[0-9]+$/

// Everything a card draws and a history entry needs, read defensively from an
// arbitrary sender.
function snapshot(n, key, urgencyEnum) {
  var expire = Number(n.expireTimeout || 0)
  if (!isFinite(expire) || expire < 0) expire = 0
  // `-i some-icon` arrives as image "image://icon/some-icon": a theme name to
  // look up, not a picture (drawn raw it is a checkerboard). Pull the name out
  // before the qsimage check discards it. An absolute path (Chromium's site
  // icon) is kept only as input to the sender-image helper, never drawn raw.
  var img = Security.bounded(n.image, 256)
  var named = ""
  if (img.indexOf("image://icon/") === 0) {
    var iconPayload = img.substring("image://icon/".length)
    if (iconPayload.charAt(0) !== "/") {
      named = iconPayload
      img = ""
    }
  } else if (!QSIMAGE.test(img)) {
    img = ""
  }
  var hints = n.hints || {}
  var raw = { app: Security.bounded(n.appName, Security.MAX_APP_NAME), summary: Security.bounded(n.summary, Security.MAX_SUMMARY),
              body: Security.bounded(n.body, Security.MAX_BODY) }
  // The real source, and the body with the browser's origin anchor lifted off.
  // Detection scans the lifted body so Chrome does not offer to open the site
  // it announced itself with.
  var id = Markup.identify(raw)
  var found = Detect.scan(id.summary, id.body)
  // The hint may arrive as a list, which normalise() would read as no string.
  var argv = Security.parseExecArgv(hints["omarchy-exec-argv"])
  return normalise({
    key: key,
    originalId: n.id || 0,
    // A terminal relaying a notification owns a window; its pid says which.
    senderPid: Number(hints["sender-pid"] || 0) || 0,
    execArgv: argv ? JSON.stringify(argv) : "",
    glyph: hints["omarchy-glyph"],
    transient: hints["transient"] === true || hints["transient"] === 1,
    app: raw.app,
    // Else the desktop-entry hint, which names the app's .desktop file and so,
    // usually, its icon. normalise() drops it when it is a path (Chrome's).
    appIcon: Security.bounded(n.appIcon || named || n.desktopEntry, 256),
    summary: id.summary,
    body: id.body,
    // What the sender sent, so a replay keeps the source anchor.
    rawBody: raw.body,
    source: id.source,
    code: found.code,
    codes: found.codes,
    link: found.link,
    meeting: found.meeting,
    phone: found.phone,
    image: img,
    urgency: typeof n.urgency === "number" ? n.urgency : urgencyEnum.Normal,
    expireTimeout: expire,
    ts: Date.now() / 1000
  })
}

// The fields an in-place update (replaces_id) must write through to the row.
var ROLES = ["originalId", "senderPid", "execArgv", "glyph", "transient", "app", "appIcon", "summary", "body", "rawBody", "bodyRich",
             "bodyLine", "source", "groupKey", "image", "urgency",
             "expireTimeout", "duration", "ts",
             "code", "codes", "link", "meeting", "phone", "replyPath", "replyTo"]

function applyTo(model, index, row) {
  var current = model.get(index)
  for (var i = 0; i < ROLES.length; i++) {
    var role = ROLES[i]
    if (current[role] !== row[role]) model.setProperty(index, role, row[role])
  }
}

// A restored row has no live sender, and its original timeout has long run
// out. It gets a short grace instead; critical still waits for you.
var RESTORE_GRACE = 20000

// Every field a row can have, with its default. A ListModel fixes its roles
// from the first row it sees and silently drops keys that row lacked, so every
// row goes through normalise() and carries every field.
var SHAPE = {
  key: "", originalId: 0, senderPid: 0, execArgv: "", glyph: "", transient: false, app: "", appIcon: "", summary: "", body: "",
  bodyRich: "", bodyLine: "", rawBody: "", source: "", groupKey: "", image: "",
  code: "", codes: "", link: "", meeting: false, phone: "", replyPath: "", replyTo: "",
  urgency: 1, expireTimeout: 0, duration: 0, ts: 0,
  restored: false
}

function normalise(row) {
  var out = {}
  for (var k in SHAPE) {
    var value = row ? row[k] : undefined
    if (typeof SHAPE[k] === "string") out[k] = Security.bounded(value, Security.MAX_BODY)
    else if (typeof SHAPE[k] === "number") out[k] = typeof value === "number" && isFinite(value) ? value : SHAPE[k]
    else out[k] = value === true
  }
  out.app = out.app.slice(0, Security.MAX_APP_NAME)
  out.summary = out.summary.slice(0, Security.MAX_SUMMARY)
  out.source = out.source.slice(0, Security.MAX_SOURCE)
  out.appIcon = /^[a-zA-Z0-9_.-]{1,256}$/.test(out.appIcon) ? out.appIcon : ""
  out.link = Security.safeHttpUrl(out.link)
  out.phone = out.phone.slice(0, Security.MAX_PHONE)
  out.glyph = Security.safeGlyph(out.glyph)
  var argv = Security.parseExecArgv(out.execArgv)
  out.execArgv = argv ? JSON.stringify(argv) : ""
  out.codes = out.codes.split(" ").slice(0, Security.MAX_CODES).join(" ")
  // qsimage is in-process pixels. An icon-scheme absolute path is only pending
  // helper input; keeping it does not authorise Qt to open it.
  var okIconPath = out.image.indexOf("image://icon//") === 0 && out.image.indexOf("..") === -1
  out.image = (QSIMAGE.test(out.image) || okIconPath) ? out.image : ""
  // Derived fields are recomputed, never trusted: a stored row from an older
  // build picks up today's rendering and grouping rules.
  out.bodyRich = Markup.render(out.body)
  out.bodyLine = Markup.oneLine(out.body)
  out.groupKey = Markup.regroup(out)
  return out
}

function restored(entry) {
  if (!entry || !entry.key) return null
  var row = normalise(entry)
  // The store drops link/meeting/phone on write so a stored entry cannot
  // assert capabilities. Recompute them from the text and re-validate. Codes
  // are not recomputed: a redacted entry has nothing left to find.
  var found = Detect.scan(row.summary, row.body)
  row.link = found.link
  row.meeting = found.meeting
  row.phone = found.phone
  row = normalise(row)
  row.duration = row.urgency === 2 ? 0 : RESTORE_GRACE
  row.restored = true
  return row
}

function parseList(text) {
  try {
    if (String(text || "").length > 100 * Security.MAX_HISTORY_ENTRY_BYTES) return []
    var value = JSON.parse(String(text || "[]"))
    if (!Array.isArray(value)) return []
    value = value.slice(0, 100)
    for (var i = 0; i < value.length; i++) {
      // Image handles lived in the previous shell; read back they are broken
      // boxes that also stop a real icon from being looked up.
      value[i] = normalise(value[i])
      value[i].image = ""
    }
    return value
  } catch (e) {
    return []
  }
}

// One writer, one queue: two Processes racing on a key could let a close
// overtake its put.
var _queue = []
var _busy = false

// A pending put for the same row, or a pending settings save, is replaced by
// the newer one, so a burst of replacements cannot crowd out a close. Only
// puts are ever dropped.
function write(proc, bin, verb, payload, args) {
  var job = { bin: bin, verb: verb, payload: verb === "put" ? persistable(payload) : payload, args: args || [] }
  var merges = verb === "put" || verb === "quiet-save" || verb === "policy"
  for (var i = _queue.length - 1; merges && i >= 0; i--) {
    var queued = _queue[i]
    if (verb === "put" && queued.verb === "close" && queued.args[0] === job.payload.key) break
    if (queued.verb === verb && (verb !== "put" || queued.payload.key === job.payload.key)) {
      _queue[i] = job
      return _pump(proc)
    }
  }
  if (verb !== "put" || _queue.length < 256) _queue.push(job)
  _pump(proc)
}

function _pump(proc) {
  if (proc.policyReady === false || _busy || _queue.length === 0) return
  var job = _queue.shift()
  _busy = true
  proc.command = [].concat(job.bin, [job.verb], job.args)
  proc.exited.connect(function done() {
    proc.exited.disconnect(done)
    _busy = false
    _pump(proc)
  })
  // stdin must be open before start and closed after the payload, or the
  // store waits forever for EOF.
  proc.stdinEnabled = !!job.payload
  proc.running = true
  if (job.payload) {
    proc.write(JSON.stringify(job.payload))
    proc.stdinEnabled = false
  }
}

// The store takes at most 64 KiB of JSON and writes it back ASCII-escaped, so
// a row is measured that way and its body shortened until it fits. Derived
// text is recomputed on restore and not sent at all.
var PERSIST_BYTES = 60000

function escapedLength(value) {
  var text = JSON.stringify(value), n = 0
  for (var i = 0; i < text.length; i++) n += text.charCodeAt(i) < 0x80 ? 1 : 6
  return n
}

function persistable(row) {
  var out = sanitiseForPersistence(row)
  delete out.bodyRich
  delete out.bodyLine
  if (out.rawBody === out.body) out.rawBody = ""
  while (escapedLength(out) > PERSIST_BYTES && (out.body || out.rawBody)) {
    out.body = out.body.slice(0, Math.floor(out.body.length * 3 / 4))
    out.rawBody = out.rawBody.slice(0, Math.floor(out.rawBody.length * 3 / 4))
  }
  if (escapedLength(out) > PERSIST_BYTES) out.execArgv = ""
  return out
}

// What a redacted row says, stored in English like any stored value (the
// store writes the same) and translated where it is shown.
var REDACTED_SUMMARY = "Verification notification"
var REDACTED_BODY = "[redacted]"

function redacted(row) {
  return !!row && row.summary === REDACTED_SUMMARY && (row.body === REDACTED_BODY || row.bodyLine === REDACTED_BODY)
}

// A secret-bearing notification persists only as a placeholder, so encoded
// variants, URLs and sender metadata cannot leak it.
function sanitiseForPersistence(row) {
  var out = normalise(row)
  // Strip literal markup before detection so long attributes cannot push a
  // code outside the keyword window in a legacy/raw-only entry.
  var secret = out.codes || out.code || Detect.codes(
      Markup.decodeEntities(out.summary + " " + out.rawBody + " " + out.body)
        .replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()).length
  if (secret) {
    for (var k in SHAPE) if (typeof SHAPE[k] === "string" && k !== "key") out[k] = ""
    out.summary = REDACTED_SUMMARY
    out.body = REDACTED_BODY
    out.rawBody = out.body
    out.bodyLine = out.body
    out.bodyRich = out.body
  }
  out.replyPath = ""; out.replyTo = ""; out.image = ""
  return out
}
