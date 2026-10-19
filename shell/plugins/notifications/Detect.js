// What a notification is actually offering you.
//
// A body is not just text: a quarter of the ones this desktop receives carry a
// link, and the ones that carry a verification code are the ones you most need
// to act on within thirty seconds. Both are routinely invisible, because a
// card shows two lines and the useful part is past the ellipsis.
//
// Everything here is a guess about someone else's prose, so the bar is: a
// detection that fires wrongly is worse than one that does not fire. Offering
// to copy "412" out of "412 passed, 0 failed" makes the whole feature feel
// like a toy.
.pragma library
.import "Security.js" as Security

// A code is only a code if the sender says so. Shape alone is hopeless - four
// to eight digits is also an order number, a port, a build number, a year, an
// issue reference and a count of passing tests. Across 200 real notifications
// on this machine, ten had a digit run of the right shape and none of them
// were codes; every one would have been a false positive.
var CODE_WORDS = /\b(code|otp|one[\s-]?time|verification|verify|passcode|pin|2fa|two[\s-]factor|security key|confirm(?:ation)?)\b/i

// "482913", "482 913", "84 2139", "482-913", "G-482913".
var CODE_SHAPE = /(?:^|[^\w-])((?:[A-Za-z]-)?\d{2,4}[\s-]\d{2,5}|(?:[A-Za-z]-)?\d{4,8})(?![\w-])/g

// Uppercase alphanumeric with at least one digit and one letter: "A9F3K2".
var CODE_ALNUM = /(?:^|[^\w-])([A-Z0-9]{5,8})(?![\w-])/g

function looksLikeYear(value) {
  return value.length === 4 && /^(19|20)\d\d$/.test(value)
}

// The keyword and the code have to be near each other. "Claude Code" trips the
// keyword on this desktop dozens of times a day; without proximity, the next
// four-digit number anywhere in the body - a build number, a token count -
// would be offered as something to paste into a login box.
var NEAR_BEFORE = 24
var NEAR_AFTER = 72

// "Code" is also half a product name - Claude Code, VS Code, Xcode - and those
// arrive dozens of times a day here. When the word is preceded by a
// capitalised word it is a name, not an instruction, and the build number
// after it is not something to paste into a login box. Only "code" gets this
// treatment: "Uber PIN" is a real PIN, and no product is called Something OTP.
function isProductName(t, at, word) {
  if (String(word).toLowerCase() !== "code") return false
  // A product capitalises it - "Claude Code", "VS Code". An instruction does
  // not - "use code SAVE20". That one letter is the whole difference.
  if (word[0] !== word[0].toUpperCase()) return false
  var before = t.slice(Math.max(0, at - 20), at).match(/([A-Za-z][\w.]*)\s+$/)
  if (!before || !/^([A-Z][a-z]+|[A-Z]{2,})$/.test(before[1])) return false
  // ...unless the word in front is itself one of ours: "Your Verification
  // Code is 482913" is title case, not a product.
  return !CODE_WORDS.test(before[1])
}

function windows(t) {
  var out = [], m
  var re = new RegExp(CODE_WORDS.source, "gi")
  while ((m = re.exec(t)) !== null) {
    if (!isProductName(t, m.index, m[0]))
      out.push([Math.max(0, m.index - NEAR_BEFORE), m.index + m[0].length + NEAR_AFTER])
    if (re.lastIndex === m.index) re.lastIndex++
  }
  return out.slice(0, Security.MAX_CODES)
}

function harvest(t, re, seen, out, keep) {
  var m
  re.lastIndex = 0
  while ((m = re.exec(t)) !== null) {
    var value = keep(m[1])
    if (!value || seen[value]) continue
    seen[value] = true
    out.push(value)
  }
}

