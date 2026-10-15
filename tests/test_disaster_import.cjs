const assert = require('node:assert/strict');
const data = require('./disaster_medicine.json');
assert.equal(data.questions.length, 99);
for (const q of data.questions) {
  assert(q.question.trim());
  assert(q.options.length >= 2 && q.options.every(option => option.trim()));
  assert(Number.isInteger(q.correct_index) && q.correct_index >= 0 && q.correct_index < q.options.length);
}
const functional = data.questions.find(q => q.question.startsWith('Функциональным подразделением этапа медицинской эвакуации является'));
const medicalCare = data.questions.find(q => q.question.startsWith('Медицинская помощь пораженным оказывается в'));
assert.equal(functional.correct_index, 2);
assert.equal(functional.options[2], 'приемно-сортировочное отделение');
assert.equal(medicalCare.correct_index, 1);
assert.equal(medicalCare.options[1], 'в перевязочной');
console.log('Passed: 99 questions, corrected functional-unit answer and restored medical-care answer.');
