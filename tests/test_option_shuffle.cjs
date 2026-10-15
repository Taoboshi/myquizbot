const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../quiz_bot/web/app-quiz.js'), 'utf8');
const helpers = code.slice(code.indexOf('  function canShuffleQuestionOptions'), code.indexOf('  // Answers always use source indices'));
const state = {userAnswers:{}, revealedAnswers:new Set()};
const appPreferences = {shuffleOptions:true};
const math = Object.create(Math);
math.random = () => 0;
const context = vm.createContext({state,appPreferences,Math:math});
vm.runInContext(helpers,context);
const q = {id:1,question:'Выберите правильный ответ',options:['Alpha','Beta','Gamma'],correct_index:1};
const order = () => Array.from(context.getSolverOptionOrder(q));
assert.deepEqual(order(),[1,2,0]);
assert.deepEqual(q.options,['Alpha','Beta','Gamma']);
assert.deepEqual(order(),[1,2,0]);
state.userAnswers[1]=1;
appPreferences.shuffleOptions=false;
assert.deepEqual(order(),[1,2,0]);
state.userAnswers={};
assert.deepEqual(order(),[0,1,2]);
for(const option of ['Верны ответы 1 и 3','Всё вышеперечисленное','Все ответы верны','Оба варианта','Последний вариант','Answers 1 and 3','all of the above']) {
  assert.equal(context.canShuffleQuestionOptions({...q,options:['A',option]}),false,option);
}
assert(context.canShuffleQuestionOptions(q));
state.optionOrders[1]=[0,0,2];
assert.deepEqual(order(),[0,1,2]);
console.log('Passed: shuffle permutation, stable order, source immutability, answered retention, reset, exclusions and invalid saved order.');
