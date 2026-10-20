// The names a card's icon may go by, best first. Toast.qml looks them up in
// your overrides, the icon theme and the desktop entries, in the shell like
// the dock does; nothing here touches a file.
.pragma library
.import "Security.js" as Security

// Override files are named this way: ~/.config/omarchy/notifications/icons/<slug>.png
function slug(text) {
  return String(text || "").slice(0, 256).toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "").slice(0, 100)
}

function unique(names) {
  var out = []
  for (var i = 0; i < names.length; i++)
    if (names[i] && out.indexOf(names[i]) < 0) out.push(names[i])
  return out
}

// app.slack.com -> app.slack.com, slack. The middle label is almost always the
// name of the thing; the site is never fetched, only named.
var SITE_PREFIXES = ["www", "app", "web", "my", "m"]
function siteNames(source) {
  var host = Security.canonicalHostname(String(source || ""))
  if (!host) return []
  var labels = host.split(".").filter(function(label) { return SITE_PREFIXES.indexOf(label) < 0 })
  var names = [host]
  if (labels.length >= 2) names.push(labels[labels.length - 2])
  if (labels.length) names.push(labels[0])
  return unique(names)
}

// What to look for, in order. A site comes first and its browser last, and a
// site's names only as exact icon-theme names: a fuzzy desktop-entry match on
// a domain label is how mail.google.com ends up wearing Google Contacts. The
// hint of a browser notification always names the browser, so it waits too.
function candidates(row) {
  row = row || {}
  var site = String(row.groupKey || "").indexOf("web:") === 0 ? siteNames(row.source) : []
  var appIcon = String(row.appIcon || ""), source = String(row.source || ""), app = String(row.app || "")
  var own = [appIcon, source, app]
  var themed = site.length ? site : [appIcon]
  for (var i = 0; i < own.length; i++) themed = themed.concat([own[i], slug(own[i])])
  return {
    overrides: unique(site.concat(own, [String(row.groupKey || source || app)]).map(slug)),
    themed: unique(themed.map(function(name) { return /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,255}$/.test(name) ? name : "" })),
    entries: unique(site.length ? [appIcon, app] : own)
  }
}

// The override folder's files as slug -> file name, PNG preferred when a name
// comes in more than one format.
var OVERRIDE_EXTENSIONS = ["png", "svg", "jpg", "jpeg", "webp", "ico"]
function overrideMap(fileNames) {
  var out = {}, rank = {}
  for (var i = 0; i < (fileNames || []).length; i++) {
    var m = String(fileNames[i]).match(/^(.+)\.([A-Za-z]+)$/)
    if (!m) continue
    var at = OVERRIDE_EXTENSIONS.indexOf(m[2].toLowerCase()), name = slug(m[1])
    if (at < 0 || !name) continue
    if (rank[name] === undefined || at < rank[name]) {
      rank[name] = at
      out[name] = fileNames[i]
    }
  }
  return out
}

// A one-colour icon to tint with the theme's text colour, known by the
// freedesktop -symbolic name, as an image://icon/ name or a file path.
function isSymbolic(source) {
  var text = String(source || "").split("?")[0]
  return /-symbolic$/.test(text) || text.indexOf("/symbolic/") >= 0 || /-symbolic\.[A-Za-z]+$/.test(text)
}
