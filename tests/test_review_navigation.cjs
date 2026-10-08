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
  document: {getElementById(id) {
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
