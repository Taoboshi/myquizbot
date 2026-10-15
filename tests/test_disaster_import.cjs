const assert = require('node:assert/strict');
const data = require('./disaster_medicine.json');
assert.equal(data.questions.length, 99);
for (const q of data.questions) {
  assert(q.question.trim());
  assert(q.options.length >= 2 && q.options.every(option => option.trim()));
  assert(Number.isInteger(q.correct_index) && q.correct_index >= 0 && q.correct_index < q.options.length);
}
assert.equal(data.questions[71].correct_index, 2);
assert.equal(data.questions[71].options[2], 'в приемно-сортировочном отделении');
console.log('Passed: 99 questions and user-specified third answer for question 72.');
