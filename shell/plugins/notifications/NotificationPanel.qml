// The notification panel: what has been held back, what came in recently,
// the history on disk, snooze controls, and the notification preferences.
//
// Hosted by the bar's notification indicator (bar/indicators/Dnd.qml), one per
// monitor, and anchored to it. The service decides everything; this only draws
// it and asks for changes.

import QtQuick
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Item {
  id: root

  required property Item anchorItem
  property QtObject bar: null
  property var service: null

  readonly property bool opened: controller.open
  property bool settingsView: false

  function open() {
    settingsView = false
    controller.show()
  }
  function openSettings() {
    settingsView = true
    controller.show()
  }
  function close() { controller.hide() }
  function toggle() {
    if (controller.open) controller.hide()
    else open()
  }

  PanelController { id: controller }
  Component.onDestruction: if (service) service.notePanel(root, false)

  // ------------------------------------------------------------- state
  readonly property int snoozeRevision: service ? service.snoozeRevision : 0
  readonly property int heldRevision: service ? service.heldRevision : 0
  readonly property int historyRevision: service ? service.historyRevision : 0
  readonly property bool silenced: service ? service.doNotDisturb : false
  readonly property var snoozed: { snoozeRevision; return service ? service.liveSnoozes() : [] }
  readonly property double globalUntil: { snoozeRevision; return service ? service.globalSnoozeUntil : 0 }
  readonly property bool globalSnoozed: globalUntil > 0
  readonly property bool quiet: silenced || globalSnoozed
  readonly property bool hasState: quiet || snoozed.length > 0
  readonly property bool codesLetThrough: service ? service.codesBypassQuiet : true
  readonly property bool sharingOfferPending: service ? service.sharingOfferPending : false
  readonly property var preferences: service ? service.preferences : ({})

  readonly property var recent: { snoozeRevision; return service ? service.recentForPanel(service.recentCount) : [] }
  readonly property var history: { historyRevision; return service ? service.historyRows : [] }
  readonly property var sources: {
    snoozeRevision; heldRevision
    return service ? service.quietSources(service.sourceLimit) : []
  }

  property string expandedKey: ""
  property bool recentExpanded: false
  property bool historyExpanded: false
  property int cursorAt: 0
  property bool cursorLive: false
  property bool globalChoosing: false

  onQuietChanged: if (quiet) recentExpanded = false
  onOpenedChanged: {
    if (service) service.notePanel(root, opened)
    cursorAt = 0; cursorLive = false; expandedKey = ""; globalChoosing = false
    recentExpanded = false
    historyExpanded = false
    if (!opened) settingsView = false
    // Read on opening rather than kept up to date: the panel is the only
    // thing that ever asks.
    if (opened && service) {
      service.refreshHeld()
      service.refreshHistory()
    }
  }
  onSettingsViewChanged: {
    // The panel focuses its content only when it opens; a view switch inside
    // an open panel moves focus itself once bindings settle.
    Qt.callLater(function() {
      if (root.opened && panel.loadedContent) panel.loadedContent.forceActiveFocus()
    })
  }

  // ------------------------------------------------------------- looks
  readonly property color panelFg: Commons.Color.popups.text
  readonly property color dim: Qt.darker(panelFg, 1.4)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  // Do not disturb in the urgent role, a snooze that will end in the accent
  // role, so the two quiet states never read as the same.
  readonly property color silencedColour: Commons.Color.urgent
  readonly property color snoozedColour: Commons.Color.accent

  readonly property string bell: "\u{f009a}"
  readonly property string bellOff: "\u{f009b}"
  readonly property string bellSleep: "\u{f00a0}"
  readonly property string keyGlyph: "\u{f0306}"
  readonly property string keyOff: "\u{f0308}"
  readonly property string hourglass: "\u{f051f}"
  readonly property string chevronDown: "\u{f0140}"
  readonly property string chevronUp: "\u{f0143}"

  // ------------------------------------------------------------- words
  readonly property string timeFormat: preferences.timeFormat || "system"

  function clockTime(when) {
    var locale = Qt.locale(I18n.formatLocale)
    if (timeFormat === "24h") return locale.toString(when, "HH:mm")
    if (timeFormat === "12h") return locale.toString(when, "h:mm ap")
    return locale.toString(when, locale.timeFormat(Locale.ShortFormat))
  }

  // A wake time on another day carries the day offset the way a flight
  // arrival does: "which night" is the question, not the date.
  function dayOffset(when) {
    var today = new Date(); today.setHours(0, 0, 0, 0)
    var then = new Date(when.getTime()); then.setHours(0, 0, 0, 0)
    var days = Math.round((then.getTime() - today.getTime()) / 86400000)
    return days <= 0 ? "" : " +" + days
  }

  // "28m", "3h", and the wake time itself once the wait stops being the
  // useful half of the answer.
  function waitingFor(until) {
    var left = Math.max(0, until - Date.now() / 1000)
    var minutes = Math.max(1, Math.round(left / 60))
    if (minutes < 60) return I18n.t("notifications.minutesShort").arg(minutes)
    if (left < 8 * 3600) return I18n.t("notifications.hoursShort").arg(Math.max(1, Math.round(left / 3600)))
    var when = new Date(until * 1000)
    return clockTime(when) + dayOffset(when)
  }

  function heldLabel(count) {
    return I18n.tn("notifications.heldCount", count).arg(count)
  }

  readonly property string stateLine: {
    snoozeRevision
    if (globalSnoozed) {
      var when = new Date(globalUntil * 1000)
      return I18n.t("notifications.snoozedUntil").arg(clockTime(when) + dayOffset(when))
    }
    if (silenced) return I18n.t("notifications.dndOn")
    if (snoozed.length > 0) return I18n.tn("notifications.sourcesSnoozed", snoozed.length).arg(snoozed.length)
    return I18n.t("notifications.enabled")
  }

  // ------------------------------------------------------------- preferences
  readonly property var availableScreens: Quickshell.screens || []
  readonly property string configuredDisplayMode: preferences.displayMode || "active"
  readonly property string configuredDisplayName: preferences.displayName || ""
  readonly property bool configuredDisplayPresent: {
    if (configuredDisplayName === "") return false
    for (var i = 0; i < availableScreens.length; i++)
      if (availableScreens[i] && String(availableScreens[i].name || "") === configuredDisplayName) return true
    return false
  }
  readonly property string displayChoice: configuredDisplayMode === "specific"
    ? "output:" + configuredDisplayName : configuredDisplayMode
  readonly property var displayOptions: {
    var options = [
      { value: "active", label: I18n.t("notifications.displayActive") },
      { value: "all", label: I18n.t("notifications.displayAll") }
    ]
    for (var i = 0; i < availableScreens.length; i++) {
      var name = String(availableScreens[i].name || "")
      if (name) options.push({ value: "output:" + name, label: name })
    }
    if (configuredDisplayMode === "specific" && !configuredDisplayPresent)
      options.push({ value: displayChoice, label: configuredDisplayName
        ? I18n.t("notifications.displayDisconnected").arg(configuredDisplayName)
        : I18n.t("notifications.displaySelect") })
    return options
  }
  readonly property string displayExplanation: configuredDisplayMode === "all"
    ? I18n.t("notifications.displayAllHint")
    : configuredDisplayMode === "specific" && configuredDisplayPresent
      ? I18n.t("notifications.displaySpecificHint").arg(configuredDisplayName)
      : configuredDisplayMode === "specific"
        ? I18n.t("notifications.displayMissingHint")
        : I18n.t("notifications.displayActiveHint")

  readonly property string configuredFullscreenOverlay: preferences.fullscreenOverlay || "all"
  readonly property var fullscreenOverlayOptions: [
    { value: "off", label: I18n.t("notifications.stepAsideOff") },
    { value: "all", label: I18n.t("notifications.stepAsideAll") },
    { value: "steam", label: I18n.t("notifications.stepAsideSteam") },
    { value: "all-away", label: I18n.t("notifications.stepAsideAllAway") },
    { value: "steam-away", label: I18n.t("notifications.stepAsideSteamAway") }
  ]
  readonly property string fullscreenOverlayExplanation: {
    switch (configuredFullscreenOverlay) {
    case "all": return I18n.t("notifications.stepAsideAllHint")
    case "steam": return I18n.t("notifications.stepAsideSteamHint")
    case "all-away": return I18n.t("notifications.stepAsideAllAwayHint")
    case "steam-away": return I18n.t("notifications.stepAsideSteamAwayHint")
    default: return I18n.t("notifications.stepAsideOffHint")
    }
  }

  function selectDisplay(value) {
    if (!service) return
    if (value === "active" || value === "all") {
      service.setSetting("displayMode", value)
      return
    }
    if (value.indexOf("output:") !== 0) return
    var name = value.slice(7)
    // The output name before the mode, in one write, so selecting a present
    // monitor never passes through specific-without-a-name.
    if (name) service.setSettings({ displayName: name, displayMode: "specific" })
  }

  function snoozeEverything(seconds) {
    if (service) service.snoozeSource(service.globalKey, "", seconds, true)
    globalChoosing = false
  }

  function toggleQuiet() {
    if (!service) return
    if (quiet) service.letEverythingThrough()
    else service.setDoNotDisturb(true)
  }

  // ------------------------------------------------------------- the panel
  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(520))

    content: PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      implicitHeight: column.implicitHeight
      onCloseRequested: controller.hide()
      onMoveRequested: function(dx, dy) {
        if (root.settingsView || dy === 0 || root.sources.length === 0) return
        root.cursorAt = Math.max(0, Math.min(root.sources.length - 1, root.cursorAt + dy))
        root.cursorLive = true
      }
      // Every key acts on the row the cursor is on, and nothing acts without
      // one: an open panel holds the keyboard, and a stray sentence typed at it
      // must not change what gets through.
      onActivateRequested: {
        if (root.settingsView || !root.cursorLive || root.cursorAt >= root.sources.length) return
        var key = root.sources[root.cursorAt].key
        root.expandedKey = root.expandedKey === key ? "" : key
      }
      onDeleteRequested: {
        if (!root.settingsView && root.cursorLive && root.cursorAt < root.sources.length && root.service)
          root.service.unsnooze(root.sources[root.cursorAt].key)
      }

      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { id: panelScrollBar; policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: parent.width
          spacing: Style.space(12)

          // --------------------------------------------------- preferences
          Column {
            visible: root.settingsView
            width: parent.width
            spacing: Style.spacing.huge

            PanelHero {
              width: parent.width
              title: I18n.t("notifications.title")
              meta: I18n.t("notifications.preferences")
              foreground: root.panelFg
              fontFamily: root.fontFamily
              trailingControl: Component {
                PanelActionButton {
                  iconText: "\u{f00d}"
                  tooltipText: I18n.t("notifications.closePreferences")
                  foreground: root.panelFg
                  fontFamily: root.fontFamily
                  onClicked: root.settingsView = false
                }
              }
            }

            Column {
              width: parent.width
              spacing: Style.spacing.lg

              Picker {
                width: parent.width
                label: I18n.t("notifications.display")
                value: root.displayChoice
                options: root.displayOptions
                foreground: root.panelFg
                fontFamily: root.fontFamily
                onPicked: function(value) { root.selectDisplay(value) }
              }

              Hint { text: root.displayExplanation }
            }

            PanelSeparator { foreground: root.panelFg }

            Column {
              width: parent.width
              spacing: Style.spacing.lg

              Picker {
                width: parent.width
                label: I18n.t("notifications.stepAside")
                value: root.configuredFullscreenOverlay
                options: root.fullscreenOverlayOptions
                foreground: root.panelFg
                fontFamily: root.fontFamily
                onPicked: function(value) { if (root.service) root.service.setSetting("fullscreenOverlay", value) }
              }

              Hint { text: root.fullscreenOverlayExplanation }
            }

            PanelSeparator { foreground: root.panelFg }

            SwitchRow {
              label: I18n.t("notifications.groupBySource")
              hint: I18n.t("notifications.groupBySourceHint")
              checked: root.preferences.stacking !== "all"
              onToggled: if (root.service) root.service.setSetting("stacking", root.preferences.stacking === "all" ? "source" : "all")
            }

            SwitchRow {
              label: I18n.t("notifications.showCountdown")
              hint: I18n.t("notifications.showCountdownHint")
              checked: root.preferences.showCountdown === true
              onToggled: if (root.service) root.service.setSetting("showCountdown", !root.preferences.showCountdown)
            }

            SwitchRow {
              label: I18n.t("notifications.suggestSnooze")
              hint: root.service && !root.service.sharingDetectionAvailable
                ? I18n.t("notifications.sharingUnavailable")
                : I18n.t("notifications.suggestSnoozeHint")
              checked: root.preferences.offerSnoozeWhenSharing !== false
              onToggled: if (root.service) root.service.setSetting("offerSnoozeWhenSharing", root.preferences.offerSnoozeWhenSharing === false)
            }

            Hint {
              visible: root.service && (root.service.sandboxStatus.mode === "direct"
                                        || root.service.sandboxStatus.mode === "blocked")
              text: root.service && root.service.sandboxStatus.mode === "blocked"
                ? I18n.t("notifications.sandboxBlocked")
                : I18n.t("notifications.sandboxDirect")
            }
          }

          // --------------------------------------------------- notifications
          PanelHero {
            id: hero
            visible: !root.settingsView
            width: parent.width
            title: I18n.t("notifications.title")
            meta: root.stateLine
            foreground: root.panelFg
            fontFamily: root.fontFamily
            iconOpacity: root.hasState ? 1.0 : 0.5
            // A fixed square: a bell, a crossed-out bell and a sleeping bell
            // are three widths, and the title must not move between them.
            iconComponent: Component {
              Item {
                implicitWidth: hero.iconSize
                implicitHeight: hero.iconSize

                Text {
                  textFormat: Text.PlainText
                  anchors.centerIn: parent
                  text: root.silenced ? root.bellOff
                      : (root.globalSnoozed || root.snoozed.length > 0) ? root.bellSleep
                      : root.bell
                  color: root.silenced ? root.silencedColour
                       : (root.globalSnoozed || root.snoozed.length > 0) ? root.snoozedColour
                       : root.panelFg
                  font.family: root.fontFamily
                  font.pixelSize: hero.iconSize
                }
              }
            }

            trailingControl: Component {
              Row {
                spacing: Style.space(6)

                // Whether quiet has a hole in it for verification codes. Only
                // while there is quiet to qualify, or one is being chosen.
                PanelActionButton {
                  visible: root.hasState || root.globalChoosing
                  anchors.verticalCenter: parent.verticalCenter
                  iconText: root.codesLetThrough ? root.keyGlyph : root.keyOff
                  tooltipText: root.codesLetThrough
                    ? I18n.t("notifications.blockCodes")
                    : I18n.t("notifications.allowCodes")
                  foreground: root.codesLetThrough ? root.panelFg : root.dim
                  fontFamily: root.fontFamily
                  onClicked: if (root.service) root.service.setCodesBypassQuiet(!root.codesLetThrough)
                }

                PanelActionButton {
                  anchors.verticalCenter: parent.verticalCenter
                  iconText: root.globalSnoozed ? root.bell : root.bellSleep
                  tooltipText: root.globalSnoozed ? I18n.t("notifications.endSnooze") : I18n.t("notifications.snoozeAll")
                  foreground: root.globalSnoozed ? root.snoozedColour : root.panelFg
                  fontFamily: root.fontFamily
                  onClicked: {
                    if (root.globalSnoozed) root.service.unsnooze(root.service.globalKey)
                    else root.globalChoosing = !root.globalChoosing
                  }
                }

                PanelActionButton {
                  anchors.verticalCenter: parent.verticalCenter
                  iconText: "\u{f0493}"
                  tooltipText: I18n.t("notifications.settings")
                  foreground: root.panelFg
                  fontFamily: root.fontFamily
                  onClicked: root.settingsView = true
                }

                // On means notifications are coming through.
                ToggleSwitch {
                  anchors.verticalCenter: parent.verticalCenter
                  checked: !root.quiet
                  foreground: root.panelFg
                  onToggled: root.toggleQuiet()
                }
              }
            }
          }

          // A share started: offer a timed snooze, never impose one.
          BorderSurface {
            visible: !root.settingsView && root.sharingOfferPending
            width: parent.width
            implicitHeight: sharingOfferContent.implicitHeight + Style.space(16)
            color: "transparent"
            borderSpec: Border.controlSpec("normal", root.panelFg, Commons.Color.accent)
            radius: Style.cornerRadius

            Column {
              id: sharingOfferContent
              anchors.fill: parent
              anchors.margins: Style.space(8)
              spacing: Style.space(5)

              Text {
                width: parent.width
                text: I18n.t("notifications.sharingDetected")
                textFormat: Text.PlainText
                color: root.panelFg
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                font.bold: true
              }

              Text {
                width: parent.width
                text: I18n.t("notifications.sharingQuestion")
                textFormat: Text.PlainText
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              Flow {
                width: parent.width
                spacing: Style.space(5)

                Repeater {
                  model: root.service && root.sharingOfferPending ? [30, 60, 240] : []

                  ChoiceButton {
                    required property var modelData
                    text: root.service.shortWords(modelData)
                    onClicked: root.service.snoozeSharingOffer(modelData * 60)
                  }
                }

                ChoiceButton {
                  text: I18n.t("notifications.notNow")
                  onClicked: if (root.service) root.service.dismissSharingOffer()
                }
              }
            }
          }

          // The lengths a global snooze can run for, revealed by its button,
          // with the one thing that still gets through.
          Column {
            width: parent.width
            spacing: Style.space(5)
            visible: !root.settingsView && root.globalChoosing && !root.globalSnoozed

            Hint {
              visible: root.codesLetThrough
              text: I18n.t("notifications.codesException")
            }

            Flow {
              width: parent.width
              spacing: Style.space(5)

              Repeater {
                model: root.globalChoosing && root.service ? root.service.snoozeOptions : []

                ChoiceButton {
                  required property var modelData
                  text: String(modelData.short)
                  onClicked: root.snoozeEverything(Number(modelData.seconds))
                }
              }
            }
          }

          // --------------------------------------------------- recent
          PanelSeparator { visible: !root.settingsView && !root.quiet; foreground: root.panelFg }

          SectionToggle {
            visible: !root.settingsView && !root.quiet
            text: I18n.t("notifications.recentHeader").arg(root.recent.length)
            expanded: root.recentExpanded
            showTooltip: I18n.t("notifications.showRecent")
            hideTooltip: I18n.t("notifications.hideRecent")
            onToggled: root.recentExpanded = !root.recentExpanded
          }

          Hint {
            visible: !root.settingsView && !root.quiet && root.recentExpanded && root.recent.length === 0
            text: I18n.t("notifications.noneRecent")
          }

          Column {
            visible: !root.settingsView && !root.quiet && root.recentExpanded
            width: parent.width
            spacing: Style.spacing.md

            Repeater {
              model: !root.settingsView && !root.quiet && root.recentExpanded ? root.recent : []

              EntryCard {
                required property var modelData
                entry: modelData
              }
            }
          }

          // --------------------------------------------------- held back
          PanelSeparator { visible: !root.settingsView; foreground: root.panelFg }

          PanelSectionHeader {
            visible: !root.settingsView
            text: root.quiet ? I18n.t("notifications.heldBack") : I18n.t("notifications.snoozedSources")
            foreground: root.panelFg
            fontFamily: root.fontFamily
          }

          Hint {
            visible: !root.settingsView && root.sources.length === 0
            text: root.quiet ? I18n.t("notifications.noneHeld") : I18n.t("notifications.noneSnoozed")
          }

          Column {
            visible: !root.settingsView
            width: parent.width
            spacing: Style.spacing.sm

            Repeater {
              model: root.sources

              Column {
                id: line
                required property var modelData
                required property int index
                readonly property bool expanded: root.expandedKey === modelData.key
                readonly property bool snoozedByName: modelData.until > 0
                property bool choosing: false
                width: parent.width
                spacing: 0

                CursorSurface {
                  width: parent.width
                  height: Math.max(label.implicitHeight, controls.implicitHeight, Style.spacing.controlHeight)
                  hasCursor: root.cursorLive && root.cursorAt === line.index
                  foreground: root.panelFg

                  Column {
                    id: label
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - controls.width - Style.spacing.xl

                    Text {
                      textFormat: Text.PlainText
                      width: parent.width
                      text: line.modelData.label
                      color: root.panelFg
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.bodySmall
                      elide: Text.ElideRight
                    }

                    // When it comes back, in the snoozed bell's colour, and
                    // what it has held so far.
                    Row {
                      width: parent.width
                      spacing: Style.spacing.sm

                      Text {
                        textFormat: Text.PlainText
                        visible: line.snoozedByName
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.hourglass
                        color: root.snoozedColour
                        font.family: root.fontFamily
                        font.pixelSize: Math.round(Style.font.caption * 0.85)
                      }

                      Text {
                        textFormat: Text.PlainText
                        visible: line.snoozedByName
                        text: root.waitingFor(line.modelData.until)
                        color: root.snoozedColour
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                      }

                      Text {
                        textFormat: Text.PlainText
                        visible: line.snoozedByName && line.modelData.held.length > 0
                        text: "·"
                        color: root.dim
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                      }

                      Text {
                        textFormat: Text.PlainText
                        readonly property int count: line.modelData.held.length
                        visible: count > 0
                        width: Math.min(implicitWidth, Math.max(0, parent.width - x))
                        text: root.heldLabel(count)
                        color: root.dim
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        elide: Text.ElideRight
                      }
                    }
                  }

                  MouseArea {
                    anchors.fill: label
                    enabled: line.modelData.held.length > 0
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onContainsMouseChanged: if (containsMouse) {
                      root.cursorAt = line.index
                      // Hover selects, but only keyboard navigation arms the
                      // state-changing keys on this row.
                      root.cursorLive = false
                    }
                    onClicked: root.expandedKey = line.expanded ? "" : line.modelData.key
                  }

                  Row {
                    id: controls
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Style.spacing.xs

                    Row {
                      spacing: Style.spacing.xs
                      visible: line.choosing

                      Repeater {
                        model: line.choosing && root.service ? root.service.snoozeOptions : []

                        ChoiceButton {
                          required property var modelData
                          text: String(modelData.short)
                          // From now, not on top of what is left.
                          onClicked: {
                            root.service.snoozeSource(line.modelData.key, line.modelData.label,
                                                      Number(modelData.seconds), true)
                            line.choosing = false
                          }
                        }
                      }
                    }

                    PanelActionButton {
                      visible: line.modelData.held.length > 0
                      iconText: line.expanded ? root.chevronUp : root.chevronDown
                      tooltipText: line.expanded ? I18n.t("notifications.hideHeld") : I18n.t("notifications.showHeld")
                      foreground: root.panelFg
                      fontFamily: root.fontFamily
                      onClicked: root.expandedKey = line.expanded ? "" : line.modelData.key
                    }

                    PanelActionButton {
                      iconText: line.choosing ? "\u{f0156}" : "\u{f0150}"
                      tooltipText: line.choosing ? I18n.t("notifications.closeSnoozeOptions")
                                 : (line.snoozedByName ? I18n.t("notifications.extendSnooze") : I18n.t("notifications.snoozeSource"))
                      foreground: root.panelFg
                      fontFamily: root.fontFamily
                      onClicked: line.choosing = !line.choosing
                    }

                    PanelActionButton {
                      visible: line.snoozedByName
                      iconText: root.bell
                      tooltipText: I18n.t("notifications.resumeSource")
                      foreground: root.panelFg
                      fontFamily: root.fontFamily
                      onClicked: root.service.unsnooze(line.modelData.key)
                    }
                  }
                }

                // What it caught while you were not being told: one line each,
                // for recognising what you missed rather than reading it.
                Item {
                  width: parent.width
                  height: line.expanded ? heldList.implicitHeight + Style.spacing.lg : 0
                  visible: height > 0
                  clip: true
                  Behavior on height { NumberAnimation { duration: Style.duration(170); easing.type: Easing.OutCubic } }

                  Column {
                    id: heldList
                    width: parent.width - Style.spacing.xxl
                    x: LayoutMirroring.enabled ? 0 : Style.spacing.xxl
                    y: Style.spacing.sm
                    spacing: Style.spacing.hairline

                    Repeater {
                      model: line.expanded ? line.modelData.held : []

                      Text {
                        textFormat: Text.PlainText
                        required property var modelData
                        width: parent.width
                        text: {
                          var when = root.clockTime(new Date(Number(modelData.ts) * 1000))
                          var head = String(modelData.summary || "")
                          var rest = String(modelData.bodyLine || "")
                          if (head && rest) return when + "  " + head + " · " + rest
                          return when + "  " + (head || rest)
                        }
                        color: root.dim
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        elide: Text.ElideRight
                      }
                    }
                  }
                }
              }
            }
          }

          // --------------------------------------------------- history
          PanelSeparator { visible: !root.settingsView; foreground: root.panelFg }

          SectionToggle {
            visible: !root.settingsView
            text: I18n.t("notifications.historyHeader").arg(root.history.length)
            expanded: root.historyExpanded
            showTooltip: I18n.t("notifications.showHistory")
            hideTooltip: I18n.t("notifications.hideHistory")
            onToggled: root.historyExpanded = !root.historyExpanded
          }

          Hint {
            visible: !root.settingsView && root.historyExpanded && root.history.length === 0
            text: I18n.t("notifications.noneHistory")
          }

          Column {
            visible: !root.settingsView && root.historyExpanded
            width: parent.width
            spacing: Style.spacing.md

            // Collapsed instantiates nothing: a hundred cards is real weight to
            // carry only while this is open.
            Repeater {
              model: !root.settingsView && root.historyExpanded ? root.history : []

              EntryCard {
                required property var modelData
                entry: modelData
                expandable: true
              }
            }
          }

          Button {
            visible: !root.settingsView && (root.quiet || root.snoozed.length > 1)
            width: parent.width
            text: I18n.t("notifications.resumeAll")
            bordered: true
            foreground: root.panelFg
            fontFamily: root.fontFamily
            fontSize: Style.font.caption
            onClicked: {
              if (!root.service) return
              root.service.letEverythingThrough()
              root.service.unsnoozeAll()
            }
          }
        }
      }
    }
  }

  // ------------------------------------------------------------- pieces
  component Hint: Text {
    width: parent ? parent.width : 0
    textFormat: Text.PlainText
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.bodySmall
    wrapMode: Text.WordWrap
  }

  component ChoiceButton: Button {
    bordered: true
    foreground: root.panelFg
    fontFamily: root.fontFamily
    fontSize: Style.font.caption
    verticalPadding: Style.spacing.hairline
  }

  component SwitchRow: Column {
    id: switchRow
    property string label: ""
    property string hint: ""
    property bool checked: false
    signal toggled()
    width: parent ? parent.width : 0
    spacing: Style.spacing.lg

    Row {
      width: parent.width
      spacing: Style.spacing.controlGap

      Text {
        width: parent.width - toggle.width - parent.spacing
        anchors.verticalCenter: parent.verticalCenter
        text: switchRow.label
        textFormat: Text.PlainText
        color: root.panelFg
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        wrapMode: Text.WordWrap
      }

      ToggleSwitch {
        id: toggle
        anchors.verticalCenter: parent.verticalCenter
        checked: switchRow.checked
        foreground: root.panelFg
        onToggled: switchRow.toggled()
      }
    }

    Hint { text: switchRow.hint }
  }

  component SectionToggle: Item {
    id: section
    property string text: ""
    property bool expanded: false
    property string showTooltip: ""
    property string hideTooltip: ""
    signal toggled()
    width: parent ? parent.width : 0
    height: Math.max(heading.implicitHeight, chevron.implicitHeight)

    PanelSectionHeader {
      id: heading
      anchors.left: parent.left
      anchors.right: chevron.left
      anchors.verticalCenter: parent.verticalCenter
      text: section.text
      foreground: root.panelFg
      fontFamily: root.fontFamily
    }

    MouseArea {
      anchors.left: parent.left
      anchors.right: chevron.left
      anchors.top: parent.top
      anchors.bottom: parent.bottom
      cursorShape: Qt.PointingHandCursor
      onClicked: section.toggled()
    }

    PanelActionButton {
      id: chevron
      anchors.right: parent.right
      // The scrollbar owns the right-edge hit area even over this row.
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      iconText: section.expanded ? root.chevronUp : root.chevronDown
      tooltipText: section.expanded ? section.hideTooltip : section.showTooltip
      foreground: root.panelFg
      fontFamily: root.fontFamily
      focusable: true
      onClicked: section.toggled()
    }
  }

  // A notification that already left the screen: where it came from and
  // when, its title, and as much of its message as is wanted.
  component EntryCard: BorderSurface {
    id: entryCard
    property var entry: ({})
    property bool expandable: false
    property bool open: false
    width: parent ? parent.width : 0
    leftPadding: Style.spacing.controlPaddingX
    rightPadding: Style.spacing.controlPaddingX
    topPadding: Style.spacing.md
    bottomPadding: Style.spacing.md
    height: entryText.implicitHeight + contentTopInset + contentBottomInset
    radius: Style.cornerRadius
    color: Style.normalFillFor(root.panelFg, Commons.Color.accent)
    borderSpec: Border.controlSpec("normal", root.panelFg, Commons.Color.accent)

    MouseArea {
      anchors.fill: parent
      enabled: entryCard.expandable
      cursorShape: entryCard.expandable ? Qt.PointingHandCursor : Qt.ArrowCursor
      onClicked: entryCard.open = !entryCard.open
    }

    Column {
      id: entryText
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.leftMargin: entryCard.contentLeftInset
      anchors.rightMargin: entryCard.contentRightInset
      anchors.topMargin: entryCard.contentTopInset
      spacing: Style.spacing.xs

      Text {
        width: parent.width
        text: (entryCard.entry.source || entryCard.entry.app || "") + " · "
              + root.clockTime(new Date(Number(entryCard.entry.ts) * 1000))
        textFormat: Text.PlainText
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
      }

      Text {
        width: parent.width
        text: entryCard.entry.summary || ""
        textFormat: Text.PlainText
        color: root.panelFg
        font.family: "Liberation Sans"
        font.pixelSize: Style.font.title
        font.bold: true
        elide: Text.ElideRight
      }

      Text {
        visible: text !== ""
        width: parent.width
        text: entryCard.entry.bodyLine || ""
        textFormat: Text.PlainText
        color: Qt.darker(root.panelFg, 1.15)
        font.family: "Liberation Sans"
        font.pixelSize: Style.font.title
        wrapMode: Text.WordWrap
        maximumLineCount: entryCard.open ? 2147483647 : 2
        elide: entryCard.open ? Text.ElideNone : Text.ElideRight
      }
    }
  }
}
