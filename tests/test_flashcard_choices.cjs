const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../quiz_bot/web/app-quiz.js'), 'utf8');
const helper = source.slice(source.indexOf('  function getFCQuestionText'), source.indexOf('  function renderFCCard'));
const context = vm.createContext({});
vm.runInContext(helper, context);
let count = 0;
const normalize = value => String(value).replace(/\s+/g, ' ').trim();
for (const file of fs.readdirSync(__dirname).filter(file => file.endsWith('.json'))) {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, file), 'utf8'));
  for (const [index, q] of data.questions.entries()) {
    const before = JSON.stringify(q);
    const text = context.getFCQuestionText(q);
    assert.equal(JSON.stringify(q), before, `${file} #${index + 1}: mutated source`);
    if (q.options?.length > 1) {
      for (const option of q.options) assert(normalize(text).includes(normalize(option)), `${file} #${index + 1}: missing option`);
      assert(Number.isInteger(q.correct_index) && q.correct_index >= 0 && q.correct_index < q.options.length);
      count++;
    } else assert.equal(text, q.question, `${file} #${index + 1}: changed direct recall`);
  }
}
for (const question of ['Пример\n1) Alpha\n2) Beta', 'Пример\nА. Alpha\nБ.Beta', 'Пример\na. Alpha\nb. Beta']) {
  assert.equal(context.getFCQuestionText({question, options:['Alpha','Beta']}), question);
}
const partial = context.getFCQuestionText({question:'Пример\na. Alpha', options:['Alpha','Beta']});
assert(partial.includes('Beta'));
const biology = require('./biology_5_module.json').questions;
assert.equal(biology.length, 385);
assert(biology[5].options[0].startsWith('все ответы правильные'));
assert(biology[5].options[0].includes('Г высвободить нуклеиновую кислоту.'));
assert(!biology[5].question.includes('все ответы правильные'));
for (const number of [13,33,39,110]) {
  assert(!biology[number-1].question.includes('Г.'));
  assert(biology[number-1].options[0].includes('А.') && biology[number-1].options[0].includes('Г.'));
}
for (const number of [14,17,44,49,178]) assert(biology[number-1].options[0].length > 40);
assert(biology[177].options[0].includes('1. Фекально-оральным') && biology[177].options[0].includes('4. При близком контакте'));
console.log(`Passed: all ${count} multiple-choice cards retain choices; direct recall, existing lists, source immutability and biology repairs.`);
