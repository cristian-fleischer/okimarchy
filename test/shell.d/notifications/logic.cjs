const assert=require('node:assert/strict'), fs=require('node:fs'), load=require('./loader.cjs');
const S=load('Security'), M=load('Markup'), D=load('Detect'), Store=load('Store');
const bad=['https://paypal.com@evil.example','https://user:pass@example.com','javascript:alert(1)','file:///etc/passwd','smb://server/share','data:text/html,test','https://example.com/\n','https://example.com/%0d%0a','https://example.com/%250a','https://example.com%40evil.example','https://[::1]','https://127.1','https://éxample.com','https://example..com','https://example.com:99999','https://example.com\\@evil.example','https://example.com/'+ 'x'.repeat(4096)];
for (const u of bad) {
 assert.equal(S.safeExternalUrl(u),'',u);
 assert.equal(M.linkable(u),false,u);
 assert.equal(S.openExternalUrl(u),false,u);
 assert.ok(!M.render('<a href="'+u+'">click</a>').includes('<a href='),u);
 for (const detected of D.links(u)) assert.ok(S.safeHttpUrl(detected));
}
for (const u of ['https://example.com','http://example.com/path?q=1','https://xn--bcher-kva.example','https://example.com/a%40b','mailto:user@example.com']) assert.ok(S.safeExternalUrl(u),u);
assert.equal(S.safeHttpUrl('HTTPS://Example.COM.:443/a'),'https://example.com:443/a');
assert.equal(S.safeMailtoUrl('mailto:user@example.com?attach=/etc/passwd'),'');
for(const payload of ['<img src="file:///etc/passwd">','<svg><image href="https://example.com"/></svg>','<script>alert(1)</script>','<iframe src="x">','https://example.com/"onmouseover="x']) {
 const rendered=M.render(payload);
 assert.ok(!/<(?:img|svg|script|iframe|object|embed|style)\b/i.test(rendered),rendered);
 assert.ok(!/<a[^>]+onmouseover=/i.test(rendered),rendered);
}
{ // Escaped sender markup must not leak into collapsed or restored previews.
 const body='Thread in #support: &lt;b&gt;Sam&lt;/b&gt;&lt;br/&gt;the preview is readable &amp; compact';
 const expected='Thread in #support: Sam the preview is readable & compact';
 const row=Store.snapshot({appName:'Slack',summary:'Slack',body},'markup',{Normal:1});
 assert.equal(row.bodyLine,expected);
 const nested=body.replace(/&/g,'&amp;');
 assert.equal(Store.restored({key:'markup',body:nested,bodyLine:'stale preview'}).bodyLine,expected);
 const literals='List&lt;String&gt;: Sam &lt;sam@example.com&gt; asks if 3 &lt; 5\n&amp; 5 &gt; 2; &lt;3';
 const literalLine='List<String>: Sam <sam@example.com> asks if 3 < 5 & 5 > 2; <3';
 assert.equal(Store.snapshot({body:literals},'literal',{Normal:1}).bodyLine,literalLine);
 assert.equal(Store.restored({key:'literal',body:literals,bodyLine:'stale preview'}).bodyLine,literalLine);
 assert.equal(M.oneLine('<b>Sam</b><br/><a href="https://example.com">read &lt;details&gt;</a>'),
              'Sam read <details>');
 assert.equal(M.oneLine('&lt;img src="file:///etc/passwd"&gt; &lt;b class="literal"&gt;'),
              '<img src="file:///etc/passwd"> <b class="literal">');
 // Reverse only our own escaping; do not add a fourth sender-decoding pass.
 assert.equal(M.oneLine('&amp;amp;amp;lt;b&amp;amp;amp;gt;'), '&lt;b&gt;');
}
for (const body of ['Your verification code is 938271','Your code is 938 271','Your code is 938-271','Your code is &#57;38271','Your code is A9F3K2']) {
 const row=Store.snapshot({appName:'Test',summary:'Verification',body},'test', {Normal:1});
 const saved=Store.sanitiseForPersistence(row);
 for(const secret of ['938271','938 271','938-271','A9F3K2']) assert.ok(!JSON.stringify(saved).includes(secret));
}
{ // Literal attributes must not move legacy/raw-only codes outside the scan window.
 const body='Your code is <span title="'+'x'.repeat(100)+'">938271</span>';
 for (const entry of [{body}, {rawBody:body.replace(/</g,'&lt;').replace(/>/g,'&gt;')}]) {
  const saved=Store.sanitiseForPersistence(entry);
  assert.equal(saved.body,'[redacted]');
  assert.ok(!JSON.stringify(saved).includes('938271'));
 }
}
assert.equal(Store.snapshot({body:'x'.repeat(100000),summary:'y'.repeat(3000)},'test',{Normal:1}).body.length,32768);
assert.equal(Store.normalise({image:'file:///etc/passwd',stored_image:'/etc/passwd'}).image,'');
assert.equal(Store.normalise({body:'hello',bodyRich:'<img src="x">'}).bodyRich,'hello');
const start=Date.now();
for (const text of ['<'.repeat(32768),'&amp;'.repeat(6500),'9'.repeat(32768), 'https://'.repeat(4000)]) { M.render(text); D.scan('',text); }
assert.ok(Date.now()-start < 3000,'parsers exceeded 3-second budget');
// Deterministic generated corpus, never personal notifications.
let seed=17;
for(let i=0;i<1000;i++) {
 let s=''; for(let j=0;j<80;j++){seed=(seed*1664525+1013904223)>>>0;s+=String.fromCharCode(seed%128);}
 const u=S.safeExternalUrl(s); if(u) assert.equal(S.safeExternalUrl(u),u);
 assert.ok(!/<(?:img|script|iframe|object|svg)\b/i.test(M.render(s)));
}
for (const u of JSON.parse(fs.readFileSync(__dirname+'/../fixtures/notifications/urls.json'))) assert.equal(S.safeExternalUrl(u),'');
for (const text of JSON.parse(fs.readFileSync(__dirname+'/../fixtures/notifications/markup.json'))) assert.ok(!/<(?:img|svg|script|iframe|object)\b/i.test(M.render(text)));
for (const text of JSON.parse(fs.readFileSync(__dirname+'/../fixtures/notifications/codes.json'))) {
 const row=Store.snapshot({summary:'Verification',body:text},'fixture',{Normal:1});
 assert.equal(Store.sanitiseForPersistence(row).body,'[redacted]');
}
for (const row of JSON.parse(fs.readFileSync(__dirname+'/../fixtures/notifications/notifications.json'))) assert.equal(Store.snapshot(row,'fixture',{Normal:1}).summary,'Synthetic');
// Execute the production focus function: hostile compositor metadata must not
// become Lua syntax. The only dispatchable value is a validated hex address.
const vm=require('node:vm'), source=fs.readFileSync(load.dir+'/Service.qml','utf8');
const focus=source.match(/function focusWindow\(win\) \{[\s\S]*?\n  \}/)[0];
const calls=[], scope={Hyprland:{dispatch:x=>calls.push(x)}};
vm.createContext(scope);vm.runInContext(focus,scope);
scope.focusWindow({wmClass:'x\\"}); os.execute("bad") --'});
scope.focusWindow({address:'0x123);bad()',wmClass:'x'});
assert.equal(calls.length,0);
scope.focusWindow({address:'0x123abc'});assert.equal(calls.length,1);
assert.equal(calls[0],'hl.dsp.focus({window = hl.get_window("address:0x123abc")})');

