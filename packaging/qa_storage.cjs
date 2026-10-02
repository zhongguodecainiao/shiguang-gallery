const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
class Element {
  constructor() { this.children = []; this.disabled = false; this.open = false; this.classList = {toggle(){}}; this.listeners = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(event, cb) { this.listeners[event] = cb; }
  showModal() { this.open = true; }
}
const nodes = new Map();
const $ = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
const fixed = {path: 'C:\\', label: 'Windows', kind: 'fixed', default: true, ready: true};
const usb = {path: 'F:\\', label: '照片备份', kind: 'usb', default: false, ready: true};
let state = {mode: 'computer', roots: ['C:\\'], drives: [fixed]};
let timer, applyCalls = 0, failRefresh = false, pending = null;
const context = vm.createContext({
  $, document: {createElement: () => new Element()},
  el: (tag, cls, text) => Object.assign(new Element(), {text, cls}),
  T: (text, ...args) => text.replace(/\{(\d+)\}/g, (_, i) => args[+i]),
  I18n: {text: (node, value) => node.text = value, concat: (...v) => v.join(''), number: String, errorText: String},
  guard: f => f, openFolderBrowser(){}, location: {reload(){}},
  setInterval: fn => (timer = fn, 1), clearInterval: () => timer = null,
  api: async route => { if (route.includes('/apply')) {applyCalls++; return {ok:true};} if (pending) return pending; if (failRefresh) throw Error('offline'); return structuredClone(state); }
});
const js = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
const start = js.indexOf('// Source edits');
const end = js.indexOf("$('#sourceDialog').addEventListener('close'", start);
vm.runInContext(js.slice(start, js.indexOf('\n});', end) + 4), context);
const run = code => vm.runInContext(code, context);
(async () => {
  await run('openSourceSettings()');
  assert.equal($('#sourceDriveChoices').children.length, 1);
  state.drives = [fixed, usb];
  await timer();
  assert.equal($('#sourceDriveChoices').children.length, 2);
  assert.equal($('#sourceDriveChoices').children[1].children[0].checked, false);
  const input = $('#sourceDriveChoices').children[1].children[0];
  input.checked = true; input.onchange();
  assert.equal(run('sourceDraft.roots.length'), 2);
  state.drives = [fixed];
  await run('refreshSourceDrives()');
  assert.equal($('#applySource').disabled, true);
  const offline = $('#sourceDriveChoices').children[1].children[0];
  assert.equal(offline.checked, true);
  assert.equal(offline.disabled, false);
  assert.match($('#sourceSelection').text, /未就绪/);
  state.drives = [fixed, usb];
  await timer();
  assert.equal($('#applySource').disabled, false);
  $('#sourceAll').checked = false; $('#sourceAll').onchange();
  $('#sourceFolderPath').value = 'F:\\DCIM'; $('#sourceFolderPath').oninput();
  await run('refreshSourceDrives()');
  assert.equal(run('sourceDraft.roots[0]'), 'F:\\DCIM');
  failRefresh = true; await run('refreshSourceDrives()'); failRefresh = false;
  assert.match($('#sourceError').text, /offline/);
  let resolve; pending = new Promise(r => resolve = r);
  const refresh = run('refreshSourceDrives()');
  $('#sourceDialog').open = false; $('#sourceDialog').listeners.close();
  resolve(structuredClone(state)); await refresh; pending = null;
  assert.equal(timer, null);
  assert.equal(applyCalls, 0);
  console.log('PASS: hot-plug, disconnect/reconnect, preserved drafts, error recovery, close race, no automatic scans');
})().catch(err => {console.error(err); process.exitCode = 1;});
