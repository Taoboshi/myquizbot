const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const elements = new Map();
const context = vm.createContext({
  console, Set, Map, AbortController,
  state: {
    testLoadStatus: 'ready', activeTestId: 'test', activeAttempt: null,
    currentTestOriginalQuestions: [{id: 1}], userErrors: new Set([1]),
    currentTab: 'home', homeActiveView: 'hub',
  },
  document: {addEventListener() {}, getElementById(id) {
    if (!elements.has(id)) elements.set(id, {classList: {
      add() {}, remove() {},
    }});
    return elements.get(id);
  }},
  localStorage: {getItem(key) {return key.startsWith('ohtest_errors_') ? '[1]' : null;}, setItem() {}, removeItem() {}},
  viewStack: [],
  BUNDLED_TESTS: {test: {title: 'Test', questions: [{id: 1}]}},
  triggerHaptic() {}, hideAllViews() {}, updateHeaderNavState() {},
  updateTelegramBackButton() {}, clearInterval() {}, setInterval() {return 1;},
});
for (const module of ['app-quiz.js', 'app-profile.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../quiz_bot/web', module), 'utf8'), context);
}
vm.runInContext(`
  isQuizletOnly = () => false;
  saveActiveAttemptState = () => {};
  renderCurrentQuestion = () => {};
  doFinishQuiz = () => { state.finished = true; };
  returnToProfileErrors = () => { state.destination = 'profile'; };
  openTestHub = () => { state.destination = 'hub'; };
  getAllSavedErrors = () => [{testId: 'test', questionId: 1}];
`, context);

context.startQuizMode('errors_solve');
assert.equal(context.state.errorReviewOrigin, 'hub');
context.returnFromErrorReview();
assert.equal(context.state.destination, 'hub');

context.state.currentTab = 'profile';
context.state.homeActiveView = 'home';
context.startQuizMode('errors_solve');
assert.equal(context.state.errorReviewOrigin, 'profile');
context.returnFromErrorReview();
assert.equal(context.state.destination, 'profile');

context.state.currentTab = 'home';
context.state.homeActiveView = 'result';
context.startQuizMode('errors_solve');
assert.equal(context.state.errorReviewOrigin, 'profile');

context.solveOneError('test', 1);
assert.equal(context.state.errorReviewOrigin, 'profile');
context.state.userErrors = new Set([1]);
context.startAllErrorsSession('hub');
assert.equal(context.state.errorReviewOrigin, 'hub');

for (const mode of ['errors_solve', 'training', 'mini10']) {
  context.state.currentMode = mode;
  context.state.activeQuestions = [{id: 1}, {id: 2}];
  context.state.userAnswers = {};
  context.state.finished = false;
  context.requestFinishQuiz();
  assert.equal(context.state.finished, true, mode);
}
context.state.currentMode = 'normal';
context.state.finished = false;
context.requestFinishQuiz();
assert.equal(context.state.finished, false);
console.log('Passed: review origins, retry origin, immediate review/training finish, normal-test confirmation.');
context.adminStore = {testsMeta: [{id: 'test', title: 'Test', questions_count: 1}]};
context.fetchTestResource = () => {throw new Error('Opening the hub must not request questions');};
context.selectTest('test').then(async () => {
  assert.equal(context.state.testLoadStatus, 'idle');
  assert.equal(context.state.currentTestOriginalQuestions.length, 0);
  console.log('Passed: opening the test hub defers all material requests.');
  const recorded = [];
  context.fetch = (url, options) => {recorded.push({url, data: JSON.parse(options.body)}); return Promise.resolve({ok:true});};
  context.getCorrectIndex = () => 0;
  context.selectOption = index => {context.state.userAnswers[1] = index;};
  context.state.activeQuestions = [{id:1}];
  context.state.currentQIndex = 0;
  context.state.revealedAnswers = new Set([1]);
  context.state.userAnswers = {};
  context.assessRevealedAnswer(true);
  assert.equal(context.state.userAnswers[1], 0);
  await Promise.resolve();
  assert.equal(recorded[0].url, '/api/errors/resolve');
  context.state.userAnswers = {};
  context.assessRevealedAnswer(false);
  assert.equal(context.state.userAnswers[1], -1);
  assert.equal(recorded.length, 1);
  context.state.userAnswers = {1:1};
  context.assessRevealedAnswer(true);
  assert.equal(context.state.userAnswers[1], 1);
  console.log('Passed: revealed-answer self-assessment and protection of an already wrong answer.');
}).catch(error => {console.error(error); process.exitCode = 1;});
