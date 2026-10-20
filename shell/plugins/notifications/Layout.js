// Where every card sits: rows in, placements out. Cards are placed absolutely,
// so a card keeps its identity (and its animation) when the one above leaves.
.pragma library

// Collapsed geometry.
var PEEK = 10          // px each card behind the front one drops
var SHRINK = 0.035     // and the scale it loses
var VISIBLE = 3        // cards drawn before the rest just fade out
var FADE = 0.55        // opacity of the last drawn card in a collapsed deck

function groupKeyFor(row) {
  return String(row.groupKey || row.source || row.app || "?")
}

// One deck in "all" mode; one per sender in "source" mode.
function deckKeyFor(row, stacking) {
  return stacking === "source" ? groupKeyFor(row) : "all"
}

// A deck shows every notification. Grouping is a count on the newest card from
// each source, not hiding the rest, so there is still a stack to expand.
function groupRows(rows) {
  var counts = {}, seen = {}, items = [], i, key
  for (i = 0; i < rows.length; i++) {
    key = groupKeyFor(rows[i])
    counts[key] = (counts[key] || 0) + 1
  }
  for (i = 0; i < rows.length; i++) {
    key = groupKeyFor(rows[i])
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
  var order = [], byKey = {}
  for (var i = 0; i < rows.length; i++) {
    var key = deckKeyFor(rows[i], stacking)
    if (!byKey[key]) { byKey[key] = { key: key, rows: [] }; order.push(key) }
    byKey[key].rows.push(rows[i])
  }

  var decks = []
  for (var d = 0; d < order.length; d++) {
    var deck = byKey[order[d]]
    // In "source" mode the deck already separates senders.
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
    // Shut, every card takes the front card's height, so a taller one behind
    // does not hang out below the stack.
    var frontHeight = heightOf(items[0].key)

    for (var r = 0; r < items.length; r++) {
      var item = items[r]
      if (open) {
        var height = heightOf(item.key)
        placements[item.key] = {
          y: y, scale: 1, opacity: 1, z: 1000 - r, front: r === 0,
          hidden: false, height: height, count: item.count
        }
        y += height + gap
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

  return { decks: decks, placements: placements, height: Math.max(0, y) }
}