// Execute the production admission/close/replay functions and Store transforms.
// Only the ListModel, QObject signals, deferred event loop and external effects
// are faked: assertions observe cards, sender lifetime and reusable capacity.
function extract(src, startMarker, endMarker) {
  const s = src.indexOf(startMarker);
  if (s < 0) throw new Error('start marker not found: ' + startMarker);
  const e = src.indexOf(endMarker, s + startMarker.length);
  if (e < 0) throw new Error('end marker not found: ' + endMarker);
  return src.slice(s, e);
}
const capacitySource = [
  extract(source, 'function pinDeckDisplay()', '\n  // A verification code'),
  extract(source, 'function fullscreenOn(name)', '\n  Connections {'),
  extract(source, 'function rememberRecent(row)', '// ------------------------------------------------------- what was held'),
  extract(source, 'function durationFor(urgency, requested)', '// ------------------------------------------------------------- snooze'),
  extract(source, 'function liveCount()', '// ------------------------------------------------------------- icons'),
  extract(source, 'function wantSenderImage(row)', '\n  Process {'),
  extract(source, 'function nextKey()', '// ------------------------------------------------------------- arrival'),
  extract(source, 'function handleNotification(notification)', '// Qt.callLater: mutating the model'),
  extract(source, 'function showRow(row)', "// Let go of the sender's object"),
  extract(source, 'function release(key, reason)', '// ------------------------------------------------------------- departure'),
  extract(source, 'function closeToast(key, reason)', '// What the sender said can be done'),
  extract(source, 'function releaseHeld()', '// Nothing waits forever'),
  extract(source, 'function restoreRows(rows, replay)', '\n  Process {'),
  extract(source, 'function actionsOf(key, revision)', 'function invokeAction(key, identifier)'),
].join('\n');

function newCapacityScope() {
  const toasts = { rows: [],
    get count() { return this.rows.length; },
    get(i) { return this.rows[i]; },
    insert(i, row) { this.rows.splice(i, 0, { ...row }); },
    setProperty(i, role, value) { this.rows[i][role] = value; },
    remove(i) { this.rows.splice(i, 1); } };
  const later = [];
  const s = {
    toasts, refs: {}, refsRevision: 0, keySeed: 0, liveKeys: Object.create(null),
    maxLiveNotifications: 100, heights: {}, leaving: {}, layoutRevision: 0,
    replyingKey: '', held: [], doNotDisturb: false, globalSnoozeUntil: 0,
    recentRows: [], recentLimit: 20,
    senderImageQueue: [], senderImageRevision: 0, helperSettingsReady: false,
    configuredDisplayName: 'fixture-display', deckDisplayName: '',
    fullscreenAway: false, fullscreenScope: '', hyprRevision: 0,
    displayNames: ['fixture-display'], focusedDisplayName: 'fixture-display',
    Quickshell: { screens: [] }, Hyprland: { monitorFor: screen => screen.monitor },
    snoozeRevision: 0, snoozes: {},
    codesBypassQuiet: false, hideSettingsAction: false,
    lowDuration: 5000, normalDuration: 8000, maxDuration: 30000,
    snoozedUntil: key => s.snoozes[key] || 0,
    liveSnoozes: () => Object.keys(s.snoozes).map(key => ({ key })),
    storeProc: {}, storeBin: '', wantIcon: () => {},
    lookForReply: () => {}, Security: S, Delivery: load('Delivery'),
    Store: { ...Store, write: () => {} },
    NotificationUrgency: { Critical: 2, Normal: 1, Low: 0 },
    Qt: { callLater: fn => later.push(fn),
      md5: value => require('node:crypto').createHash('md5').update(value).digest('hex') },
    Style: { space: n => n },
    holding: () => s.pointerHolding === true,
    snapshot: () => ({}), deckHeight: 0, retarget: () => {}, layout: { placements: {} },
  };
  // Bare QML properties and service-qualified accesses are the same object.
  s.service = s;
  vm.createContext(s);
  vm.runInContext(capacitySource, s);
  s.drainCallLater = () => { while (later.length) later.shift()(); };
  s.fakeNotification = (id = 0, summary = 'Synthetic', urgency = 1) => {
    let tracked = false, destroyed = false;
    const signal = () => {
      const listeners = [];
      return { connect: fn => listeners.push(fn), emit: () => listeners.slice().forEach(fn => fn()) };
    };
    const close = reason => {
      n.closeAttempts++;
      if (destroyed) { n.destroyedCloseAttempts++; return; }
      destroyed = true;
      tracked = false;
      if (reason === 'expired') n.expiries++;
      else n.dismissals++;
      n.closed.emit();
    };
    const n = { id, summary, body: 'Synthetic body: ' + summary, urgency, appName: 'Fixture',
      actions: [{ identifier: 'open', text: summary }], dismissals: 0, expiries: 0,
      closeAttempts: 0, destroyedCloseAttempts: 0, closed: signal(),
      get tracked() { return tracked; },
      set tracked(value) { if (value) tracked = true; else close('dismissed'); },
      dismiss() { close('dismissed'); },
      expire() { close('expired'); },
      replace(properties) {
        // NotificationServer::Notify mutates the same QObject in a property
        // update group. It does NOT emit a new server notification event.
        const changed = Object.keys(properties).filter(field => n[field] !== properties[field]);
        Object.assign(n, properties);
        for (const field of changed) n[field + 'Changed'].emit();
      },
    };
    for (const field of ['summary', 'body', 'appName', 'appIcon', 'image', 'urgency', 'expireTimeout', 'hints', 'actions'])
      n[field + 'Changed'] = signal();
    return n;
  };
  return s;
}

