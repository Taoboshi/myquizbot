const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../quiz_bot/web/app-subject-icons.js'), 'utf8'), {window});
for (const icon of window.SUBJECT_ICON_CATALOG) {
  const html = window.renderSubjectIcon(icon.key);
  assert(html.includes('<svg'), icon.key);
  assert(!html.includes('undefined'), icon.key);
  assert(!html.includes('accent'), icon.key);
}
for (const key of ['hospital', 'first-aid', 'nursing', 'medical-record', 'prevention']) {
  const html = window.renderSubjectIcon(key);
  assert(html.includes('--subject-detail-dark:#fb7185'), key);
  assert.equal((html.match(/class="subject-icon-detail"/g) || []).length, 2, key);
}
const capsule = window.renderSubjectIcon('pill');
assert.equal((capsule.match(/<path /g) || []).length, 2);
assert.equal((capsule.match(/class="subject-icon-detail"/g) || []).length, 1);
assert(!window.renderInterfaceIcon('pill').includes('subject-icon-detail'));
console.log(`Passed: ${window.SUBJECT_ICON_CATALOG.length} subject icons, medical crosses, capsule halves, interface isolation.`);
