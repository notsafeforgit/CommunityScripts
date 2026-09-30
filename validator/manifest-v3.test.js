const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { Validator } = require('./index.js');

for (const [name, manifest, expected] of [
  ['legacy manifest', 'name: Legacy\nsettings: {enabled: {displayName: Enabled, type: BOOLEAN}}', true],
  ['v3 native settings', 'apiVersion: 3\nname: Native\nsettings: {mapping: {type: JSON, editor: JQ_MAP, default: {title: .title}}}', true],
  ['v3 browser module', 'apiVersion: 3\nname: Browser\nui: {entry: index.js, assets: {"/": dist}}', true],
  ['v3 backend notifications', 'apiVersion: 3\nname: Hooks\nhooks: [{name: Deleted, triggeredBy: [File.Destroy.Post, Group.Update.Post, Performer.Merge.Post]}]', true],
  ['v3 entity preview', 'apiVersion: 3\nname: Preview\nsettings: {mapping: {type: JSON, editor: JQ_MAP, preview: {entity: SCENE}}}', true],
  ['invalid preview entity', 'apiVersion: 3\nname: Invalid\nsettings: {mapping: {editor: JQ, preview: {entity: OTHER}}}', false],
  ['future version', 'apiVersion: 4\nname: Future', false],
  ['legacy scripts in v3', 'apiVersion: 3\nname: Invalid\nui: {javascript: [old.js]}', false],
  ['native settings without v3', 'name: Invalid\nsettings: {mapping: {displayName: Mapping, type: JSON}}', false],
]) {
  test(name, (t) => {
    t.mock.method(console, 'log', () => {});
    t.mock.method(console, 'error', () => {});
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plugin-manifest-'));
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    const file = path.join(dir, 'fixture.yml');
    fs.writeFileSync(file, manifest);
    assert.equal(new Validator([]).run([file]), expected);
  });
}
