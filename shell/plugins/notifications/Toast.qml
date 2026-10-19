// One notification card, in every state it has.
//
// The card never decides where it goes - Layout.js does that and hands it a
// placement. What the card owns is how it gets there (springs for anything the
// pointer caused, curves for anything the clock caused) and how long it lives.

import QtQuick
import QtQuick.Effects
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui

import "Markup.js" as Markup
import "Security.js" as Security
import "Delivery.js" as Delivery

Item {
  id: card

  property real fontScale: 1
  property bool showCountdown: false
  property var row: ({})
  property string senderImage: "" // helper-validated PNG data URL, never the sender's path
  property var place: ({ y: 0, scale: 1, opacity: 1, z: 1, front: true, hidden: false })
  // The scene that owns the clock. Everything below degrades to a still card
  // rather than breaking if it is not there.
  property var scene: null
  property bool expanded: false
  property bool sole: false                  // the only card on screen
  property bool paused: false
  property bool hovered: false
  property double now: Date.now()

  // "now" for the first minute, then minutes, then the clock time it arrived
  // at, then the day. Long enough ago and the exact minute stops mattering.
  function ago() {
    var t = Number(row.ts || 0) * 1000
    if (!t) return ""
    var s = Math.max(0, (now - t) / 1000)
    if (s < 50) return I18n.t("notifications.now")
    if (s < 3600) return I18n.t("notifications.minutesAgo").arg(Math.round(s / 60))
    var then = new Date(t)
    var locale = Qt.locale(I18n.formatLocale)
    var sameDay = new Date(now).toDateString() === then.toDateString()
    if (sameDay) return locale.toString(then, "HH:mm")
    var yest = new Date(now - 86400000).toDateString() === then.toDateString()
    if (yest) return I18n.t("notifications.yesterday")
    return locale.toString(then, "ddd")
  }
  property real cardWidth: Style.space(380)

  // The only duration the card owns. Everything it animates is a crossfade
  // inside its own edges; anything that moves the deck belongs to the scene.
  readonly property int fade: 150

  signal expired()
  signal activated()
  signal dismissed()
  signal snoozeRequested(int seconds)
  signal silenceRequested()

  readonly property bool critical: row.urgency === 2
  readonly property color dimColor: Qt.darker(Commons.Color.notifications.text, 1.4)
  readonly property color bodyColor: Qt.darker(Commons.Color.notifications.text, 1.15)
  readonly property color accentColor: critical ? Commons.Color.urgent
                                               : (row.urgency === 0 ? dimColor : Commons.Color.notifications.countdown)
  readonly property var cardBorderSpec: Border.surfaceSpec(
      "notifications", "border", Commons.Color.notifications.border,
      Math.max(1, Style.space(2)))
  readonly property bool hasBody: String(row.body || "").length > 0
  readonly property bool hasGlyph: String(row.glyph || "").length > 0
  // Omarchy's own toasts and bare notify-send calls name no source worth a
  // letter, and a summary that opens with its own glyph already has its mark.
  readonly property bool anonymous: row.app === "omarchy-action" || row.app === "notify-send"
  readonly property bool glyphLed: Delivery.summaryStartsWithGlyph(row.summary)
  readonly property real contentPaddingY: hasBody ? Style.space(10) : Style.space(7)
  // A card behind the front one in a collapsed deck is a shape, not a message:
  // the cards are translucent, so its text would otherwise read straight
  // through the card in front of it.
  readonly property bool showsContent: expanded || place.front

  // Two lines is right for a deck you are scanning. It is wrong for the one
  // message you stopped to read - and phone messages are the worst of it, a
  // sentence and a half arriving as a sentence and an ellipsis. So the body
  // opens when the deck is open, and on hover when there is nothing else on
  // screen to open. A card in a collapsed stack never does: every card there
  // is drawn at the front one's height, so a tall one would hang out of it.
  readonly property bool bodyOpen: expanded || (hovered && sole)
  readonly property int bodyLines: bodyOpen ? 8 : 2
  readonly property int stands: place.count || 1     // how many this card speaks for

  // Everything this card can do, in one row: what it found in its own text
  // first, then what the sender said it supports. Spelled out rather than
  // hinted at with an icon - a verification code hiding behind a key glyph is
  // a puzzle, and on a desktop where almost nothing carries actions, nobody
  // thinks to hover looking for them. What is written on the button is what
  // happens when you press it.
  // Every code the body carried, not just the first. One is the normal case
  // and says "Copy code"; two or more have to say which, because "Copy code"
  // twice is a coin toss.
  readonly property var foundCodes: {
    var all = String(row.codes || row.code || "").split(" ")
    var out = []
    for (var i = 0; i < all.length; i++) if (all[i]) out.push(all[i])
    return out
  }

  readonly property var allDeeds: {
    var out = []
    for (var c = 0; c < foundCodes.length; c++)
      out.push({ kind: "code", value: foundCodes[c],
                 label: foundCodes.length > 1 ? I18n.t("notifications.copyThisCode").arg(foundCodes[c])
                                              : I18n.t("notifications.copyCode") })
    if (String(row.link || ""))
      out.push({ kind: row.meeting ? "meeting" : "link",
                 label: row.meeting ? I18n.t("notifications.join") : I18n.t("notifications.openLink"),
                 value: String(row.link) })
    if (String(row.phone || ""))
      out.push({ kind: "phone", label: I18n.t("notifications.copyNumber"), value: String(row.phone) })
    if (String(row.replyPath || ""))
      out.push({ kind: "reply", label: I18n.t("notifications.reply"), value: "" })
    for (var i = 0; i < actions.length; i++) {
      // The phone's own "Reply" action opens a window somewhere else; ours
      // types the answer here, so it wins and the duplicate is dropped.
      if (String(row.replyPath || "") && /^reply$/i.test(String(actions[i].text || "")))
        continue
      out.push({ kind: "action", label: String(actions[i].text || ""), value: String(actions[i].id) })
    }
    return out
  }

  // What the card is holding, as marks rather than buttons. Buttons cost
  // height, and a collapsed deck draws every card at the height of the
  // tallest - so one card with two buttons padded out every other card on
  // screen. A mark says "there is something here" for free, and the buttons
  // themselves appear when the pointer is actually on the card.
  readonly property var marks: {
    var out = []
    if (String(row.code || "")) out.push("\u{f0306}")
    if (String(row.link || "")) out.push(row.meeting ? "\u{f0567}" : "\u{f0339}")
    if (String(row.phone || "")) out.push("\u{f03f2}")
    // A cursor mid-click, not the vertical dots this used to be: at the size
    // these are drawn, dots read as punctuation or as a line that got
    // truncated, and the whole point of a mark is to be noticed. The rest of
    // the family names the thing being carried - a key, a link, a phone, a
    // file - and this one names what you can do with it.
    if (actions.length > 0) out.push("\u{f0cfd}")
    return out
  }

  // Measure the actual themed buttons: a fixed count overflows with larger
  // fonts or longer action labels. Reserve More before admitting each action.
  readonly property var actionWidths: {
    var widths = []
    for (var i = 0; i < deedMeasures.count; i++) {
      var button = deedMeasures.itemAt(i)
      if (button) widths.push(button.implicitWidth)
    }
    return widths
  }
  readonly property int fits: {
    var widths = actionWidths, gap = deedRow.spacing, available = deedArea.width
    if (widths.length !== allDeeds.length) return 0
    var total = 0
    for (var i = 0; i < widths.length; i++) total += widths[i] + (i ? gap : 0)
    if (total <= available) return widths.length
    var used = moreMeasure.implicitWidth, count = 0
    for (var j = 0; j < widths.length; j++) {
      if (used + gap + widths[j] > available) break
      used += gap + widths[j]
      count++
    }
    return count
  }
  readonly property bool overflows: allDeeds.length > fits
  readonly property var deeds: allDeeds.slice(0, fits)
  readonly property var spare: allDeeds.slice(fits)

  Item {
    visible: false
    Repeater {
      id: deedMeasures
      model: card.allDeeds
      DeedButton {
        required property var modelData
        deed: modelData
        toast: card
      }
    }
    DeedButton {
      id: moreMeasure
      deed: ({ kind: "more", label: I18n.t("notifications.more"), value: "" })
      toast: card
    }
  }
  property bool deedsOpen: false
  property bool menuOpen: false
  property string actionsAlign: "right"      // right | left

  // Right-clicking a card asks about the source rather than about the message:
  // stop this one talking for a while, or stop everything. The lengths on
  // offer are the daemon's, which are the ones from settings - a desktop where
  // half an hour is the useful unit and one where half a day is are both real.
  property var snoozeOptions: []

  readonly property var menuDeeds: {
    var out = []
    for (var i = 0; i < snoozeOptions.length; i++)
      out.push({ kind: "snooze", label: String(snoozeOptions[i].menuLabel),
                 value: Number(snoozeOptions[i].seconds) })
    out.push({ kind: "silence", label: I18n.t("notifications.enableDnd"), value: 0 })
    return out
  }

  // The pointer, in the deck's coordinates, handed down from the one region
  // that is allowed to see it. Cards convert it to their own space so the
  // buttons inside them can light up.
  property real hoverX: -1
  property real hoverY: -1
  readonly property real localHoverX: hoverX - x
  readonly property real localHoverY: hoverY - y

  function doDeed(deed) {
    var kind = String(deed.kind || "")
    if (kind === "more") { deedsOpen = !deedsOpen; return }
    if (kind === "snooze") { menuOpen = false; snoozeRequested(Number(deed.value)); return }
    if (kind === "silence") { menuOpen = false; silenceRequested(); return }
    if (kind === "reply") { menuOpen = false; replyRequested(); return }
    if (kind === "action") { actionInvoked(String(deed.value)); return }
    offerTaken(kind, String(deed.value))
    takenKind = kind + ":" + String(deed.value)
    tick.restart()
  }

  signal offerTaken(string kind, string value)

  // What the sender itself said can be done. These are not guesses: the app
  // put them on the wire. A restored card has none, because the sender that
  // would have to carry them out is gone.
  property var actions: []
  property string replyError: ""
  signal actionInvoked(string identifier)

  // Replying to a message forwarded from the phone.
  property bool replying: false
  signal replyRequested()
  signal replySent(string text)
  signal replyCancelled()

  // Which one was just pressed, so its label can say so for a moment. Copying
  // to a clipboard is completely silent otherwise: you click, nothing moves,
  // and you click again to be sure.
  property string takenKind: ""      // "kind:value" of the last press
  Timer { id: tick; interval: 1400; onTriggered: card.takenKind = "" }

  // The card's own clock. One ticker drives both the countdown and the expiry,
  // so what you see and what happens cannot drift apart; pausing holds the
  // remaining time rather than restarting it, because a card you stopped to
  // read should not lose the seconds you spent reading it.
  property real remaining: Number(row.duration || 0)
  readonly property bool ticking: Number(row.duration || 0) > 0 && !paused && !replying
  onRowChanged: remaining = Number(row.duration || 0)

  Timer {
    interval: 100
    repeat: true
    running: card.ticking && card.remaining > 0
    onTriggered: {
      card.remaining -= interval
      if (card.remaining <= 0) card.expired()
    }
  }

  width: cardWidth
  height: body.height

  // Right-to-left languages read the card mirrored; the deck itself stays in
  // the top-right corner.
  LayoutMirroring.enabled: Commons.I18n.rightToLeft
  LayoutMirroring.childrenInherit: true

  // ---------------------------------------------------- what the scene reads
  //
  // The card with its action area closed: the part that does not move when
  // buttons appear. Summed explicitly rather than taken from the laid-out
  // height minus the action area, because that area's height is derived from
  // the card's - and subtracting it back out is a binding loop.
  // The words, without whatever the deeds are doing underneath them. The card's
  // height is measured from this, so it grows when the body opens.
  // Item.visible includes ancestor visibility. An inactive output must not
  // shrink the same notification's measurement on the active output.
  readonly property real textBlock:
      headline.height + (hasBody ? column.spacing + bodyBox.height : 0)

  // The same block at its two-line height, whatever the body is doing now. The
  // icon is centred on this rather than on the live one: a body that opens on
  // hover would otherwise walk the mark down the card exactly as the buttons
  // used to, and the mark is how you recognise the sender before reading.
  readonly property real restingBlock:
      headline.height + (hasBody ? column.spacing + bodyBox.restHeight : 0)

  readonly property real fixedHeight: plate.borderTop + plate.borderBottom
      + contentPaddingY * 2 + Math.max(thumb.height, textBlock)

  // The height this card's *state* implies. The deck lays out from this and
  // only this: feeding a rendered, mid-animation height back into the layout
  // is what made the stack stall and then jump.
  readonly property real targetHeight: fixedHeight + deedArea.wanted

  // And the height the scene says it is right now, on the way there.
  property real drawnHeight: targetHeight

  onHoveredChanged: if (!hovered) menuOpen = false
  onExpandedChanged: if (!expanded) menuOpen = false

  // Position, size and opacity all come from the scene. The card owns none of
  // them and animates none of them: it is told where it is, every frame, by
  // the one clock the deck runs. What it still owns is everything inside its
  // own edges - a button row appearing, a reply field opening - which may
  // animate itself freely, on one condition: it must not change the height the
  // layout reads while it is moving. That is `targetHeight`, and it is a step
  // function of the card's state.
  y: scene ? scene.at(row.key, "y") : 0
  z: place.z
  scale: scene ? scene.at(row.key, "scale") : 1
  opacity: place.hidden ? 0 : (scene ? scene.at(row.key, "opacity") : 1)
  transformOrigin: Item.Top

  // `visible` is deliberately not bound to anything. It used to be
  // `opacity > 0.01`, and that closed a circle: toggling visible changes what
  // the card contributes to the layout, the layout is measured back into
  // `heights`, and `heights` is where the scene gets opacity from - a hundred
  // binding-loop warnings for every scene of cards arriving, and the wasted
  // re-evaluation behind them, on exactly the frames the animation is trying
  // to keep smooth. Deriving it from `place.hidden` instead only moved the
  // loop, because `place` is layout output too. Anything the layout produces
  // is the wrong side of this fence.
  //
  // Nothing is lost. A hidden card is already at opacity 0, and the scene
  // graph skips a fully transparent subtree, so it costs no drawing. What
  // `visible: false` did do is refuse the pointer, and `enabled` says that on
  // its own without being part of any measurement.
  enabled: !place.hidden

  // The surface is the shell's own notification surface. BorderSurface keeps
  // gradients and per-side border widths intact; content below is inset by
  // those exact widths so neither measurement nor paint crosses the theme edge.
  BorderSurface {
    id: plate
    x: body.x
    width: body.width
    height: body.height
    radius: Style.cornerRadius
    color: Commons.Color.notifications.background
    borderSpec: card.cardBorderSpec
  }

  // Everything that changes: text, icon and countdown. It stays offscreen-layer
  // free so the ticking countdown does not force a cached card repaint.
  Item {
    id: body
    x: 0
    width: parent.width
    height: card.drawnHeight

    Row {
      id: layout
      // Anchored to the top, not centred. A card grows downwards when its
      // buttons or its reply field appear, and content hung off the centre
      // line slides up by half of whatever was added - so the words move while
      // you are reading them.
      anchors { left: parent.left; right: parent.right; top: parent.top
                leftMargin: plate.contentLeftInset + Style.space(12)
                rightMargin: plate.contentRightInset + Style.space(12)
                topMargin: plate.contentTopInset + card.contentPaddingY }
      spacing: thumb.compact ? Style.space(8) : Style.space(12)

      // The card's mark: the sender's image, else the icon resolved for its
      // source, else the glyph an Omarchy sender asked for, else the first
      // letter of wherever it came from. Omarchy's own anonymous toasts, and
      // summaries that open with their own glyph, go without.
      Item {
        id: thumb
        readonly property bool pictured: picture.status === Image.Ready && best !== ""
        readonly property bool glyphed: !pictured && card.hasGlyph
        readonly property bool lettered: !pictured && !glyphed && !card.anonymous && !card.glyphLed
        // A one-line toast with a glyph keeps the glyph at text size beside
        // its line rather than in a slot taller than the card's text.
        readonly property bool compact: glyphed && !card.hasBody
        readonly property real slot: Style.space(40)
        width: pictured || lettered ? slot : glyphed ? (compact ? glyphText.implicitWidth : slot) : 0
        height: compact ? glyphText.implicitHeight : slot
        visible: width > 0
        // Centred against the text beside it, at its resting height: the body
        // opening on hover must not walk the mark down the card.
        y: Math.max(0, (card.restingBlock - height) / 2)
        opacity: card.showsContent ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: card.fade } }

        readonly property bool mono: String(picture.source).indexOf("-mono.png") >= 0

        function asUrl(src) {
          var value = String(src || "")
          if (!value) return ""
          return value.indexOf("file://") === 0 || value.indexOf("image://") === 0
                 ? value : "file://" + value
        }

        // What the sender handed over, and what the icon helper resolved for
        // this source. Nothing else: Quickshell.iconPath happily returns a
        // provider URL for an icon that does not exist, and that draws as a
        // checkerboard.
        readonly property string sent: /^image:\/\/qsimage\/[0-9]+\/[0-9]+$/.test(String(card.row.image || ""))
                                       ? String(card.row.image) : card.senderImage
        readonly property string resolved: asUrl(card.row.stored_image)

        // The sender's own picture wins while it works - for a message
        // forwarded from a phone that is often the contact's photo. When it
        // will not draw, the resolved icon takes over.
        property bool sentFailed: false
        onSentChanged: sentFailed = false
        readonly property string best: (sent && !sentFailed) ? sent : resolved
        readonly property bool photo: best !== "" && best === sent

        Rectangle {
          anchors.fill: parent
          visible: thumb.lettered
          radius: Style.cornerRadius
          color: Style.normalFillFor(Commons.Color.notifications.text, card.accentColor, Commons.Color.urgent)

          Text {
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: String(card.row.source || card.row.app || "?").substring(0, 1).toUpperCase()
            color: card.dimColor
            font.family: Style.font.family
            font.pixelSize: Style.font.body * card.fontScale
            font.weight: Font.DemiBold
          }
        }

        Text {
          id: glyphText
          textFormat: Text.PlainText
          anchors.centerIn: parent
          visible: thumb.glyphed
          text: String(card.row.glyph || "")
          color: Commons.Color.notifications.text
          font.family: Style.font.family
          font.pixelSize: (thumb.compact ? Style.font.icon : Style.font.displayLarge) * card.fontScale
        }

        // A one-colour glyph is painted in the theme's text colour rather
        // than drawn as it came, or a dark mark disappears into a dark card.
        Rectangle {
          anchors.fill: parent
          visible: thumb.mono && thumb.pictured
          color: Commons.Color.notifications.text
          opacity: 0.85
          layer.enabled: visible
          layer.effect: MultiEffect { maskEnabled: true; maskSource: picture }
        }

        Image {
          id: picture
          anchors.fill: parent
          visible: thumb.pictured && !thumb.mono
          source: thumb.best
          onStatusChanged: if (status === Image.Error && source == thumb.sent) thumb.sentFailed = true
          // A photo fills its square; an app icon keeps its own shape.
          fillMode: thumb.photo ? Image.PreserveAspectCrop : Image.PreserveAspectFit
          // Constant, so the slot growing or shrinking never reloads the image.
          sourceSize.width: thumb.slot * Screen.devicePixelRatio
          sourceSize.height: thumb.slot * Screen.devicePixelRatio
          asynchronous: true
          // Rounded like the card only when the theme rounds corners at all.
          layer.enabled: visible && thumb.photo && Style.cornerRadius > 0
          layer.effect: MultiEffect { maskEnabled: true; maskSource: mask }
        }

        Rectangle {
          id: mask
          anchors.fill: parent
          visible: false
          layer.enabled: true
          radius: Style.cornerRadius
          color: "black"
        }
      }

      Column {
        id: column
        width: layout.width - (thumb.visible ? thumb.width + layout.spacing : 0)
        spacing: Style.space(3)

        // Title, then how many this one stands for, then when it arrived.
        // The sender's name used to sit above this; it says "notify-send" more
        // often than it says anything useful, so it now only picks the icon.
        Item {
          id: headline
          width: parent.width
          height: Math.max(title.implicitHeight, rightSide.height,
                           badge.visible ? badge.height : 0)
          opacity: card.showsContent ? 1 : 0
          Behavior on opacity { NumberAnimation { duration: card.fade } }

          Text {
            textFormat: Text.PlainText
            id: title
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(1, parent.width - rightSide.width
                   - (badge.visible ? badge.width + Style.space(6) : 0)
                   - (titleMarks.visible ? titleMarks.width + Style.space(7) : 0)
                   - Style.space(8))
            text: String(card.row.summary || "")
            color: card.critical ? Commons.Color.urgent : Commons.Color.notifications.text
            font.family: "Liberation Sans"
            font.pixelSize: Style.font.title * card.fontScale
            font.bold: true
            // Larger fonts should wrap the summary, not hide it after a few words.
            // Bound unusually long titles just as we bound the message body.
            wrapMode: Text.Wrap
            maximumLineCount: card.bodyOpen ? 8 : 3
            elide: Text.ElideRight
          }

          // Straight after the title, at the title's size and in the theme's
          // foreground. No chip: tried as an inverted pill beside the time and
          // as a badge on the corner of the app icon, and both read as heavy -
          // the badge version also stacked leftwards off the icon as soon as a
          // card had more than one thing to offer, which is the normal case.
          // As glyphs on the headline they are part of the sentence.
          Row {
            id: titleMarks
            visible: card.marks.length > 0
            anchors.verticalCenter: title.verticalCenter
            // Placed by arithmetic, so it follows a right-to-left card itself.
            readonly property real titleInk: Math.min(title.implicitWidth, title.width)
            x: card.LayoutMirroring.enabled
               ? title.x + title.width - titleInk - Style.space(7) - width
               : title.x + titleInk + Style.space(7)
            spacing: Style.space(5)

            Repeater {
              model: card.marks
              Text {
                textFormat: Text.PlainText
                required property var modelData
                text: modelData
                color: Commons.Color.notifications.text
                opacity: 0.9
                font.family: Style.font.family
                font.pixelSize: Style.font.body * card.fontScale
              }
            }
          }

          Rectangle {
            id: badge
            // The row, not the time inside it: anchoring across into another
            // item's children is not a sibling relationship and Qt refuses it.
            anchors.right: rightSide.left
            anchors.rightMargin: Style.space(6)
            anchors.verticalCenter: title.verticalCenter
            visible: card.stands > 1
            width: badgeText.implicitWidth + Style.spacing.sm * 2
            height: badgeText.implicitHeight + Style.spacing.xxs * 2
            radius: Style.cornerRadius
            color: Style.normalFillFor(Commons.Color.notifications.text, card.accentColor,
                                       Commons.Color.urgent)

            Text {
              textFormat: Text.PlainText
              id: badgeText
              anchors.centerIn: parent
              text: String(card.stands)
              color: card.dimColor
              font.family: Style.font.family
              font.pixelSize: Style.font.caption * card.fontScale
            }
          }

          // Timestamp and dismiss action share one stable slot, so hover can
          // crossfade between them without moving the headline.
          Row {
            id: rightSide
            anchors.right: parent.right
            anchors.verticalCenter: title.verticalCenter
            spacing: Style.space(5)

            // The time and the close control occupy the same square. Hover
            // crossfades between them rather than sliding the time aside: one
            // thing changing into another reads as a single control, and
            // nothing has to move to make room.
            Item {
              width: Math.max(stamp.implicitWidth, shut.implicitWidth)
              height: Math.max(stamp.implicitHeight, shut.implicitHeight)
              anchors.verticalCenter: parent.verticalCenter

              Text {
                textFormat: Text.PlainText
                id: stamp
                anchors.centerIn: parent
                text: card.ago()
                color: card.dimColor
                opacity: card.hovered ? 0 : 1
                visible: opacity > 0.01
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall * card.fontScale
                Behavior on opacity { NumberAnimation { duration: card.fade } }
              }

              // A bare mark, like the rest of the shell's close controls.
              Item {
                id: shut
                anchors.centerIn: parent
                implicitWidth: closeMark.implicitWidth + Style.space(6)
                implicitHeight: closeMark.implicitHeight
                // The deck owns pointer hover, so the card works out whether
                // the pointer is on this mark from the coordinates it is given.
                readonly property bool hot: {
                  if (!card.hovered) return false
                  var origin = mapToItem(card, 0, 0)
                  return card.localHoverX >= origin.x
                      && card.localHoverX <= origin.x + width
                      && card.localHoverY >= origin.y
                      && card.localHoverY <= origin.y + height
                }
                enabled: card.hovered
                opacity: card.hovered ? 1 : 0
                visible: opacity > 0.01
                Behavior on opacity { NumberAnimation { duration: card.fade } }

                Text {
                  id: closeMark
                  anchors.centerIn: parent
                  textFormat: Text.PlainText
                  text: "\u2715"
                  color: shut.hot ? Commons.Color.notifications.text : card.dimColor
                  font.pixelSize: Math.round(Style.font.caption * 1.44 * card.fontScale)
                }

                MouseArea {
                  anchors.fill: parent
                  anchors.margins: -Style.space(3)
                  acceptedButtons: Qt.LeftButton | Qt.RightButton
                  cursorShape: Qt.PointingHandCursor
                  onClicked: function(mouse) {
                    if (mouse.button === Qt.RightButton) card.menuOpen = !card.menuOpen
                    else card.dismissed()
                  }
                }
              }
            }
          }
        }

        // Rich text cannot elide, so bodies beyond the current two-line or
        // eight-line disclosure are flattened into the bounded plain-text
        // rendering that can end in an ellipsis.
        FontMetrics {
          id: metrics
          font.family: "Liberation Sans"
          font.pixelSize: Style.font.title * card.fontScale
        }

        Item {
          id: bodyBox
          clip: true
          width: parent.width
          // Use the text's actual laid-out height so a short body does not
          // reserve empty lines and a wrapped body keeps every visible pixel.
          //
          // Measured from the laid-out height, never from `lineCount`: in
          // RichText mode lineCount counts paragraphs rather than wrapped
          // lines, so a single sentence that visibly takes two lines still
          // reports one - which sized the box to one line and clipped the rest.
          readonly property real lineH: Math.max(1, metrics.height)
          // The cap the body is being held to right now, and the slack that
          // decides overflow: a body a hair over the cap is not worth
          // flattening, it is worth one more pixel.
          readonly property real cap: lineH * card.bodyLines
          readonly property bool overflow: rich.contentHeight > cap + lineH * 0.4
          // The visible height comes from the rendering that is actually on
          // screen; converting it to a rounded line count clipped descenders.
          readonly property real shown: overflow ? plain.contentHeight : rich.contentHeight
          // Not clamped to `cap`. The line limit is enforced where the lines
          // are - `plain.maximumLineCount` - and its laid-out height is a hair
          // taller than lineH x lines once leading and descenders are counted.
          // Clamping the box to the arithmetic instead sliced the last line
          // through the middle rather than eliding it.
          height: Math.ceil(shown)

          // What this box would be if the body were closed. Only the icon reads
          // it, and only so that it does not move when the body opens.
          readonly property real restHeight:
              Math.min(Math.ceil(lineH * 2), Math.ceil(rich.contentHeight))
          visible: card.hasBody
          opacity: card.showsContent ? 1 : 0
          Behavior on opacity { NumberAnimation { duration: card.fade } }

          Text {
            id: rich
            width: parent.width
            visible: !bodyBox.overflow
            textFormat: Text.RichText
            text: Markup.colourLinks(String(card.row.bodyRich || card.row.body || ""),
                                     String(Commons.Color.notifications.countdown))
            color: card.bodyColor
            font.family: "Liberation Sans"
            font.pixelSize: Style.font.title * card.fontScale
            wrapMode: Text.Wrap
            // Second gate on the same rule. Markup drops an anchor it will
            // not vouch for, so nothing unsafe should arrive here - but this
            // is one regex away from being wrong, and the cost of the check
            // is a function call.
            onLinkActivated: function(url) {
              Security.openExternalUrl(url)
            }
          }

          Text {
            textFormat: Text.PlainText
            id: plain
            width: parent.width
            visible: bodyBox.overflow
            text: String(card.row.bodyLine || card.row.body || "")
            color: card.bodyColor
            font.family: "Liberation Sans"
            font.pixelSize: Style.font.title * card.fontScale
            wrapMode: Text.Wrap
            maximumLineCount: card.bodyLines
            elide: Text.ElideRight
          }

        }

        // Everything the card can do, written out. Visible whenever the card's
        // content is - not on hover - because an action nobody knows is there
        // may as well not exist. Three across is what fits; anything beyond
        // that folds into "More", which opens the lot as a list rather than a
        // floating menu: this surface is clipped, and a popup that can be cut
        // off is worse than one more row.
        Item {
          id: deedArea
          width: parent.width

          // The space under the body does one job at a time. Answering used to
          // leave the buttons stacked above the field, which read as a form
          // rather than as a reply - and put "Reply" directly above the box it
          // had just opened. Escape puts them back, because it puts the card
          // back to not replying.
          //
          // The row is under the pointer only, and only in an open deck: a
          // collapsed deck is a peek of an edge, and buttons appearing inside
          // one would be clipped to nothing.
          readonly property string mode: card.replying ? "reply"
                                       : card.menuOpen ? "menu"
                                       : card.deedsOpen ? "list"
                                       : (card.hovered && card.expanded
                                          && card.allDeeds.length > 0) ? "row" : ""

          readonly property real contentHeight: mode === "reply" ? replyBox.height
                                              : mode === "menu" ? menuColumn.implicitHeight
                                              : mode === "list" ? deedColumn.implicitHeight
                                              : mode === "row" ? deedRow.implicitHeight : 0
          // What this area's state asks for, with nothing animating. The card
          // lays out from it; the drawn height below is whatever slack the
          // scene has given the card so far, so the two can never disagree.
          readonly property real wanted: mode === "" ? 0 : contentHeight + Style.space(7)
          height: Math.max(0, card.drawnHeight - card.fixedHeight)
          visible: height > 0
          clip: true

          Row {
            id: deedRow
            anchors.bottom: parent.bottom
            // Right by default: the buttons line up under the time and the
            // close control rather than under the icon, which keeps the left
            // edge of every card reading as one column of text.
            anchors.right: card.actionsAlign === "right" ? parent.right : undefined
            anchors.left: card.actionsAlign === "right" ? undefined : parent.left
            spacing: Style.space(6)
            opacity: deedArea.mode === "row" ? 1 : 0
            visible: opacity > 0.01
            Behavior on opacity { NumberAnimation { duration: card.fade } }

            Repeater {
              model: card.deeds
              DeedButton {
                required property var modelData
                deed: modelData
                toast: card
              }
            }

            DeedButton {
              visible: card.spare.length > 0
              deed: ({ kind: "more", label: I18n.t("notifications.more"), value: "" })
              toast: card
            }
          }

          // Typing an answer, in the card the message arrived in. Only the
          // phone can actually deliver it - this is the near end of a
          // conversation that lives on the device.
          Item {
            id: replyBox
            width: parent.width
            // A step, not an animation. This height is part of what the
            // layout reads, and anything the layout reads must not move
            // between frames - the scene animates the slack around it.
            height: card.replying ? replyInput.implicitHeight + Style.space(3) : 0
            visible: height > 0
            anchors.bottom: parent.bottom
            clip: true

            // The kit's own text input: same focus ring, selection tint and
            // padding as every other field in the desktop, and it follows
            // [controls] in the theme rather than a shape invented here.
            TextField {
              id: replyInput
              anchors.fill: parent
              anchors.topMargin: Style.space(3)
              foreground: Commons.Color.notifications.text
              font.family: Style.font.family
              font.pixelSize: Style.font.body * card.fontScale
              leftPadding: horizontalPadding + Border.left(_borderSpec)
                           + (sendButton.visible && sendButton.isRtl
                              ? sendButton.width + Style.spacing.controlGap : 0)
              rightPadding: horizontalPadding + Border.right(_borderSpec)
                            + (sendButton.visible && !sendButton.isRtl
                               ? sendButton.width + Style.spacing.controlGap : 0)
              placeholderText: card.replyError || I18n.t("notifications.replyTo").arg(String(card.row.replyTo || card.row.summary || ""))
              onAccepted: { card.replySent(text); text = "" }
              Keys.onEscapePressed: { text = ""; card.replyCancelled() }

              // Enter sends, but an affordance nobody can see is not one.
              // Sits at the trailing edge of the field. When the first
              // directional character is Arabic or Hebrew the field reads
              // right-to-left, so "trailing" means left.
              Button {
                id: sendButton
                x: isRtl
                   ? Border.left(replyInput._borderSpec) + replyInput.horizontalPadding
                   : parent.width - width - Border.right(replyInput._borderSpec)
                     - replyInput.horizontalPadding
                anchors.verticalCenter: parent.verticalCenter
                visible: replyInput.text.length > 0
                text: I18n.t("notifications.send")
                bordered: false
                foreground: Commons.Color.notifications.text
                fontFamily: Style.font.family
                fontSize: Style.font.body * card.fontScale
                onClicked: { card.replySent(replyInput.text); replyInput.text = "" }

                // True when the reply text starts with an RTL script.
                // Skips anything without a strong direction (spaces,
                // digits, brackets, punctuation) to find the first
                // character that actually picks a side. 
                property bool isRtl: {
                  var t = replyInput.text;
                  for (var i = 0; i < t.length;) {
                    var c = t.codePointAt(i);
                    i += c > 0xFFFF ? 2 : 1;                         // step past surrogate pairs
                    if (c <= 0x7F && !(c >= 0x41 && c <= 0x5A)
                                  && !(c >= 0x61 && c <= 0x7A))
                      continue;                                       // skip all ASCII non-letters
                    if (c <= 0x024F) return false;                    // Latin
                    if (c >= 0x0590 && c <= 0x08FF) return true;      // Hebrew, Arabic, Syriac, Thaana
                    if (c >= 0xFB50 && c <= 0xFDFF) return true;      // Arabic Presentation Forms-A
                    if (c >= 0xFE70 && c <= 0xFEFF) return true;      // Arabic Presentation Forms-B
                    return false;
                  }
                  return false;
                }
              }
            }

            onVisibleChanged: if (visible) replyInput.forceActiveFocus()
          }

          Column {
            id: deedColumn
            anchors.bottom: parent.bottom
            width: parent.width
            spacing: Style.space(4)
            opacity: deedArea.mode === "list" ? 1 : 0
            visible: opacity > 0.01
            Behavior on opacity { NumberAnimation { duration: card.fade } }

            Repeater {
              model: card.deedsOpen ? card.allDeeds : []
              DeedButton {
                required property var modelData
                deed: modelData
                toast: card
                wide: true
              }
            }
          }

          // Right-click: what to do about this sender, rather than about this
          // message. Drawn in the card rather than as a popup for the same
          // reason "More" is - the notification surface is clipped, and a menu
          // that can be cut in half is worse than one that pushes the card
          // down by four rows.
          Column {
            id: menuColumn
            anchors.bottom: parent.bottom
            width: parent.width
            spacing: Style.space(4)
            opacity: deedArea.mode === "menu" ? 1 : 0
            visible: opacity > 0.01
            Behavior on opacity { NumberAnimation { duration: card.fade } }

            Repeater {
              model: card.menuOpen ? card.menuDeeds : []
              DeedButton {
                required property var modelData
                deed: modelData
                toast: card
                wide: true
              }
            }
          }
        }
      }
    }

    // Optional visual countdown. The expiry clock keeps running when this is
    // disabled, so hiding the animation never makes a notification permanent.
    BorderSurface {
      visible: card.showCountdown && card.row.duration > 0 && card.place.front
               && card.remaining > 0 && !card.expanded
      anchors { left: parent.left; bottom: parent.bottom
                leftMargin: plate.contentLeftInset + Style.space(7)
                bottomMargin: plate.contentBottomInset }
      height: Style.spacing.hairline
      radius: Style.cornerRadius
      color: card.accentColor
      borderSpec: Border.none()
      width: visible ? Math.max(0, (body.width - plate.contentLeftInset
                                    - plate.contentRightInset - Style.space(14))
                                   * (card.remaining / Math.max(1, card.row.duration))) : 0
    }

    // Clicks on the card. Underneath the card's own content: this covers the
    // whole card and is declared after it, so it sat on top and swallowed
    // every click before a button could see one - the buttons highlighted on
    // hover and then did nothing when pressed. Items above that do not accept
    // a click still let it fall through to here, so click-to-open keeps
    // working everywhere except on an actual button.
    MouseArea {
      anchors.fill: parent
      z: -1
      // Deliberately NOT hoverEnabled: hover goes to the topmost item that
      // wants it, so a card that took hover would starve the deck's own
      // region and the stack would never expand.
      hoverEnabled: false
      acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
      cursorShape: Qt.PointingHandCursor

      onClicked: function(mouse) {
        if (mouse.button === Qt.RightButton) { card.menuOpen = !card.menuOpen; return }
        // With the menu open, a click anywhere else on the card is a way out
        // of it rather than a way into the app - the surface takes no keyboard
        // focus while it is open, so Escape never reaches us.
        if (card.menuOpen) { card.menuOpen = false; return }
        if (mouse.button === Qt.MiddleButton) card.dismissed()
        else card.activated()
      }
    }
  }
}