{ // Route away from fullscreen outputs, but not merely maximised windows.
  const s = newCapacityScope();
  const game = { lastIpcObject: { fullscreen: 1, class: 'steam_app_31' } };
  const work = { lastIpcObject: { fullscreen: 0, class: 'editor' } };
  s.displayNames = ['game', 'work'];
  s.focusedDisplayName = 'game';
  s.Quickshell.screens = [game, work].map((window, i) => ({
    name: s.displayNames[i],
    monitor: { activeWorkspace: { hasFullscreen: true, toplevels: { values: [window] } } },
  }));
  s.fullscreenAway = true;
  s.fullscreenScope = 'all';
  assert.equal(s.routeAround('game'), 'game');
  game.lastIpcObject.fullscreen = 2;
  assert.equal(s.routeAround('game'), 'work');
  work.lastIpcObject.fullscreen = 2;
  assert.equal(s.routeAround('game'), '');
  s.fullscreenScope = 'steam';
  assert.equal(s.routeAround('game'), 'work');
  s.fullscreenAway = false;
  assert.equal(s.routeAround('game'), 'game');
}

{ // Rapid single dismissals must skip rows still playing their exit animation.
  const s = newCapacityScope();
  vm.runInContext(extract(source, 'function dismissOne(): string', 'function invokeLast()')
    .replace(/\(\): string/g, '()'), s);
  assert.equal(s.dismissOne(), 'none');
  const senders = [1, 2, 3, 4].map(id => s.fakeNotification(id));
  for (const sender of senders) s.handleNotification(sender);
  s.drainCallLater();
  const keys = s.toasts.rows.map(row => row.key);
  s.closeToast(keys[0], 'expired');
  for (const key of keys.slice(1)) {
    assert.equal(s.dismissOne(), 'ok');
    assert.equal(s.leaving[key], 'dismissed', 'each press selects the next live card');
  }
  assert.equal(s.dismissOne(), 'none', 'departing cards are not dismissible');
  assert.equal(s.toasts.count, 4, 'exit animations retain their model rows');
  assert.equal(s.leaving[keys[0]], 'expired', 'dismissal preserves an earlier expiry');
  for (const key of keys) s.finishClose(key, s.leaving[key]);
  assert.equal(s.toasts.count, 0);
  assert.equal(senders[3].expiries, 1);
  for (const sender of senders.slice(0, 3)) assert.equal(sender.dismissals, 1);
  for (const sender of senders) assert.equal(sender.closeAttempts, 1);
}

{ // Dismiss the visible deck, including across mode changes and exit animations.
  const Layout = load('Layout');
  function fixture(stacking, expanded, openDeck) {
    const s = newCapacityScope();
    Object.assign(s, { Layout, stacking, expanded, openDeck });
    for (const [key, groupKey] of [['old', 'chat'], ['build', 'build'], ['new', 'chat']]) {
      s.reserveLive(key);
      s.toasts.insert(0, { key, groupKey });
    }
    Object.defineProperty(s, 'layout', { get: () => Layout.compute(
      s.toasts.rows.filter(row => !s.leaving[row.key]),
      { stacking: s.stacking, expanded: s.expanded, openDeck: s.openDeck }) });
    return s;
  }
  const collapsed = fixture('source', false, '');
  assert.equal(collapsed.clearDeck('dismissed'), 2);
  assert.deepEqual(Object.keys(collapsed.leaving).sort(), ['new', 'old']);
  // Departing rows remain in the model, but must not consume the next press.
  assert.equal(collapsed.clearDeck('dismissed'), 1);
  assert.deepEqual(Object.keys(collapsed.leaving).sort(), ['build', 'new', 'old']);
  assert.equal(collapsed.clearDeck('dismissed'), 0);
  const open = fixture('source', true, 'build');
  assert.equal(open.clearDeck('dismissed'), 1);
  assert.deepEqual(Object.keys(open.leaving), ['build']);
  assert.equal(open.clearDeck('dismissed'), 2);
  const all = fixture('all', true, 'chat');
  assert.equal(all.clearDeck('dismissed'), 3);
  assert.deepEqual(Object.keys(all.leaving).sort(), ['build', 'new', 'old']);
  const source = fixture('source', true, 'all');
  assert.equal(source.clearDeck('dismissed'), 2);
  assert.deepEqual(Object.keys(source.leaving).sort(), ['new', 'old']);
  const empty = fixture('source', false, '');
  empty.toasts.rows = [];
  assert.equal(empty.clearDeck('dismissed'), 0);
}

{ // A late decode cannot overwrite a replacement, even if it reuses the path.
  const s = newCapacityScope();
  const n = s.fakeNotification(1, 'First icon');
  n.image = 'image://icon//tmp/site-icon.png';
  s.handleNotification(n);
  s.drainCallLater();
  const key = s.keyForOriginal(1), first = s.liveKeys[key].senderImage;
  const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB';
  n.replace({ summary: 'Replacement icon' });
  s.drainCallLater();
  const replacement = s.liveKeys[key].senderImage;
  s.finishSenderImage(first, png);
  assert.equal(s.senderImageFor(key, n.image), '');
  s.finishSenderImage(replacement, png);
  assert.equal(s.senderImageFor(key, n.image), png);
  n.replace({ image: '' });
  s.drainCallLater();
  assert.equal(s.senderImageFor(key, ''), '');
  s.finishClose(key, 'dismissed');
  s.finishSenderImage(replacement, png);
  assert.equal(s.senderImageFor(key, n.image), '');
}

{ // Expired notifications remain readable, newest first, without unbounded retention.
  const s = newCapacityScope();
  for (let i = 1; i <= 25; i++) {
    const n = s.fakeNotification(i, 'Message ' + i);
    s.handleNotification(n);
    s.drainCallLater();
    s.finishClose(s.keyForOriginal(i), 'expired');
  }
  assert.equal(s.toasts.count, 0);
  assert.deepEqual(Array.from(s.recentRows, row => row.summary),
    Array.from({ length: 20 }, (_, i) => 'Message ' + (25 - i)));
}

{ // Replacing a live sender updates one recent entry and moves it to the front.
  const s = newCapacityScope();
  const first = s.fakeNotification(1, 'First');
  s.handleNotification(first);
  s.handleNotification(s.fakeNotification(2, 'Second'));
  s.drainCallLater();
  first.replace({ summary: 'First updated', body: 'Latest text' });
  s.drainCallLater();
  assert.deepEqual(Array.from(s.recentRows, row => row.summary), ['First updated', 'Second']);
  assert.equal(s.recentRows[0].bodyLine, 'Latest text');
}

{ // A code must not outlive its toast, even in source metadata used for filtering.
  const s = newCapacityScope();
  const code = s.fakeNotification(1, 'Your verification code is 938271');
  code.appName = 'Source 938271';
  s.handleNotification(code);
  s.drainCallLater();
  const key = s.keyForOriginal(1), group = s.toasts.get(0).groupKey;
  s.finishClose(key, 'expired');
  assert.equal(s.recentForPanel(5)[0].bodyLine, '[redacted]');
  assert.ok(!JSON.stringify(s.recentRows).includes('938271'));
  s.snoozes[group] = 1;
  assert.equal(s.recentForPanel(5).length, 0);
}

