// One thing a notification can do, as a themed Button with its name on it.

import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Button {
  id: button

  property var deed: ({})
  // Not "card": the toast's id is `card`, so a property of that name would
  // bind to itself and stay null.
  property var toast: null
  property bool wide: false

  // Matched on the value too: a card with two codes has two Copy buttons.
  readonly property bool taken: toast && toast.takenKind
                                === String(deed.kind) + ":" + String(deed.value)

  // The deck's hover region sits above every card, so hover is worked out
  // from the pointer position the deck hands down.
  readonly property bool hot: toast ? toast.pointerOver(button) : false

  // A tick rather than a past-tense verb, so the width does not change.
  readonly property string labelText: taken ? "\u{f012c}" : String(deed.label || "")

  bordered: true
  hasCursor: hot                      // paints the theme's hover state
  foreground: Commons.Color.notifications.text
  fontFamily: Style.font.family
  fontSize: Style.font.body * (toast ? toast.fontScale : 1)

  // Full width in the "More" list, its own width in the row.
  leftAlign: wide
  width: wide && parent ? parent.width : implicitWidth

  // The shared Button's label is a single unbounded line. Measure our own so
  // full-width actions wrap and contribute their complete height.
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
