import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

// The notification indicator: a crossed-out bell under Do Not Disturb, a
// sleeping bell while everything or some source is snoozed, and a sharing mark
// while a detected screen share is waiting for a snooze decision. Click to
// silence or resume; right-click for the notification panel.
BarIndicator {
  id: root

  readonly property var notificationService: bar?.shell?.firstPartyServiceFor("omarchy.notifications")
  readonly property bool dnd: notificationService ? notificationService.doNotDisturb : false
  // A built-in clone of the indicators widget gets a narrowed service proxy
  // with only the silence switch; everything past it needs the real service.
  readonly property bool fullService: !!notificationService && notificationService.snoozeRevision !== undefined
  readonly property bool snoozed: fullService && notificationService.anySnooze === true
  readonly property bool sharingOffer: fullService && notificationService.sharingOfferPending === true

  readonly property string bellOff: "\u{f009b}"
  readonly property string bellSleep: "\u{f00a0}"
  readonly property string sharingGlyph: "\u{f1483}"

  active: dnd || snoozed || sharingOffer
  activeText: sharingOffer ? sharingGlyph : dnd ? bellOff : bellSleep
  inactiveText: bellOff
  activeTooltipText: sharingOffer ? I18n.t("bar.notificationsSharing")
                   : dnd ? I18n.t("bar.allowNotifications")
                   : I18n.t("bar.notificationsSnoozed")
  inactiveTooltipText: I18n.t("bar.silenceNotifications")

  onPressed: function(button) {
    if (!root.notificationService) return
    if (button === Qt.RightButton || root.sharingOffer) {
      if (root.fullService) root.notificationService.requestPanel("toggle", root.screenName)
    } else if (root.fullService && root.active) {
      root.notificationService.letEverythingThrough()
    } else {
      root.notificationService.setDoNotDisturb(!root.notificationService.doNotDisturb)
    }
  }

  readonly property string screenName: {
    var window = root.QsWindow.window
    return window && window.screen ? String(window.screen.name || "") : ""
  }

  // Clicks, keybindings and IPC all ask the service, which closes the panel
  // wherever it is open, or asks for one on a monitor. The indicator showing
  // in the bar there answers. The panel is built the first time it is wanted
  // on this monitor, and kept from then on.
  Connections {
    target: root.fullService ? root.notificationService : null
    ignoreUnknownSignals: true
    function onPanelRequested(action, screenName) {
      if (!root.belongsInBlock || (screenName && root.screenName && root.screenName !== screenName)) return
      if (!panelLoader.item) {
        panelLoader.setSource(root.notificationService.panelUrl,
                              { anchorItem: root, bar: root.bar, service: root.notificationService })
      }
      var panel = panelLoader.item
      if (!panel) return
      if (action === "settings") panel.openSettings()
      else panel.open()
    }
  }

  Loader { id: panelLoader }
}
