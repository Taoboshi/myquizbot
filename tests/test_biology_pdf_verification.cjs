const assert = require('node:assert/strict');
const modules = [1,2,3,4].map(n => require(`./biology_${n}_module.json`).questions);
assert.deepEqual(modules.map(qs => qs.length), [225,116,191,223]);
for (const qs of modules) for (const q of qs) {
  assert(q.question.trim());
  if (q.options) {
    assert(q.options.every(option => option.trim()));
    assert(Number.isInteger(q.correct_index) && q.correct_index >= 0 && q.correct_index < q.options.length);
  } else assert(q.answer.trim());
}
assert.deepEqual(modules[1][112].options, ['2']);
assert.deepEqual(modules[1][113].options, ['Дупликация']);
assert.equal(modules[2][188].options[0], 'Патау');
assert(modules[2][188].question.includes('геномную аутосомную мутацию'));
for (const [number,count,key] of [[31,5,1],[34,5,0],[82,6,4],[220,5,0]]) {
  const q = modules[3][number-1];
  assert.equal(q.options.length,count);
  assert.equal(q.correct_index,key);
  assert(!q.question.includes('→'));
  assert(q.options.every(option => !/\s[a-f][.]\s/.test(option)));
}
assert.equal(modules[3][81].options[5], 'Индукция');
assert(modules[3][219].options[2].endsWith('гомейозисные гены'));
console.log('Passed: biology counts, preserved extra source card, direct recall and repaired choices/keys.');