function codes(text) {
  var t = Security.bounded(text, Security.MAX_BODY)
  var spans = windows(t)
  if (!spans.length) return []

  var out = [], seen = {}
  for (var i = 0; i < spans.length; i++) {
    var chunk = t.slice(spans[i][0], spans[i][1])
    harvest(chunk, CODE_SHAPE, seen, out, function (raw) {
      var value = raw.replace(/^[A-Za-z]-/, "").replace(/[\s-]/g, "")
      if (value.length < 4 || value.length > 8) return ""
      if (looksLikeYear(value)) return ""
      return value
    })
  }
  if (out.length) return out.slice(0, Security.MAX_CODES)

  for (var j = 0; j < spans.length; j++) {
    harvest(t.slice(spans[j][0], spans[j][1]), CODE_ALNUM, seen, out, function (raw) {
      // Needs both a digit and a letter, or it is a word in caps.
      return (/\d/.test(raw) && /[A-Z]/.test(raw)) ? raw : ""
    })
  }
  return out.slice(0, Security.MAX_CODES)
}

// Trailing punctuation is almost always the sentence's, not the URL's.
function tidyUrl(url) {
  return String(url).replace(/[.,;:!?)\]}'"]+$/, "")
}

function links(text) {
  var out = [], seen = {}, m
  var re = /(https?:\/\/[^\s<>"']+)/g
  while ((m = re.exec(Security.bounded(text, Security.MAX_BODY))) !== null) {
    var url = Security.safeHttpUrl(tidyUrl(m[1]))
    if (!url) continue
    if (seen[url]) continue
    seen[url] = true
    out.push(url)
  }
  return out.slice(0, Security.MAX_CODES)
}

// A meeting is a link you are late for, so it gets its own name.
var MEETING = /(zoom\.us|meet\.google\.com|teams\.microsoft\.com|teams\.live\.com|whereby\.com|meet\.jit\.si)/i

function isMeeting(url) {
  return MEETING.test(String(url || ""))
}

// Phone numbers are the easiest thing to detect badly: a version string, an
// order id and a bank balance are all digits with punctuation in them. So only
// three shapes count, each one committing to something a bare number does not:
// a leading +, brackets around an area code, or a leading 0 with separators.
var PHONE_SHAPES = [
  /(\+\d[\d\s().-]{7,16}\d)/g,             // +44 7911 123456
  /(\(\d{2,4}\)\s?\d{3,4}[\s-]?\d{3,4})/g, // (020) 7946 0958
  /(\b0\d{1,4}[\s-]\d{3,4}[\s-]?\d{3,4}\b)/g // 07911 123 456
]

function phones(text) {
  var t = Security.bounded(text, Security.MAX_BODY)
  var out = [], seen = {}
  for (var i = 0; i < PHONE_SHAPES.length; i++) {
    var re = PHONE_SHAPES[i], m
    re.lastIndex = 0
    while ((m = re.exec(t)) !== null) {
      var raw = String(m[1]).trim()
      var digits = raw.replace(/\D/g, "")
      if (digits.length < 9 || digits.length > 15) continue
      if (seen[digits]) continue
      seen[digits] = true
      out.push(raw)
    }
  }
  return out.slice(0, Security.MAX_CODES)
}

// Everything a card might offer, from the text it is going to draw. The body
// passed in must be the one with the sender's own origin anchor already lifted
// off: otherwise every Chrome notification offers to open the site it came
// from, which is not an offer at all.
function scan(summary, body) {
  var text = String(summary || "") + "\n" + String(body || "")
  var code = codes(text)
  var link = links(text)
  var phone = phones(text)
  return {
    code: code.length ? code[0] : "",
    // All of them, space separated. A message carrying two - "your code is
    // 482913, your backup code is 771204" - used to offer the first and drop
    // the second on the floor, which is the wrong one about half the time.
    codes: code.join(" "),
    link: link.length ? link[0] : "",
    meeting: link.length ? isMeeting(link[0]) : false,
    phone: phone.length ? phone[0] : ""
  }
}