{ // Full quiet hides the entire recent list and held arrivals never backfill it.
  const s = newCapacityScope();
  s.handleNotification(s.fakeNotification(1, 'Before quiet'));
  s.drainCallLater();
  s.doNotDisturb = true;
  s.handleNotification(s.fakeNotification(2, 'Silenced arrival'));
  assert.equal(s.recentForPanel(5).length, 0);
  s.doNotDisturb = false;
  s.globalSnoozeUntil = 1;
  s.handleNotification(s.fakeNotification(3, 'Global snooze arrival'));
  assert.equal(s.recentForPanel(5).length, 0);
  s.globalSnoozeUntil = 0;
  assert.deepEqual(Array.from(s.recentForPanel(5), row => row.summary), ['Before quiet']);
}

{ // Filter before applying N, preserving other sources and restoring earlier rows on wake.
  const s = newCapacityScope();
  s.handleNotification(s.fakeNotification(1, 'Other source'));
  const snoozed = s.fakeNotification(2, 'Soon snoozed');
  snoozed.appName = 'Noisy';
  s.handleNotification(snoozed);
  s.drainCallLater();
  const group = s.toasts.get(0).groupKey;
  s.snoozes[group] = 1;
  assert.deepEqual(Array.from(s.recentForPanel(1), row => row.summary), ['Other source']);
  const held = s.fakeNotification(3, 'Held arrival');
  held.appName = 'Noisy';
  s.handleNotification(held);
  delete s.snoozes[group];
  assert.deepEqual(Array.from(s.recentForPanel(5), row => row.summary), ['Soon snoozed', 'Other source']);
  s.snoozes[group] = 1;
  snoozed.replace({ summary: 'Updated while snoozed' });
  s.drainCallLater();
  delete s.snoozes[group];
  assert.deepEqual(Array.from(s.recentForPanel(5), row => row.summary), ['Other source']);
}

for (const held of [true, false]) {
  const s = newCapacityScope();
  s.pointerHolding = held;
  const arrivals = Array.from({ length: 150 }, (_, i) => s.fakeNotification(i + 1));
  arrivals.forEach(n => s.handleNotification(n));
  assert.equal(s.toasts.count, 0, 'held/deferred arrivals have not entered the model');
  assert.equal(arrivals.filter(n => n.tracked).length, 100);
  assert.equal(s.liveCount(), 100);
  if (held) assert.equal(s.held.length, 100);

  const updated = arrivals[0];
  for (const summary of ['First replacement', 'Second replacement', 'Latest replacement']) {
    updated.replace({ summary, body: 'Synthetic body: ' + summary,
      actions: [{ identifier: 'open', text: summary }] });
    assert.equal(updated.tracked, true, 'pending replacement stays accepted at capacity');
    assert.equal(s.liveCount(), 100);
    if (held) assert.equal(s.held.length, 100, 'replacement does not queue a second card');
  }
  s.pointerHolding = false;
  s.releaseHeld();
  s.drainCallLater();
  assert.equal(s.toasts.count, 100);
  const replacements = s.toasts.rows.filter(row => row.originalId === 1);
  assert.equal(replacements.length, 1);
  assert.equal(replacements[0].summary, 'Latest replacement');
  assert.equal(replacements[0].body, 'Synthetic body: Latest replacement');
}

{ // Visible replacements keep their position and expose only the latest sender's actions.
  const s = newCapacityScope();
  const original = s.fakeNotification(1, 'Original');
  s.handleNotification(original);
  for (let i = 2; i <= 100; i++) s.handleNotification(s.fakeNotification(i));
  s.drainCallLater();
  const key = s.keyForOriginal(1), index = s.rowIndexFor(key);
  s.pointerHolding = true;
  const updated = original;
  updated.replace({ summary: 'Updated', actions: [{ identifier: 'open', text: 'Updated' }] });
  updated.replace({ summary: 'Same object latest', body: 'Latest body', expireTimeout: 12345 });
  s.drainCallLater();
  assert.equal(s.rowIndexFor(key), index);
  assert.equal(s.toasts.get(index).summary, 'Same object latest');
  assert.equal(s.toasts.get(index).body, 'Latest body');
  assert.equal(s.toasts.get(index).duration, 12345);
  assert.equal(s.actionsOf(key)[0].text, 'Updated');
  assert.equal(s.held.length, 0);
  assert.equal(s.toasts.count, 100);
  const rejected = s.fakeNotification(1001);
  s.handleNotification(rejected);
  assert.equal(rejected.tracked, false);
  updated.replace({ summary: 'Cancelled visible update' });
  s.closeToast(key, 'expired');
  assert.equal(s.liveCount(), 100, 'a leaving visible row retains its reservation');
  s.finishClose(key, 'expired');
  s.finishClose(key, 'expired');
  s.drainCallLater();
  assert.equal(s.toasts.count, 99, 'a pending visible update cannot resurrect a closed card');
  assert.equal(updated.expiries, 1);
  assert.equal(updated.closeAttempts, 1, 'expire must not be followed by a second close via tracked=false');
  assert.equal(updated.destroyedCloseAttempts, 0);
  assert.equal(updated.tracked, false);
  assert.equal(s.actionsOf(key).length, 0);
  assert.equal(s.liveCount(), 99);
}

for (const held of [true, false]) {
  const s = newCapacityScope();
  s.pointerHolding = held;
  const dropped = s.fakeNotification(1, 'Cancelled');
  s.handleNotification(dropped);
  for (let i = 2; i <= 100; i++) s.handleNotification(s.fakeNotification(i));
  dropped.replace({ summary: 'Cancelled pending update' });
  const key = s.keyForOriginal(1);
  s.closeToast(key, 'dismissed');
  s.closeToast(key, 'dismissed');
  assert.equal(dropped.dismissals, 1);
  assert.equal(dropped.closeAttempts, 1, 'dismiss must not be followed by tracked=false');
  assert.equal(dropped.destroyedCloseAttempts, 0);
  assert.equal(dropped.tracked, false);
  assert.equal(s.liveCount(), 99);
  const replacement = s.fakeNotification(1, 'Reused sender ID');
  s.handleNotification(replacement);
  assert.equal(replacement.tracked, true);
  dropped.closed.emit();
  const rejected = s.fakeNotification(1001);
  s.handleNotification(rejected);
  assert.equal(rejected.tracked, false, 'cancellation frees exactly one slot');
  s.pointerHolding = false;
  s.releaseHeld();
  s.drainCallLater();
  assert.equal(s.toasts.count, 100);
  assert.equal(s.toasts.rows.filter(r => r.summary === 'Cancelled').length, 0);
  assert.equal(s.toasts.rows.filter(r => r.summary === 'Reused sender ID').length, 1);
}

