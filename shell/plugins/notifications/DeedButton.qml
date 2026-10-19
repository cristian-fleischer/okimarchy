// One thing a notification can do, as a button with its name on it.
//
// Omarchy's own Button, not a shape of our own: it carries the theme's control
// fills, border specs, focus ring and padding, all of which come from
// [controls] in the theme's shell.toml. A hand-rolled pill looked close on one
// theme and wrong on the next, and it quietly ignored every control token the
// desktop has.

import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Button {
  id: button

  property var deed: ({})
  // Not "card": the toast's id is `card`, so a property of that name binds to
  // itself rather than to the toast, sits there as null, and every click dies
  // on it silently.
  property var toast: null
  property bool wide: false

  // Matched on the value as well as the kind: a card carrying two codes has
  // two Copy buttons, and pressing one used to tick both.
  readonly property bool taken: toast && toast.takenKind
                                === String(deed.kind) + ":" + String(deed.value)

  // Under the pointer? Worked out from where the deck says the pointer is,
  // because this button never receives hover itself - the deck's hover region
  // is above every card and takes it first.
  readonly property bool hot: {
    if (!toast || !toast.hovered) return false
    var origin = mapToItem(toast, 0, 0)
    var px = toast.localHoverX, py = toast.localHoverY
    return px >= origin.x && px <= origin.x + width
        && py >= origin.y && py <= origin.y + height
  }

  // A tick, not a word: "Copied" was being shown for "Open link" too, and a
  // per-verb past tense would change the button's width the moment you
  // pressed it. The mark means "that happened" whatever the verb was.
  readonly property string labelText: taken ? "\u{f012c}" : String(deed.label || "")

  bordered: true
  hasCursor: hot                      // paints the theme's hover state
  foreground: Commons.Color.notifications.text
  fontFamily: Style.font.family
  fontSize: Style.font.body * (toast ? toast.fontScale : 1)

  // Full width in the "More" list, its own width in the row.
  leftAlign: wide
  width: wide && parent ? parent.width : implicitWidth

  // The shared Button's label is a single unbounded line. Keep its themed
  // surface and hit handling, but measure our own label so full-width actions
  // wrap and contribute their complete height to the card's list.
  implicitWidth: label.implicitWidth + horizontalPadding * 2
                 + _reservedBorderLeft + _reservedBorderRight
  implicitHeight: label.implicitHeight + verticalPadding * 2
                  + _reservedBorderTop + _reservedBorderBottom

  Text {
    id: label
    x: button._reservedContentLeftInset
    anchors.verticalCenter: parent.verticalCenter
    width: Math.max(1, button.width - button._reservedContentLeftInset
                      - button.rightPadding - button._reservedBorderRight)
    text: button.labelText
    textFormat: Text.PlainText
    wrapMode: button.wide ? Text.Wrap : Text.NoWrap
    color: button.selected ? button._selectedColor : button.foreground
    font.family: button.fontFamily
    font.pixelSize: button.fontSize
    font.bold: button.selected
  }

  onClicked: button.toast.doDeed(button.deed)
}
