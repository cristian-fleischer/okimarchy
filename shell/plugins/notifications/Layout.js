// Where every card sits, in one function.
//
// The deck is not a column: cards are placed absolutely, so a card keeps its
// identity (and its half-finished animation) when the one above it leaves.
// Everything here is pure - rows in, placements out - so the positioning can
// be reasoned about without a compositor.
.pragma library

// Collapsed geometry. Three steps of peek is the floor before a deck stops
// reading as a deck; past that the cards only fade.
var PEEK = 10          // px each card behind the front one drops
var SHRINK = 0.035     // and the scale it loses
var VISIBLE = 3        // cards drawn before the rest just fade out
var FADE = 0.55        // opacity of the last drawn card in a collapsed deck

// Which deck a row belongs to. In "all" mode there is one deck and this is
// constant; in "source" mode it is the sender.
function deckKeyFor(row, stacking) {
  if (stacking !== "source") return "all"
  return String(row.groupKey || row.source || row.app || "?")
}

function groupKeyFor(row) {
  return String(row.groupKey || row.source || row.app || "?")
}

// A deck shows every notification - that is what makes it a stack. Grouping
// is carried as a count on the newest card from each source rather than by
// hiding the rest: folding three notifications into one card left nothing to
// stack and nothing to expand, which reads as broken.
function groupRows(rows) {
  var counts = {}, seen = {}, items = [], i, key
  for (i = 0; i < rows.length; i++) {
    key = groupKeyFor(rows[i])
    counts[key] = (counts[key] || 0) + 1
  }
  for (i = 0; i < rows.length; i++) {
    key = groupKeyFor(rows[i])
    // Only the newest of a group wears the count; the ones behind it would
    // just be repeating themselves.
    items.push({ key: rows[i].key, row: rows[i], count: seen[key] ? 1 : counts[key] })
    seen[key] = true
  }
  return items
}

// Rows are newest-first. Returns:
//   decks:      [{ key, rows: [row...] }] in display order, newest deck first
//   placements: { rowKey: { y, height, scale, opacity, z, front, hidden, count } }
//   height:     total height the deck area occupies
function compute(rows, opts) {
  var stacking = opts.stacking || "all"
  var expanded = !!opts.expanded
  var gap = opts.gap || 6
  var deckGap = opts.deckGap || 12
  var heightOf = opts.heightOf || function() { return 76 }
  // A card is its own height when the deck is open, and the *front card's*
  // height while it is shut.
  //
  // Shut, all you see of the ones behind is a strip of edge peeking out from
  // under the one in front. Drawn at their own heights, a card taller than the
  // front one hangs out below the stack - which reads as a notification stuck
  // half way out, and is what "the bottom one sticks out more than it needs
  // to" was. Uniform *within a deck*, and only while it is shut: this is not
  // the old shared height, which took the tallest card anywhere on screen and
  // padded every one-line card out to match it.

  // Which deck each row belongs to. One in "all" mode; one per source in
  // "source" mode, where the deck already separates them and grouping inside
  // it would be grouping twice.
  var order = [], byKey = {}
  for (var i = 0; i < rows.length; i++) {
    var key = deckKeyFor(rows[i], stacking)
    if (!byKey[key]) { byKey[key] = { key: key, rows: [] }; order.push(key) }
    byKey[key].rows.push(rows[i])
  }

  var decks = []
  for (var d = 0; d < order.length; d++) {
    var deck = byKey[order[d]]
    // In "source" mode the deck already separates senders, so grouping inside
    // it would be grouping twice.
    deck.items = stacking === "source"
      ? deck.rows.map(function(r) { return { key: r.key, row: r, count: 1 } })
      : groupRows(deck.rows)
    decks.push(deck)
  }

  var placements = {}
  var y = 0

  for (var k = 0; k < decks.length; k++) {
    var items = decks[k].items
    var open = expanded && (stacking !== "source" || opts.openDeck === decks[k].key
                            || opts.openDeck === undefined)
    var deckTop = y
    var frontHeight = items.length ? heightOf(items[0].key) : 76
    var shown = 0

    for (var r = 0; r < items.length; r++) {
      var item = items[r]
      if (open) {
        placements[item.key] = {
          y: y, scale: 1, opacity: 1, z: 1000 - shown, front: r === 0,
          hidden: false, height: heightOf(item.key), count: item.count
        }
        y += heightOf(item.key) + gap
        shown += 1
      } else {
        var drawn = r < VISIBLE
        placements[item.key] = {
          height: frontHeight,
          y: deckTop + r * PEEK,
          scale: Math.max(0.7, 1 - r * SHRINK),
          opacity: r === 0 ? 1 : (drawn ? (r === VISIBLE - 1 ? FADE : 0.85) : 0),
          z: 1000 - r,
          front: r === 0,
          hidden: !drawn,
          count: item.count
        }
      }
    }

    if (!open) y = deckTop + frontHeight + Math.min(items.length - 1, VISIBLE - 1) * PEEK
    else y -= gap

    if (k < decks.length - 1) y += (stacking === "source" ? deckGap : gap)
  }

  // Anything the model still holds but no deck placed - a row on its way out -
  // gets a definite hidden placement rather than the fallback the delegate
  // would otherwise invent for itself.
  for (var q = 0; q < rows.length; q++) {
    if (!placements[rows[q].key])
      placements[rows[q].key] = { y: 0, scale: 0.9, opacity: 0, z: 0,
                                  front: false, hidden: true, height: 0, count: 1 }
  }

  return { decks: decks, placements: placements, height: Math.max(0, y) }
}