{ // A callback queued before the pointer arrived must not insert or overwrite the held update.
  const s = newCapacityScope();
  const pending = s.fakeNotification(1, 'Deferred');
  s.handleNotification(pending);
  s.pointerHolding = true;
  pending.replace({ summary: 'Held update' });
  s.drainCallLater();
  assert.equal(s.toasts.count, 0);
  s.pointerHolding = false;
  s.releaseHeld();
  pending.replace({ summary: 'Update after release' });
  s.drainCallLater();
  assert.equal(s.toasts.count, 1);
  assert.equal(s.toasts.get(0).summary, 'Update after release');
}

{ // Sender withdrawal cancels pending cards but leaves an already visible snapshot intact.
  const s = newCapacityScope();
  const withdrawn = s.fakeNotification(1, 'Withdrawn');
  s.handleNotification(withdrawn);
  withdrawn.replace({ summary: 'Withdrawn pending update' });
  withdrawn.tracked = false;
  s.drainCallLater();
  assert.equal(s.liveCount(), 0);
  assert.equal(s.toasts.count, 0);
  const visible = s.fakeNotification(2, 'Visible');
  s.handleNotification(visible);
  s.drainCallLater();
  const key = s.keyForOriginal(2);
  visible.tracked = false;
  assert.equal(s.toasts.get(0).summary, 'Visible');
  assert.equal(s.actionsOf(key).length, 0);
  assert.equal(s.liveCount(), 1);
  s.finishClose(key, 'dismissed');
  assert.equal(s.liveCount(), 0);
}

for (const quiet of ['silenced', 'snoozed']) {
  const s = newCapacityScope();
  s.pointerHolding = quiet === 'snoozed';
  const muted = s.fakeNotification(1, 'Before quiet');
  s.handleNotification(muted);
  if (quiet === 'silenced') s.doNotDisturb = true;
  else s.snoozedUntil = () => 12345;
  muted.replace({ summary: 'Quiet update' });
  s.releaseHeld();
  s.drainCallLater();
  assert.equal(muted.tracked, false);
  assert.equal(s.liveCount(), 0);
  assert.equal(muted.closeAttempts, 1);
  assert.equal(s.toasts.count, 0);
  // Critical alone does not punch through: chat apps send critical to force
  // visibility. A bare notify-send alert and Omarchy's own toasts do.
  const branded = s.fakeNotification(2, 'Branded critical', 2);
  s.handleNotification(branded);
  s.releaseHeld();
  s.drainCallLater();
  assert.equal(s.toasts.count, 0);
  const critical = s.fakeNotification(3, 'Critical', 2);
  critical.appName = 'notify-send';
  s.handleNotification(critical);
  s.releaseHeld();
  s.drainCallLater();
  assert.equal(s.toasts.get(0).summary, 'Critical');
  const action = s.fakeNotification(4, 'Theme changed', 0);
  action.appName = 'omarchy-action';
  s.handleNotification(action);
  s.releaseHeld();
  s.drainCallLater();
  assert.equal(s.toasts.get(0).summary, 'Theme changed');
}

{ // A muted visible replacement keeps the old card, not a previously queued update.
  const s = newCapacityScope();
  const visible = s.fakeNotification(1, 'Visible original');
  s.handleNotification(visible);
  s.drainCallLater();
  visible.replace({ summary: 'Pending update' });
  s.doNotDisturb = true;
  visible.replace({ summary: 'Muted update' });
  s.drainCallLater();
  assert.equal(s.toasts.get(0).summary, 'Visible original');
  assert.equal(s.liveCount(), 1);
  assert.equal(s.actionsOf(s.keyForOriginal(1)).length, 0);
}

{ // Non-text updates also refresh the snapshot: priority can remove expiry,
  // and a changed sender-pid hint must reach the routing row without new text.
  const s = newCapacityScope();
  const n = s.fakeNotification(1, 'Unchanged text');
  s.handleNotification(n);
  s.drainCallLater();
  n.replace({ urgency: 2 });
  s.drainCallLater();
  assert.equal(s.toasts.get(0).urgency, 2);
  assert.equal(s.toasts.get(0).duration, 0);
  n.replace({ hints: { 'sender-pid': 1234 } });
  s.drainCallLater();
  assert.equal(s.toasts.get(0).senderPid, 1234);
  assert.equal(s.toasts.count, 1);
}

const storedRows = count => Array.from({ length: count }, (_, i) => ({ key: 'stored-' + i, summary: 'Stored ' + i }));
for (const replay of [false, true]) {
  const s = newCapacityScope();
  s.pointerHolding = true;
  for (let i = 1; i <= 98; i++) s.handleNotification(s.fakeNotification(i));
  s.restoreRows(storedRows(4), replay);
  assert.equal(s.liveCount(), 100, 'replay and startup restore share held reservations');
  s.restoreRows([{ key: 'overflow', summary: 'Overflow' }], !replay);
  s.drainCallLater();
  assert.equal(s.toasts.count, 2);
  const key = s.toasts.get(0).key;
  s.finishClose(key, 'dismissed');
  s.restoreRows([{ key: 'reused-slot', summary: 'Slot reused' }], !replay);
  s.pointerHolding = false;
  s.releaseHeld();
  s.drainCallLater();
  assert.equal(s.toasts.count, 100);
  assert.equal(s.toasts.rows.filter(r => r.summary === 'Slot reused').length, 1);
  assert.equal(s.toasts.rows.filter(r => r.summary === 'Overflow').length, 0);
  assert.equal(new Set(s.toasts.rows.map(r => r.key)).size, 100);
}

{ // Startup itself is bounded, including a replay before its deferred insertions drain.
  const s = newCapacityScope();
  s.restoreRows(storedRows(150), false);
  s.restoreRows([{ key: 'history-a' }, { key: 'history-b' }], true);
  s.drainCallLater();
  assert.equal(s.toasts.count, 100);
  assert.equal(s.liveCount(), 100);
  assert.equal(s.toasts.get(0).summary, 'Stored 99', 'startup order remains newest first');
  s.clearAll('dismissed');
  for (const row of [...s.toasts.rows]) s.finishClose(row.key, 'dismissed');
  s.restoreRows([{ key: 'history-a' }, { key: 'history-b' }], true);
  s.drainCallLater();
  assert.equal(s.toasts.count, 2);
}

{ // Repeated replay creates distinct cards; restore cannot overwrite an admitted key.
  const s = newCapacityScope();
  s.restoreRows([{ key: 'same', summary: 'Original' }], true);
  s.restoreRows([{ key: 'same', summary: 'Replay' }], true);
  s.restoreRows([{ key: 'same', summary: 'Stale startup' }], false);
  s.drainCallLater();
  assert.equal(s.toasts.count, 2);
  assert.equal(new Set(s.toasts.rows.map(r => r.key)).size, 2);
  assert.equal(s.toasts.get(0).summary, 'Replay');
  assert.equal(s.toasts.get(1).summary, 'Original');
}

{ // Clearing pending rows cancels their callbacks even if replay reuses the exact key.
  const s = newCapacityScope();
  s.restoreRows([{ key: 'same', summary: 'Cancelled replay' }], true);
  s.pointerHolding = true;
  const held = s.fakeNotification(1, 'Cancelled held');
  s.handleNotification(held);
  s.clearAll('cleared');
  assert.equal(s.liveCount(), 0);
  assert.equal(held.tracked, false);
  s.restoreRows([{ key: 'same', summary: 'Latest replay' }], true);
  s.releaseHeld();
  s.drainCallLater();
  assert.equal(s.toasts.count, 1);
  assert.equal(s.toasts.get(0).summary, 'Latest replay');
  assert.equal(s.liveCount(), 1);
}

{ // A restarted server may allocate an ID that persisted rows carried last session.
  const s = newCapacityScope();
  s.restoreRows([{ key: 'previous-session', originalId: 1, summary: 'Previous session' }], false);
  s.drainCallLater();
  s.handleNotification(s.fakeNotification(1, 'New session'));
  s.drainCallLater();
  assert.equal(s.toasts.count, 2);
  assert.deepEqual(s.toasts.rows.map(row => row.summary), ['New session', 'Previous session']);
}

{ // ID zero never replaces a pending notification or a restored card.
  const s = newCapacityScope();
  s.restoreRows([{ key: 'restored-zero', summary: 'Restored zero' }], false);
  s.handleNotification(s.fakeNotification(0, 'First zero'));
  s.handleNotification(s.fakeNotification(0, 'Second zero'));
  s.drainCallLater();
  assert.equal(s.toasts.count, 3);
  assert.equal(new Set(s.toasts.rows.map(r => r.key)).size, 3);
  assert.equal(s.liveCount(), 3);
}

// PR 4 review finding 4 (P2): canonicalHostname() only rejected a last label
// of plain decimal digits ("127.0.0.1"), so a WHATWG-style numeric label
// using 0x-prefixed hex ("0x7f.0x0.0x0.0x1") slipped through as if it were
// an ordinary hostname, even though a real URL parser canonicalises it to a
// numeric address. Node's own URL implements the same WHATWG algorithm, so
// it is used here to prove the risk is real - not just asserted - before
// checking our policy rejects the un-canonicalised form outright.
{
  const NodeURL = require('node:url').URL;
  const hexQuad = 'http://0x7f.0x0.0x0.0x1/';
  const canon = new NodeURL(hexQuad).hostname;
  assert.equal(canon, '127.0.0.1', 'sanity: this environment\'s URL parser must actually canonicalise hex-quad host forms, or this test proves nothing');
  assert.equal(S.safeHttpUrl(hexQuad), '', 'review_p2_hex_ipv4_rejected');
  assert.equal(S.safeHttpUrl('http://0xa.0x0.0x0.0x1/'), '', 'review_p2_hex_ipv4_rejected');
  assert.equal(new NodeURL('http://0xa.0x0.0x0.0x1/').hostname, '10.0.0.1');
}
{
  const octalQuad = 'http://0177.0.0.1/';
  assert.equal(new (require('node:url').URL)(octalQuad).hostname, '127.0.0.1',
    'sanity: this environment\'s URL parser must actually canonicalise octal host forms, or this test proves nothing');
  assert.equal(S.safeHttpUrl(octalQuad), '', 'review_p2_octal_ipv4_rejected');
  assert.equal(S.safeHttpUrl('http://0177.00.00.01/'), '', 'review_p2_octal_ipv4_rejected');
}
{
  const NodeURL = require('node:url').URL;
  assert.equal(new NodeURL('http://2130706433/').hostname, '127.0.0.1',
    'sanity: this environment\'s URL parser must actually canonicalise integer host forms, or this test proves nothing');
  assert.equal(S.safeHttpUrl('http://2130706433/'), '', 'review_p2_integer_ipv4_rejected');
  assert.equal(S.safeHttpUrl('http://0x7f000001/'), '', 'review_p2_integer_ipv4_rejected');
}
{
  const NodeURL = require('node:url').URL;
  assert.equal(new NodeURL('http://10.0.0x0.0x1/').hostname, '10.0.0.1',
    'sanity: this environment\'s URL parser must actually canonicalise mixed-radix host forms, or this test proves nothing');
  assert.equal(S.safeHttpUrl('http://10.0.0x0.0x1/'), '', 'review_p2_mixed_numeric_ipv4_rejected');
  assert.equal(S.safeHttpUrl('http://10.0.00.01/'), '', 'review_p2_mixed_numeric_ipv4_rejected');
  assert.equal(S.safeHttpUrl('http://0X7F.0X0.0X0.0X1/'), '', 'review_p2_mixed_numeric_ipv4_rejected (uppercase 0X)');
}
// Ordinary DNS-style hostnames remain unaffected.
for (const u of ['https://example.com/', 'https://sub.example.co.uk/', 'https://x0.example.com/'])
  assert.ok(S.safeHttpUrl(u), u);

// PR 4 review finding 5 (P2): snapshot() validated the raw image handle
// against the qsimage-only shape /^image:\/\/qsimage\/\d+\/\d+$/ before the
// image://icon/<name> extraction ever ran, so any image://icon/... handle -
// exactly what `notify-send -i some-icon` produces - failed that check first
// and was thrown away, indistinguishable from no icon at all. The name is
// now pulled out before the qsimage-only check runs.
{
  const iconRow = Store.snapshot({ appName: 'Test', summary: 's', body: 'b', image: 'image://icon/kitty' }, 'n1', { Normal: 1 });
  assert.equal(iconRow.appIcon, 'kitty', 'review_p2_named_icon_hint_preserved');
  assert.equal(iconRow.image, '', 'a named-icon hint is not also a qsimage handle');
}
{
  // The strict appIcon charset (no "/") is what actually keeps a traversal
  // or a foreign scheme from being promoted into a local path lookup, not
  // the extraction itself.
  for (const hostile of ['image://icon/../../etc/passwd', 'image://icon/' + 'a'.repeat(500),
                          'file:///etc/passwd', 'https://example/image.png']) {
    const row = Store.snapshot({ appName: 'Test', summary: 's', body: 'b', image: hostile }, 'n1', { Normal: 1 });
    assert.ok(!row.appIcon.includes('/'), 'review_p2_named_icon_path_traversal_rejected: ' + hostile + ' -> ' + JSON.stringify(row.appIcon));
    assert.equal(row.image, '', hostile);
  }
  const traversal = Store.snapshot({ appName: 'Test', summary: 's', body: 'b', image: 'image://icon/../../etc/passwd' }, 'n1', { Normal: 1 });
  assert.equal(traversal.appIcon, '', 'review_p2_named_icon_path_traversal_rejected');
}
{
  // image://qsimage/<n>/<n> is the separate, already-validated internal
  // handle and must be unaffected by the reordering.
  const qs = Store.snapshot({ appName: 'Test', summary: 's', body: 'b', image: 'image://qsimage/12/1' }, 'n1', { Normal: 1 });
  assert.equal(qs.image, 'image://qsimage/12/1');
  assert.equal(qs.appIcon, '');
}

// PR 4 review finding 6 (P2): the Python persistence allowlist deliberately
// drops link/meeting/phone on write - correctly, so a stored notification
// cannot later assert its own capabilities - but restored() did not
// recompute them, so "Open link"/"Copy number" never came back after a
// restart even for an entirely ordinary notification. restored() now
// re-runs Detect.scan() on the persisted summary/body and lets normalise()
// re-validate the result, rather than persisting the derived fields again.
{
  // A persisted entry as the Python store actually returns one: bounded
  // source text only, no link/meeting/phone - those keys are simply absent.
  const persisted = { key: 'n1', app: 'Chat', summary: 'New message',
    body: 'Join https://meet.google.com/abc-defg-hij or call +44 7911 123456',
    rawBody: 'Join https://meet.google.com/abc-defg-hij or call +44 7911 123456',
    urgency: 1 };
  const row = Store.restored(persisted);
  assert.equal(row.link, 'https://meet.google.com/abc-defg-hij', 'review_p2_restored_link_reconstructed');
  assert.equal(row.meeting, true, 'review_p2_restored_link_reconstructed (meeting link)');
  assert.equal(row.phone, '+44 7911 123456', 'review_p2_restored_phone_reconstructed');
  assert.equal(row.restored, true);
}
{
  // A legacy or tampered on-disk entry carrying a link/phone the current
  // body does not actually support must not have it trusted through
  // restore - it is recomputed from the text, not read off the entry.
  const tampered = { key: 'n1', app: 'Chat', summary: 'New message',
    body: 'Nothing to see here', rawBody: 'Nothing to see here', urgency: 1,
    link: 'https://evil.example/phish', meeting: true, phone: '+1 555 0100' };
  const row = Store.restored(tampered);
  assert.equal(row.link, '', 'review_p2_restored_malicious_link_not_trusted');
  assert.equal(row.meeting, false, 'review_p2_restored_malicious_link_not_trusted');
  assert.equal(row.phone, '', 'review_p2_restored_malicious_link_not_trusted');
}
{
  // A link present in the restored text itself but rejected by today's URL
  // policy (here: a loopback address) must stay unavailable, not merely
  // pass through because Detect found *something* link-shaped.
  const dangerous = { key: 'n1', app: 'Chat', summary: 'New message',
    body: 'See http://127.0.0.1/admin for details',
    rawBody: 'See http://127.0.0.1/admin for details', urgency: 1 };
  const row = Store.restored(dangerous);
  assert.equal(row.link, '', 'review_p2_restored_malicious_link_not_trusted (loopback body link)');
}

{ // Omarchy's click contract: omarchy-notification-send --exec carries an argv
  // the shell runs through bash positional parameters, from any sender. The
  // check is structural; it fails closed rather than judging intent.
  const shot = JSON.stringify(['omasnap', '--edit', '/tmp/shot.png'])
  assert.equal(JSON.stringify(S.parseExecArgv(shot)), shot)
  assert.equal(JSON.stringify(S.parseExecArgv(['mpv', '--', '/tmp/a b.mp4'])), JSON.stringify(['mpv', '--', '/tmp/a b.mp4']))
  assert.equal(JSON.stringify(S.parseExecArgv(JSON.stringify(['bash', '-c', 'id']))), JSON.stringify(['bash', '-c', 'id']))
  for (const bad of ['', 'not json', '{}', '[]', '[1]', '["mpv", 2]', '[""]', '["-rf"]', '["--help"]',
                     JSON.stringify(Array(33).fill('x')), JSON.stringify(['x'.repeat(4097)])])
    assert.equal(S.parseExecArgv(bad), null, bad)
  for (const app of ['omarchy-action', 'Crash watch', 'notify-send']) {
    const row = Store.snapshot({ appName: app, summary: 'Action', hints: { 'omarchy-exec-argv': shot } }, 'action', { Normal: 1 })
    assert.equal(row.execArgv, shot, app + ' keeps its click command')
    // A toast restored after a shell restart clicks through like the live one.
    assert.equal(Store.sanitiseForPersistence(row).execArgv, shot)
    assert.equal(Store.restored(Store.sanitiseForPersistence(row)).execArgv, shot)
  }
  const malformed = Store.snapshot({ appName: 'x', summary: 'y', hints: { 'omarchy-exec-argv': '["-x"]' } }, 'bad', { Normal: 1 })
  assert.equal(malformed.execArgv, '')
  // A verification-code card is redacted whole, its command included.
  const secret = Store.snapshot({ appName: 'x', summary: 'Sign in', body: 'Your verification code is 482913',
                                  hints: { 'omarchy-exec-argv': shot, 'omarchy-glyph': '\u{f0306}' } }, 'secret', { Normal: 1 })
  assert.equal(Store.sanitiseForPersistence(secret).execArgv, '')
  assert.equal(Store.sanitiseForPersistence(secret).glyph, '')
}

{ // The glyph hint: a short mark for the icon slot, persisted with the row.
  const glyph = '\u{f0954}'
  const row = Store.snapshot({ appName: 'omarchy-action', summary: '14:02', hints: { 'omarchy-glyph': glyph } }, 'g', { Normal: 1 })
  assert.equal(row.glyph, glyph)
  assert.equal(Store.restored(Store.sanitiseForPersistence(row)).glyph, glyph)
  assert.equal(S.safeGlyph('x'.repeat(17)), '')
  assert.equal(S.safeGlyph('a\u0007'), '')
  assert.equal(S.safeGlyph(12), '')
  const transient = Store.snapshot({ appName: 'Slack', summary: 'typing', hints: { transient: true } }, 't', { Normal: 1 })
  assert.equal(transient.transient, true)
}

{ // Delivery: what quiet lets through, and what it records.
  const Delivery = load('Delivery')
  const state = (over) => Object.assign({ doNotDisturb: false, globalSnoozed: false, sourceSnoozed: false, codesBypassQuiet: true }, over)
  assert.equal(Delivery.quietReason({ app: 'Slack', urgency: 1 }, state()), '')
  assert.equal(Delivery.quietReason({ app: 'Slack', urgency: 1 }, state({ doNotDisturb: true })), 'silenced')
  assert.equal(Delivery.quietReason({ app: 'Slack', urgency: 1 }, state({ globalSnoozed: true })), 'snoozed')
  assert.equal(Delivery.quietReason({ app: 'Slack', urgency: 1 }, state({ sourceSnoozed: true })), 'snoozed')
  assert.equal(Delivery.quietReason({ app: 'Slack', urgency: 2 }, state({ doNotDisturb: true })), 'silenced',
               'a branded critical does not punch through')
  assert.equal(Delivery.quietReason({ app: 'notify-send', urgency: 2 }, state({ doNotDisturb: true })), '')
  assert.equal(Delivery.quietReason({ app: 'notify-send', urgency: 1 }, state({ doNotDisturb: true })), 'silenced')
  assert.equal(Delivery.quietReason({ app: 'omarchy-action', urgency: 0 }, state({ globalSnoozed: true })), '')
  assert.equal(Delivery.quietReason({ app: 'Google', urgency: 1, code: '482913' }, state({ doNotDisturb: true })), '')
  assert.equal(Delivery.quietReason({ app: 'Google', urgency: 1, code: '482913' },
                                    state({ doNotDisturb: true, codesBypassQuiet: false })), 'silenced')
  assert.ok(Delivery.isEphemeral({ app: 'notify-send' }))
  assert.ok(Delivery.isEphemeral({ app: 'omarchy-action' }))
  assert.ok(Delivery.isEphemeral({ app: 'Slack', transient: true }))
  assert.ok(!Delivery.isEphemeral({ app: 'Slack' }))
  assert.ok(Delivery.summaryStartsWithGlyph('\u{f009b}  Silenced'))
  assert.ok(!Delivery.summaryStartsWithGlyph('Silenced  notifications'))
  assert.ok(!Delivery.summaryStartsWithGlyph(''))

  // The deck clears the bar only on the top and right edges it touches, by
  // the bar's thickness on that screen.
  const bar = { barHidden: false, barSize: 26, barSizeFor: name => name === 'notched' ? 40 : 26 }
  assert.equal(Delivery.barThickness(bar, 'notched', 26), 40)
  assert.equal(Delivery.barThickness(bar, 'plain', 26), 26)
  assert.equal(Delivery.barThickness({ barHidden: true }, 'plain', 26), 0)
  assert.equal(Delivery.barThickness(null, 'plain', 28), 28)
  assert.equal(JSON.stringify(Delivery.deckMargins('top', 26, 10)), JSON.stringify({ top: 36, right: 10 }))
  assert.equal(JSON.stringify(Delivery.deckMargins('right', 40, 10)), JSON.stringify({ top: 10, right: 50 }))
  assert.equal(JSON.stringify(Delivery.deckMargins('bottom', 26, 10)), JSON.stringify({ top: 10, right: 10 }))
  assert.equal(JSON.stringify(Delivery.deckMargins('left', 26, 10)), JSON.stringify({ top: 10, right: 10 }))
}

{ // Settings: every key optional, every invalid value falls back.
  const Settings = load('Settings')
  const d = Settings.resolve(null)
  assert.equal(d.stacking, 'source')
  assert.equal(d.fullscreenOverlay, 'all')
  assert.equal(d.edgeSpacing, null, 'unset edge spacing follows the theme gap')
  assert.equal(d.allowDefaultActionOnCardClick, true)
  assert.equal(d.codesBypassQuiet, null)
  assert.equal(JSON.stringify(d.snoozeDurations), JSON.stringify(['30', '60', '240', 'tomorrow']))
  const r = Settings.resolve({ stacking: 'nope', fontScale: 500, edgeSpacing: '8', wakeHour: 0,
                               snoozeDurations: ['15', 'bogus', '15', 'tomorrow'], historyHours: 7,
                               clipboardTimeout: 90, codesBypassQuiet: false, displayName: 7 })
  assert.equal(r.stacking, 'source')
  assert.equal(r.fontScale, 200)
  assert.equal(r.edgeSpacing, 8)
  assert.equal(r.wakeHour, 0, 'midnight is a valid wake hour')
  assert.equal(JSON.stringify(r.snoozeDurations), JSON.stringify(['15', 'tomorrow']))
  assert.equal(r.historyHours, 24)
  assert.equal(r.clipboardTimeout, 90)
  assert.equal(r.codesBypassQuiet, false)
  assert.equal(r.displayName, '')
  assert.equal(JSON.stringify(Settings.resolve({ snoozeDurations: [] }).snoozeDurations), JSON.stringify(d.snoozeDurations))
  const now = new Date(2026, 9, 19, 22, 30).getTime()
  assert.equal(Settings.snoozeSeconds('60', 8, now), 3600)
  assert.equal(Settings.snoozeSeconds('tomorrow', 8, now), (9 * 3600 + 1800))
  assert.equal(Settings.snoozeSeconds('tomorrow', 0, new Date(2026, 9, 19, 23, 58).getTime()), 600,
               'tomorrow is never less than ten minutes away')
  assert.equal(Settings.snoozeSeconds('nope', 8, now), 0)
}

{ // The shell trusts helper output only in the exact shapes the helper writes.
  const dir = '/home/u/.cache/omarchy/notification-icons/'
  const scope = { iconCacheDir: dir, String, Number }
  vm.createContext(scope)
  vm.runInContext(extract(source, 'function trustedIconPath(text, exitCode)', '\n  Process {'), scope)
  const digest = 'a'.repeat(64)
  const ok = dir + digest + '.png'
  assert.equal(scope.trustedIconPath(ok + '\n', 0), ok)
  assert.equal(scope.trustedIconPath(dir + digest + '-mono.png', 0), dir + digest + '-mono.png')
  assert.equal(scope.trustedIconPath(ok, 1), '', 'a failed helper answers nothing')
  for (const bad of ['/home/u/.ssh/id_ed25519', dir + '../x.png', dir + digest + '.svg', dir + 'norm-slack.png',
                     dir + 'A'.repeat(64) + '.png', dir + digest.slice(1) + '.png', dir + 'sub/' + digest + '.png',
                     '/home/u/.local/state/omarchy/notifications/icons/' + digest + '.png',
                     'file://' + ok, ok + 'x'.repeat(600)])
    assert.equal(scope.trustedIconPath(bad, 0), '', bad)

  const images = { liveKeys: { k: { senderImage: null } }, senderImageRevision: 0 }
  vm.createContext(images)
  vm.runInContext(extract(source, 'function finishSenderImage(job, image)', 'function pumpSenderImages()'), images)
  const job = { key: 'k', image: '' }
  images.liveKeys.k.senderImage = job
  const svg = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><image href="/etc/x.png"/></svg>').toString('base64')
  images.finishSenderImage(job, 'data:image/png;base64,' + svg)
  assert.equal(job.image, '', 'an SVG labelled as a PNG is refused')
  const pngHeader = Buffer.from('\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01', 'latin1').toString('base64')
  images.finishSenderImage(job, 'data:image/png;base64,' + pngHeader)
  assert.ok(job.image.startsWith('data:image/png;base64,iVBORw0KGgo'), 'a PNG is accepted')
}

console.log('notification logic: passed')
