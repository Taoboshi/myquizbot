// Active Attempt Persistence (Preserves main quiz attempt during errors_solve!)
  function saveActiveAttemptState() {
    if (state.activeQuestions.length === 0) return;
    // DO NOT overwrite active main attempt during error reviews
    if (state.currentMode === 'errors_solve' || state.currentMode === 'all_favs') return;
    state.activeAttempt = {
      testId: state.activeTestId,
      testTitle: state.activeTestTitle,
      mode: state.currentMode,
      qIndex: state.currentQIndex,
      total: state.activeQuestions.length,
      userAnswers: state.userAnswers,
      revealedAnswers: [...state.revealedAnswers],
      timerSeconds: state.timerSeconds,
      timestamp: Date.now()
    };
    try {
      localStorage.setItem('ohtest_active_attempt', JSON.stringify(state.activeAttempt));
    } catch(e) {}
    renderActiveAttemptBanner();
    updateHubResumeButton();
  }

  function restoreActiveAttemptState() {
    try {
      const raw = localStorage.getItem('ohtest_active_attempt');
      if (raw) {
        state.activeAttempt = JSON.parse(raw);
      }
    } catch(e) {}
  }

  function renderActiveAttemptBanner() {
    const hasAttempt = Boolean(state.activeAttempt && state.activeAttempt.testId);
    const modeNames = {
      normal: 'По порядку',
      random: 'Вразброс',
      reverse: 'С конца',
      mini10: 'Мини-тест',
      errors_solve: 'Разбор ошибок'
    };

    const banners = document.querySelectorAll('.active-attempt-card');
    banners.forEach(banner => {
      if (hasAttempt) {
        banner.classList.remove('hidden');
        const titleEl = banner.querySelector('.attempt-title') || document.getElementById('home-attempt-title');
        const counterEl = banner.querySelector('.attempt-counter') || document.getElementById('home-attempt-counter');
        const modeEl = banner.querySelector('.attempt-mode') || document.getElementById('home-attempt-mode');

        if (titleEl) titleEl.innerText = state.activeAttempt.testTitle || state.activeAttempt.testId;
        if (counterEl) counterEl.innerText = `Вопрос ${state.activeAttempt.qIndex + 1} из ${state.activeAttempt.total}`;
        if (modeEl) modeEl.innerText = `Режим: ${modeNames[state.activeAttempt.mode] || 'Контроль'}`;
      } else {
        banner.classList.add('hidden');
      }
    });

    const homeBanner = document.getElementById('home-active-attempt-card');
    if (homeBanner) {
      if (hasAttempt) {
        homeBanner.classList.remove('hidden');
        const t = document.getElementById('home-attempt-title');
        const c = document.getElementById('home-attempt-counter');
        const m = document.getElementById('home-attempt-mode');
        if (t) t.innerText = state.activeAttempt.testTitle || state.activeAttempt.testId;
        if (c) c.innerText = `Вопрос ${state.activeAttempt.qIndex + 1} из ${state.activeAttempt.total}`;
        if (m) m.innerText = `Режим: ${modeNames[state.activeAttempt.mode] || 'Контроль'}`;
      } else {
        homeBanner.classList.add('hidden');
      }
    }
  }

  function updateHubResumeButton() {
    renderActiveAttemptBanner();
  }

  function resumeActiveAttempt() {
    if (!state.activeAttempt) return;
    triggerHaptic('light');
    selectTest(state.activeAttempt.testId);
    state.currentMode = state.activeAttempt.mode;
    state.currentQIndex = state.activeAttempt.qIndex;
    state.userAnswers = state.activeAttempt.userAnswers || {};
    state.revealedAnswers = new Set(state.activeAttempt.revealedAnswers || []);
    state.timerSeconds = state.activeAttempt.timerSeconds || 0;

    hideAllViews();
    state.homeActiveView = 'solver';
    document.getElementById('view-solver').classList.remove('hidden');
    document.getElementById('btn-grid-modal').classList.remove('hidden');
    document.getElementById('btn-fav-toggle')?.classList.remove('hidden');
    document.getElementById('btn-finish-early').classList.remove('hidden');
    updateTelegramBackButton();

    const modeNames = {
      normal: 'Контроль (по порядку)',
      random: 'Контроль (вразброс)',
      reverse: 'Контроль (с конца)',
      mini10: 'Мини-тест 10',
      errors_solve: 'Разбор ошибок'
    };
    document.getElementById('solver-mode-tag').innerText = modeNames[state.currentMode] || 'Контрольный тест';
    updateHeaderNavState();

    renderCurrentQuestion();
    viewStack.push('solver');
  }

  function discardActiveAttempt() {
    if (confirm('Сбросить текущую попытку?')) {
      triggerHaptic('light');
      state.activeAttempt = null;
      localStorage.removeItem('ohtest_active_attempt');
      renderActiveAttemptBanner();
      updateHubResumeButton();
    }
  }

  // Home Subjects List
  function renderHomeSubjects() {
    const list = document.getElementById('home-subjects-list');
    if (!list) return;
    list.innerHTML = '';
    const visibleTests = getCatalogVisibleTests();
    const countLabel = document.getElementById('home-subjects-count');
    if (countLabel) {
      const testCount = visibleTests.length;
      countLabel.innerText = `${testCount} ${testCount === 1 ? 'тест' : (testCount < 5 ? 'теста' : 'тестов')} доступно`;
    }

    // Only display subjects that have at least 1 test assigned
    const activeSubjects = adminStore.subjects.filter(subj => {
      return visibleTests.some(test => test.subject_id === subj.id);
    });

    if (activeSubjects.length === 0) {
      list.innerHTML = `
        <div class="p-5 rounded-3xl bg-app-card border border-app-border space-y-3 animate-pulse">
          <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-2xl bg-white/5"></div>
            <div class="space-y-1.5 flex-1">
              <div class="h-3.5 bg-white/10 rounded w-1/2"></div>
              <div class="h-2.5 bg-white/5 rounded w-1/4"></div>
            </div>
          </div>
        </div>
      `;
      return;
    }

    // Alphabetical sort with pinned on top
    const sortedSubjects = [...activeSubjects].sort((a, b) => {
      const aPinned = pinnedSubjects.has(a.id) ? 1 : 0;
      const bPinned = pinnedSubjects.has(b.id) ? 1 : 0;
      if (aPinned !== bPinned) return bPinned - aPinned;
      return a.title.localeCompare(b.title, 'ru');
    });

    sortedSubjects.forEach(subj => {
      const isPinned = pinnedSubjects.has(subj.id);
      const card = document.createElement('div');
      card.className = "p-4 rounded-3xl bg-app-card border border-app-border hover:border-brand-500/60 active:scale-[0.98] transition cursor-pointer shadow-lg space-y-2 group relative";
      card.onclick = () => openSubjectTests(subj.id, subj.title);
      attachLongPress(card, () => showPinActionModal('subject', subj.id, subj.title));

      const testsOfSubj = visibleTests.filter(t => t.subject_id === subj.id);
      const testsCount = testsOfSubj.length;

      card.innerHTML = `
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <span class="text-2xl p-2 rounded-2xl bg-app-surface border border-app-border group-hover:scale-110 transition">${subj.emoji}</span>
            <div>
              <div class="flex items-center gap-1.5">
                <h3 class="text-sm font-bold text-white group-hover:text-brand-300 transition">${subj.title}</h3>
                ${isPinned ? '<span class="text-xs" title="Закреплено">📌</span>' : ''}
              </div>
              <span class="text-[11px] text-slate-400">${testsCount} ${testsCount === 1 ? 'тест' : (testsCount < 5 ? 'теста' : 'тестов')}</span>
            </div>
          </div>
          <span class="text-xs font-bold text-slate-500 group-hover:text-brand-400 group-hover:translate-x-1 transition">→</span>
        </div>
      `;
      list.appendChild(card);
    });

    const searchInput = document.getElementById('home-catalog-search');
    if (searchInput?.value) filterCatalogByQuery(searchInput.value);
  }

  // Subject Tests View
  function openSubjectTests(subjectId, subjectTitle) {
    triggerHaptic('light');
    const testsSearch = document.getElementById('subject-tests-search');
    const testsSearchWrap = document.getElementById('subject-tests-search-wrap');
    if (testsSearch) testsSearch.value = '';
    testsSearchWrap?.classList.add('hidden');
    filterSubjectTestsByQuery('');
    state.activeSubjectId = subjectId;
    state.activeSubjectTitle = subjectTitle;
    state.homeActiveView = 'tests';

    hideAllViews();
    document.getElementById('view-tests').classList.remove('hidden');
    updateHeaderNavState();
    updateTelegramBackButton();

    document.getElementById('tests-subj-title').innerText = subjectTitle;

    const container = document.getElementById('tests-items-container');
    container.innerHTML = '';

    let tests = adminStore.testsMeta.filter(t => t.subject_id === subjectId);
    if (!state.isAdmin) {
      tests = tests.filter(t => (t.access_type || 'public') !== 'admin_only');
    }

    // Alphabetical sort with pinned on top
    const sortedTests = [...tests].sort((a, b) => {
      const aPinned = pinnedTests.has(a.id) ? 1 : 0;
      const bPinned = pinnedTests.has(b.id) ? 1 : 0;
      if (aPinned !== bPinned) return bPinned - aPinned;
      return a.title.localeCompare(b.title, 'ru');
    });

    if (sortedTests.length === 0) {
      container.innerHTML = `
        <div class="p-8 text-center rounded-2xl bg-app-card border border-app-border text-slate-400 text-xs">
          В этом разделе пока нет доступных тестов.
        </div>
      `;
    } else {
      sortedTests.forEach(t => {
        const isPinned = pinnedTests.has(t.id);
        const accType = t.access_type || 'public';
        let badgeHtml = '<span class="text-[10px] text-brand-400 font-medium">✓ Доступен</span>';

        if (accType === 'code') {
          const isUnlocked = state.isAdmin || state.unlockedCodeTests.has(t.id);
          badgeHtml = isUnlocked 
            ? '<span class="text-[10px] text-brand-400 font-medium">✓ Доступен</span>' 
            : '<span class="text-[10px] text-amber-400 font-medium">🔑 По коду</span>';
        } else if (accType === 'private') {
          badgeHtml = state.isAdmin
            ? '<span class="text-[10px] text-purple-400 font-medium">🔐 Приватный (админ)</span>'
            : '<span class="text-[10px] text-purple-400 font-medium">🔐 Приватный</span>';
        } else if (accType === 'admin_only') {
          badgeHtml = '<span class="text-[10px] text-rose-400 font-medium">🙈 Только админ</span>';
        }

        const btn = document.createElement('div');
        btn.className = "w-full text-left p-4 rounded-2xl bg-app-card border border-app-border hover:border-brand-500 flex items-center justify-between active:scale-[0.98] transition group cursor-pointer";
        btn.onclick = () => selectTest(t.id);
        attachLongPress(btn, () => showPinActionModal('test', t.id, t.title));
        btn.innerHTML = `
          <div class="space-y-1">
            <div class="flex items-center gap-1.5">
              <h4 class="text-xs sm:text-sm font-bold text-white group-hover:text-brand-300 transition">${t.title}</h4>
              ${isPinned ? '<span class="text-xs" title="Закреплено">📌</span>' : ''}
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-brand-500/10 text-brand-300 font-bold">${t.questions_count} вопросов</span>
              ${badgeHtml}
            </div>
          </div>
          <span class="text-xs text-slate-500 group-hover:text-brand-400 transition">→</span>
        `;
        container.appendChild(btn);
      });
    }

    filterSubjectTestsByQuery('');

    viewStack.push('tests');
  }

  // Test Selection & Hub
  async function selectTest(testId) {
    triggerHaptic('light');

    const testMeta = adminStore.testsMeta.find(t => t.id === testId);
    const accType = testMeta ? (testMeta.access_type || 'public') : 'public';

    if (accType === 'admin_only' && !state.isAdmin) {
      alert('Этот тест находится в режиме «Только админ» и доступен только администраторам.');
      return;
    }

    if (accType === 'private' && !state.isAdmin) {
      alert('Этот тест является приватным. Доступ открывается преподавателем или администратором (@issdm).');
      return;
    }

    if (accType === 'code' && !state.isAdmin && !state.unlockedCodeTests.has(testId)) {
      const codeEntered = prompt(`Тест «${testMeta ? testMeta.title : testId}» защищен паролем.\n\nВведите секретный код доступа:`);
      if (!codeEntered) return;

      let verified = false;
      if (testMeta && testMeta.access_code && testMeta.access_code.trim().toLowerCase() === codeEntered.trim().toLowerCase()) {
        verified = true;
      } else {
        try {
          const res = await fetch('/api/tests/verify_code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: state.userId, test_id: testId, code: codeEntered.trim() })
          });
          if (res.ok) verified = true;
        } catch(e) {}
      }

      if (!verified) {
        alert('❌ Неверный код доступа. Пожалуйста, проверьте код или обратитесь к @issdm.');
        return;
      }

      state.unlockedCodeTests.add(testId);
      try {
        localStorage.setItem('ohtest_unlocked_tests', JSON.stringify([...state.unlockedCodeTests]));
      } catch(e) {}
      alert('✓ Код принят! Доступ к тесту открыт.');
      openSubjectTests(state.activeSubjectId, state.activeSubjectTitle);
    }

    state.activeTestId = testId;
    const testData = BUNDLED_TESTS[testId];
    state.activeTestTitle = testData ? testData.title : testId;

    // Load original questions
    state.currentTestOriginalQuestions = testData ? [...testData.questions] : [];
    state.activeQuestions = [...state.currentTestOriginalQuestions];

    // Restore test specific errors & favorites from localStorage
    try {
      const errs = localStorage.getItem(`ohtest_errors_${testId}`);
      state.userErrors = errs ? new Set(JSON.parse(errs)) : new Set();
      const favs = localStorage.getItem(`ohtest_favs_${testId}`);
      state.favorites = favs ? new Set(JSON.parse(favs)) : new Set();
    } catch(e) {}

    openTestHub();

    // Live Server Sync
    try {
      const res = await fetch(`/api/tests/${testId}`);
      if (res.ok) {
        const liveData = await res.json();
        if (liveData && liveData.questions && liveData.questions.length > 0) {
          BUNDLED_TESTS[testId] = {
            title: liveData.title,
            questions: liveData.questions
          };
          state.activeTestTitle = liveData.title;
          state.currentTestOriginalQuestions = [...liveData.questions];
          state.activeQuestions = [...liveData.questions];
          document.getElementById('hub-test-title').innerText = state.activeTestTitle;
          document.getElementById('hub-q-count').innerText = state.currentTestOriginalQuestions.length;
        }
      }
    } catch(e) {}
  }

  function openTestHub() {
    state.homeActiveView = 'hub';
    hideAllViews();
    document.getElementById('view-hub').classList.remove('hidden');
    updateHeaderNavState();
    updateTelegramBackButton();

    document.getElementById('hub-test-title').innerText = state.activeTestTitle;
    document.getElementById('hub-q-count').innerText = state.currentTestOriginalQuestions.length;
    const hubErrEl = document.getElementById('hub-q-errors');
    if (hubErrEl) {
      hubErrEl.innerText = state.userErrors.size;
      hubErrEl.className = `text-xs font-bold font-mono ${state.userErrors.size > 0 ? 'text-rose-400' : 'text-slate-300'}`;
    }
    const hubFavEl = document.getElementById('hub-q-favs');
    if (hubFavEl) {
      hubFavEl.innerText = state.favorites.size;
      hubFavEl.className = `text-xs font-bold font-mono ${state.favorites.size > 0 ? 'text-amber-400' : 'text-slate-300'}`;
    }
    document.getElementById('hub-err-tag').innerText = state.userErrors.size;

    const hubBadge = document.getElementById('hub-test-badge');
    if (hubBadge) {
      const meta = adminStore.testsMeta.find(t => t.id === state.activeTestId);
      const acc = meta ? (meta.access_type || 'public') : 'public';
      if (acc === 'code') {
        hubBadge.innerText = 'Доступ по коду';
        hubBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium';
      } else if (acc === 'private') {
        hubBadge.innerText = 'Приватный';
        hubBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20 font-medium';
      } else if (acc === 'admin_only') {
        hubBadge.innerText = 'Только админ';
        hubBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 font-medium';
      } else {
        hubBadge.innerText = 'Доступен';
        hubBadge.className = 'text-xs px-2.5 py-0.5 rounded-full bg-brand-500/10 text-brand-400 border border-brand-500/20 font-medium';
      }
    }

    updateHubResumeButton();
    viewStack.push('hub');
  }

  // Quiz Solver Modes
  function openTrainingSelectorModal() {
    triggerHaptic('light');
    const modal = document.getElementById('modal-training-select');
    const container = document.getElementById('training-options-list');
    const totalQ = state.currentTestOriginalQuestions.length;

    const counts = [10, 20, 30, 50].filter(c => c < totalQ);
    counts.push(totalQ);

    container.innerHTML = '';
    counts.forEach(count => {
      const btn = document.createElement('button');
      btn.className = "p-3 rounded-2xl bg-app-surface border border-app-border hover:border-brand-500 text-center active:scale-95 transition group";
      const isAll = (count === totalQ);
      btn.onclick = () => {
        closeTrainingSelectorModal();
        startTrainingWithCount(count);
      };
      btn.innerHTML = `
        <div class="text-base font-extrabold text-white group-hover:text-brand-300 font-mono">${isAll ? 'Все' : count}</div>
        <div class="text-[10px] text-slate-400">${isAll ? `${totalQ} вопр.` : 'вопросов'}</div>
      `;
      container.appendChild(btn);
    });

    modal.classList.remove('hidden');
  }

  function closeTrainingSelectorModal() {
    document.getElementById('modal-training-select').classList.add('hidden');
  }

  function startTrainingWithCount(count) {
    state.trainingCount = count;
    startQuizMode('training');
  }

  function startQuizMode(mode) {
    // If starting a new mode and an unfinished attempt exists for this test: prompt confirmation!
    if (mode !== 'errors_solve' && state.activeAttempt && state.activeAttempt.testId === state.activeTestId) {
      const qNum = (state.activeAttempt.qIndex || 0) + 1;
      const totalQ = state.activeAttempt.total || state.activeQuestions.length;
      const confirmed = confirm(`У вас есть незавершённая попытка в этом тесте (вопрос ${qNum} из ${totalQ}). Начать заново? Текущий прогресс будет сброшен.`);
      if (!confirmed) return;
      state.activeAttempt = null;
      localStorage.removeItem('ohtest_active_attempt');
      renderActiveAttemptBanner();
      updateHubResumeButton();
    }

    triggerHaptic('light');

    if (mode === 'errors_solve') {
      const errQs = state.currentTestOriginalQuestions.filter(q => state.userErrors.has(q.id));
      if (errQs.length === 0) {
        alert('В этом тесте у вас нет нерешенных ошибок. Отличный результат!');
        return;
      }
      state.activeQuestions = errQs.map(q => ({...q}));
    } else {
      let qs = state.currentTestOriginalQuestions.map(q => ({...q}));
      if (mode === 'normal') {
        state.activeQuestions = qs;
      } else if (mode === 'random') {
        state.activeQuestions = qs.sort(() => Math.random() - 0.5);
      } else if (mode === 'reverse') {
        state.activeQuestions = qs.reverse();
      } else if (mode === 'training' || mode === 'mini10') {
        const count = state.trainingCount || 10;
        state.activeQuestions = qs.sort(() => Math.random() - 0.5).slice(0, count);
      }
    }

    state.currentMode = mode;
    state.userAnswers = {};
    state.revealedAnswers = new Set();
    state.currentQIndex = 0;
    state.homeActiveView = 'solver';

    hideAllViews();
    document.getElementById('view-solver').classList.remove('hidden');
    document.getElementById('btn-grid-modal').classList.remove('hidden');
    document.getElementById('btn-finish-early').classList.remove('hidden');
    updateTelegramBackButton();

    const modeNames = {
      normal: 'Контроль (по порядку)',
      random: 'Контроль (вразброс)',
      reverse: 'Контроль (с конца)',
      training: `⚡ Тренировка (${state.activeQuestions.length} вопр.)`,
      mini10: `⚡ Тренировка (${state.activeQuestions.length} вопр.)`,
      errors_solve: 'Разбор ошибок'
    };
    document.getElementById('solver-mode-tag').innerText = modeNames[mode] || 'Контрольный тест';
    updateHeaderNavState();

    // Start timer
    state.timerSeconds = 0;
    clearInterval(state.timerInterval);
    state.timerInterval = setInterval(() => {
      state.timerSeconds++;
      const mins = String(Math.floor(state.timerSeconds / 60)).padStart(2, '0');
      const secs = String(state.timerSeconds % 60).padStart(2, '0');
      document.getElementById('solver-timer').innerText = `⏱ ${mins}:${secs}`;
    }, 1000);

    saveActiveAttemptState();
    renderCurrentQuestion();
    viewStack.push('solver');
  }

  // SOLVER QUESTION RENDERER (NO EXPLANATION POPUP!)
  function renderCurrentQuestion() {
    const q = state.activeQuestions[state.currentQIndex];
    const total = state.activeQuestions.length;

    document.getElementById('solver-counter').innerText = `Вопрос ${state.currentQIndex + 1} из ${total}`;
    document.getElementById('solver-q-num-pill').innerText = `ВОПРОС #${q.id}`;
    document.getElementById('solver-q-text').innerText = q.question;
    document.getElementById('solver-bar').style.width = `${((state.currentQIndex + 1) / total) * 100}%`;
    document.getElementById('solver-prev-btn').disabled = (state.currentQIndex === 0);

    const nextBtn = document.getElementById('solver-next-btn');
    if (state.currentQIndex === total - 1) {
      nextBtn.innerHTML = 'Завершить';
      nextBtn.className = "px-6 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white active:scale-95 transition shadow-lg shadow-brand-600/30";
    } else {
      nextBtn.innerHTML = 'Далее →';
      nextBtn.className = "px-6 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-xs font-bold text-white active:scale-95 transition shadow-lg shadow-brand-600/30";
    }

    updateFavUI(isQuestionFavorited(q.id));

    const ans = state.userAnswers[q.id];
    const isRevealed = state.revealedAnswers.has(q.id);

    const showBtnText = document.getElementById('solver-btn-show-text');
    if (isRevealed || ans !== undefined) {
      showBtnText.innerText = isRevealed ? '✓ Ответ открыт' : '✓ Вы ответили';
    } else {
      showBtnText.innerText = 'Показать ответ';
    }
    const answerNote = document.getElementById('solver-answer-note');
    if (answerNote) {
      answerNote.innerText = isRevealed
        ? 'Вопрос добавлен в «Ошибки» для повторения.'
        : 'Неверный ответ или открытый ответ попадёт в «Ошибки» для повторения.';
      answerNote.classList.toggle('text-amber-300', isRevealed);
      answerNote.classList.toggle('text-slate-400', !isRevealed);
    }

    // Render Options with unmistakable Green/Red Feedback. ZERO EXPLANATION BOX!
    const box = document.getElementById('solver-options-box');
    box.innerHTML = '';

    const correctIdx = getCorrectIndex(q);

    q.options.forEach((opt, idx) => {
      const btn = document.createElement('button');
      btn.className = "w-full text-left p-3.5 rounded-2xl border text-xs sm:text-sm font-medium transition-all duration-200 flex items-center justify-between space-x-3 active:scale-[0.99] ";

      const isUserChoice = (ans !== undefined && Number(ans) === Number(idx));
      const isCorrectOption = (Number(idx) === Number(correctIdx));

      let badgeChip = '';
      if (ans === undefined && !isRevealed) {
        // Unanswered: clickable
        btn.className += "bg-app-card border-app-border option-btn-unanswered text-slate-200";
        btn.onclick = () => selectOption(idx);
      } else {
        // Answered: GREEN ON CORRECT, RED ON WRONG + GREEN ON CORRECT!
        if (isCorrectOption) {
          btn.className += "option-btn-correct font-bold ring-2 ring-emerald-500/60 shadow-lg";
          badgeChip = `<span class="badge-correct px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 shrink-0">Верно ✓</span>`;
        } else if (isUserChoice && !isCorrectOption) {
          btn.className += "option-btn-wrong font-bold ring-2 ring-rose-500/60 shadow-lg";
          badgeChip = `<span class="badge-wrong px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40 shrink-0">Ваш ответ ✕</span>`;
        } else {
          btn.className += "option-btn-muted";
        }
      }

      const letters = ['А', 'Б', 'В', 'Г', 'Д', 'Е'][idx] || (idx + 1);
      let badgeIcon = letters;
      let badgeStyle = "bg-app-surface border-app-border text-slate-300";

      if (ans !== undefined || isRevealed) {
        if (isCorrectOption) {
          badgeIcon = '✓';
          badgeStyle = "badge-correct-icon bg-emerald-500 border-emerald-400 text-white font-black shadow-sm";
        } else if (isUserChoice) {
          badgeIcon = '✕';
          badgeStyle = "badge-wrong-icon bg-rose-500 border-rose-400 text-white font-black shadow-sm";
        }
      }

      btn.innerHTML = `
        <div class="flex items-start space-x-3 flex-1 min-w-0">
          <span class="w-6 h-6 rounded-full border flex items-center justify-center text-xs font-mono shrink-0 mt-0.5 ${badgeStyle}">${badgeIcon}</span>
          <span class="leading-snug flex-1">${opt}</span>
        </div>
        ${badgeChip}
      `;
      box.appendChild(btn);
    });

    saveActiveAttemptState();
  }

  function selectOption(idx) {
    const q = state.activeQuestions[state.currentQIndex];
    if (state.userAnswers[q.id] !== undefined) return; // Prevent double select
    state.userAnswers[q.id] = idx;

    const correctIdx = getCorrectIndex(q);
    const isCorrect = (Number(idx) === Number(correctIdx));

    if (isCorrect) {
      try { triggerHaptic('success'); } catch(e) {}
      state.userErrors.delete(q.id);
      state.userErrors.delete(String(q.id));
    } else {
      try { triggerHaptic('error'); } catch(e) {}
      // IMMEDIATELY RECORD ERROR TO STATE & LOCALSTORAGE AT THE MOMENT OF SELECTION!
      state.userErrors.delete(String(q.id));
      state.userErrors.add(q.id);
      try {
        const resolvedKey = `ohtest_resolved_errors_${state.activeTestId}`;
        const resolved = JSON.parse(localStorage.getItem(resolvedKey) || '[]').filter(id => id != q.id);
        localStorage.setItem(resolvedKey, JSON.stringify(resolved));
      } catch(e) {}
      try {
        fetch('/api/errors/record', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: state.userId,
            test_id: state.activeTestId,
            question_id: q.id,
            user_answer: idx
          })
        }).catch(() => {});
      } catch(e) {}
    }

    try {
      localStorage.setItem(`ohtest_errors_${state.activeTestId}`, JSON.stringify([...state.userErrors]));
    } catch(e) {}

    // Update error counters immediately
    try {
      const hubErrors = document.getElementById('hub-q-errors');
      if (hubErrors) hubErrors.innerText = state.userErrors.size;
      const hubErrTag = document.getElementById('hub-err-tag');
      if (hubErrTag) hubErrTag.innerText = state.userErrors.size;
      updateProfileErrorBadge(getAllSavedErrors().length);
    } catch(e) {}

    renderCurrentQuestion();
  }

  function showCurrentAnswer() {
    triggerHaptic('light');
    const q = state.activeQuestions[state.currentQIndex];
    if (state.userAnswers[q.id] === undefined && !state.userErrors.has(q.id)) {
      state.userErrors.add(q.id);
      try {
        localStorage.setItem(`ohtest_errors_${state.activeTestId}`, JSON.stringify([...state.userErrors]));
        fetch('/api/errors/record', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: state.userId,
            test_id: state.activeTestId,
            question_id: q.id,
            user_answer: null
          })
        }).catch(() => {});
      } catch(e) {}

      const hubErrors = document.getElementById('hub-q-errors');
      if (hubErrors) hubErrors.innerText = state.userErrors.size;
      const hubErrTag = document.getElementById('hub-err-tag');
      if (hubErrTag) hubErrTag.innerText = state.userErrors.size;
      updateProfileErrorBadge(getAllSavedErrors().length);
    }
    state.revealedAnswers.add(q.id);
    renderCurrentQuestion();
  }

  function handleNextOrFinish() {
    const total = state.activeQuestions.length;
    if (state.currentQIndex === total - 1) {
      requestFinishQuiz();
    } else {
      nextQuestion();
    }
  }

  function nextQuestion() {
    triggerHaptic('light');
    if (state.currentQIndex < state.activeQuestions.length - 1) {
      state.currentQIndex++;
      renderCurrentQuestion();
    }
  }

  function prevQuestion() {
    triggerHaptic('light');
    if (state.currentQIndex > 0) {
      state.currentQIndex--;
      renderCurrentQuestion();
    }
  }

  // Confirmation Before Finish
  function requestFinishQuiz() {
    triggerHaptic('light');
    const answered = Object.keys(state.userAnswers).length;
    const total = state.activeQuestions.length;
    const unanswered = Math.max(0, total - answered);
    const allAttempted = state.activeQuestions.every(q =>
      state.userAnswers[q.id] !== undefined || state.revealedAnswers.has(q.id)
    );
    if (state.currentMode === 'errors_solve' && allAttempted) {
      doFinishQuiz();
      return;
    }
    const textEl = document.getElementById('confirm-finish-text');
    if (textEl) {
      if (unanswered > 0) {
        textEl.innerText = `Вы ответили на ${answered} из ${total} вопросов (пропущено: ${unanswered}). Завершить тест и подвести итоги?`;
      } else {
        textEl.innerText = `Вы ответили на все ${total} вопросов теста! Завершить и подвести итоги?`;
      }
    }
    const modal = document.getElementById('modal-confirm-finish');
    if (modal) modal.classList.remove('hidden');
  }

  function closeFinishModal() {
    triggerHaptic('light');
    const modal = document.getElementById('modal-confirm-finish');
    if (modal) modal.classList.add('hidden');
  }

  function doFinishQuiz() {
    try {
      closeFinishModal();
      clearInterval(state.timerInterval);
      triggerHaptic('success');

      hideAllViews();
      state.homeActiveView = 'result';
      const resultView = document.getElementById('view-result');
      if (resultView) resultView.classList.remove('hidden');
      updateHeaderNavState();
      updateTelegramBackButton();

      let correct = 0;
      const wrongQuestionIds = [];
      const total = state.activeQuestions.length;

      state.activeQuestions.forEach(q => {
        const correctIdx = getCorrectIndex(q);
        const ans = state.userAnswers[q.id];
        if (ans !== undefined && Number(ans) === Number(correctIdx)) {
          correct++;
        } else if (ans !== undefined) {
          wrongQuestionIds.push(q.id);
          state.userErrors.add(q.id);
        }
      });

      const revealedUnansweredCount = state.activeQuestions.filter(q =>
        state.userAnswers[q.id] === undefined && state.revealedAnswers.has(q.id)
      ).length;
      const answeredCount = Object.keys(state.userAnswers).length + revealedUnansweredCount;
      const errorsCount = wrongQuestionIds.length + revealedUnansweredCount;
      const skippedCount = Math.max(0, total - answeredCount);
      const pct = total > 0 ? Math.round((correct / total) * 100) : 0;

      // Persist error set to localStorage
      try {
        localStorage.setItem(`ohtest_errors_${state.activeTestId}`, JSON.stringify([...state.userErrors]));
      } catch(e) {}

      // Update counters
      try {
        const hubErr = document.getElementById('hub-q-errors');
        if (hubErr) hubErr.innerText = state.userErrors.size;
        const hubErrTag = document.getElementById('hub-err-tag');
        if (hubErrTag) hubErrTag.innerText = state.userErrors.size;
        updateProfileErrorBadge(getAllSavedErrors().length);
      } catch(e) {}

      const resPct = document.getElementById('result-percent');
      if (resPct) resPct.innerText = `${pct}%`;
      const resCounts = document.getElementById('result-counts');
      if (resCounts) resCounts.innerText = `${correct} из ${total} правильно${skippedCount > 0 ? ` (пропущено: ${skippedCount})` : ''}`;
      const resErrors = document.getElementById('result-errors');
      if (resErrors) resErrors.innerText = `${errorsCount}`;

      const mins = String(Math.floor(state.timerSeconds / 60)).padStart(2, '0');
      const secs = String(state.timerSeconds % 60).padStart(2, '0');
      const resTime = document.getElementById('result-time');
      if (resTime) resTime.innerText = `${mins}:${secs}`;

      // Clear active attempt so it no longer prompts resume
      if (state.currentMode !== 'errors_solve' && state.currentMode !== 'all_favs') {
        state.activeAttempt = null;
        try { localStorage.removeItem('ohtest_active_attempt'); } catch(e) {}
        renderActiveAttemptBanner();
        updateHubResumeButton();
      }

      // Snapshot & history
      try {
        const qSnapshot = state.activeQuestions.map(q => ({
          id: q.id,
          question: q.question,
          options: q.options,
          correct: getCorrectIndex(q),
          userAnswer: state.userAnswers[q.id]
        }));

        state.historyAttempts.unshift({
          date: 'Только что',
          title: state.activeTestTitle,
          testId: state.activeTestId,
          score: `${correct}/${total} (${pct}%)`,
          total: total,
          correct: correct,
          errors: errorsCount,
          skipped: skippedCount,
          pct: pct,
          mode: state.currentMode,
          duration: state.timerSeconds,
          questionsSnapshot: qSnapshot
        });
        localStorage.setItem('ohtest_history', JSON.stringify(state.historyAttempts.slice(0, 50)));
        const profAtt = document.getElementById('profile-attempts-count');
        if (profAtt) profAtt.innerText = state.historyAttempts.length;
      } catch(e) {}

      // Backend attempt record (non-blocking)
      try {
        fetch('/api/attempts/record', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: state.userId,
            test_id: state.activeTestId,
            correct: correct,
            answered: answeredCount,
            duration: state.timerSeconds,
            mode: state.currentMode
          })
        }).catch(() => {});
      } catch(e) {}

      // Action buttons
      const btnBox = document.getElementById('result-buttons-container');
      const msgBanner = document.getElementById('result-msg-banner');
      const iconBox = document.getElementById('result-icon-box');
      if (btnBox) btnBox.innerHTML = '';

      if (state.currentMode === 'all_favs') {
        const remainingFavorites = state.favoriteReviewQueue.reduce((count, testId) =>
          count + getAllSavedFavorites().filter(item => item.testId === testId).length, 0
        );
        const resTitle = document.getElementById('result-title');
        if (resTitle) resTitle.innerText = 'Тренировка избранного завершена!';
        const resSub = document.getElementById('result-subtitle');
        if (resSub) resSub.innerText = 'Вопросы из избранного';
        if (iconBox) iconBox.innerHTML = `<svg class="w-8 h-8 text-amber-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/></svg>`;
        if (msgBanner) {
          msgBanner.classList.remove('hidden');
          msgBanner.className = 'p-3.5 rounded-2xl bg-amber-950/40 border border-amber-500/30 text-amber-200 text-xs';
          msgBanner.innerText = remainingFavorites > 0
            ? `Группа завершена. В очереди ещё ${remainingFavorites} вопросов из избранного.`
            : 'Все группы избранного пройдены. Сохранённые вопросы остались в избранном.';
        }
        if (btnBox) {
          btnBox.innerHTML = remainingFavorites > 0
            ? `<button onclick="startNextFavoriteGroup()" class="w-full py-3.5 rounded-2xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs active:scale-[0.98] transition flex items-center justify-center gap-2">Следующая группа (${remainingFavorites})</button>`
            : `<button onclick="finishFavoriteReview()" class="btn-glass-secondary w-full py-3.5 rounded-2xl font-semibold text-xs active:scale-[0.98] transition">К избранному</button>`;
        }
      } else if (state.currentMode === 'errors_solve') {
        const resTitle = document.getElementById('result-title');
        if (resTitle) resTitle.innerText = "Разбор ошибок завершен!";
        const resSub = document.getElementById('result-subtitle');
        if (resSub) resSub.innerText = "Работа над ошибками";
        if (iconBox) iconBox.innerHTML = `<svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`;

        // Mark resolved errors
        state.activeQuestions.forEach(q => {
          const cIdx = getCorrectIndex(q);
          if (state.userAnswers[q.id] !== undefined && Number(state.userAnswers[q.id]) === Number(cIdx)) {
            state.userErrors.delete(q.id);
            state.userErrors.delete(String(q.id));
            try {
              const resKey = `ohtest_resolved_errors_${state.activeTestId}`;
              const curRes = new Set(JSON.parse(localStorage.getItem(resKey) || '[]'));
              curRes.add(q.id);
              localStorage.setItem(resKey, JSON.stringify([...curRes]));
            } catch(e) {}
            try {
              fetch('/api/errors/resolve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: state.userId, test_id: state.activeTestId, question_id: q.id })
              }).catch(() => {});
            } catch(e) {}
          }
        });

        try {
          localStorage.setItem(`ohtest_errors_${state.activeTestId}`, JSON.stringify([...state.userErrors]));
        } catch(e) {}

        const allUnresolvedErrors = getAllSavedErrors();
        const remainingErrors = allUnresolvedErrors.filter(error => error.testId === state.activeTestId).length;
        const remainingAllErrors = allUnresolvedErrors.length;
        const remainingOtherTestErrors = Math.max(0, remainingAllErrors - remainingErrors);
        if (msgBanner) {
          msgBanner.classList.remove('hidden');
          if (remainingErrors === 0) {
            msgBanner.className = "p-3.5 rounded-2xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 text-xs space-y-1";
            msgBanner.innerHTML = `<div class="font-bold flex items-center gap-1.5"><svg class="w-4 h-4 text-emerald-400 shrink-0 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>Отличная работа!</div><p class="text-[11px] text-emerald-200/90 leading-relaxed">Ошибки этого теста успешно разобраны и усвоены.${remainingAllErrors > 0 ? ` Осталось ошибок в других тестах: ${remainingAllErrors}.` : ''}</p>`;
            if (btnBox) {
              btnBox.innerHTML = `
                ${remainingAllErrors > 0 ? `<button onclick="startAllErrorsSession()" class="w-full py-3.5 rounded-2xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs active:scale-[0.98] transition flex items-center justify-center gap-2">Продолжить разбор ошибок (${remainingAllErrors})</button>` : ''}
                <button onclick="startQuizMode('normal')" class="btn-brand w-full py-3.5 rounded-2xl text-white font-bold text-xs active:scale-[0.98] transition shadow-lg shadow-brand-500/25 flex items-center justify-center gap-2">Пройти полный тест заново</button>
                <button onclick="returnToProfileErrors()" class="btn-glass-secondary w-full py-3.5 rounded-2xl font-semibold text-xs active:scale-[0.98] transition flex items-center justify-center gap-2">
                  <svg class="w-4 h-4 text-slate-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
                  <span>К списку ошибок в профиле</span>
                </button>
              `;
            }
          } else {
            msgBanner.className = "p-3.5 rounded-2xl bg-amber-950/60 border border-amber-500/40 text-amber-300 text-xs space-y-1";
            msgBanner.innerHTML = `<div class="font-bold flex items-center gap-1.5"><svg class="w-4 h-4 text-amber-400 shrink-0 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>Остались нерешенные вопросы</div><p class="text-[11px] text-amber-200/90 leading-relaxed">Исправлено: ${correct} из ${total}. Осталось ${remainingErrors} ошибок в этом тесте.${remainingOtherTestErrors > 0 ? ` В других тестах: ${remainingOtherTestErrors}.` : ''}</p>`;
            if (btnBox) {
              btnBox.innerHTML = `
                <button onclick="startQuizMode('errors_solve')" class="w-full py-3.5 rounded-2xl bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white font-bold text-xs active:scale-[0.98] transition shadow-lg shadow-rose-600/30 flex items-center justify-center gap-2">Повторить оставшиеся ошибки (${remainingErrors})</button>
                ${remainingOtherTestErrors > 0 ? `<button onclick="startAllErrorsSession()" class="w-full py-3.5 rounded-2xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs active:scale-[0.98] transition flex items-center justify-center gap-2">Перейти к ошибкам других тестов (${remainingOtherTestErrors})</button>` : ''}
                <button onclick="startQuizMode('normal')" class="btn-brand w-full py-3.5 rounded-2xl text-white font-bold text-xs active:scale-[0.98] transition shadow-lg shadow-brand-500/25 flex items-center justify-center gap-2">Пройти весь тест заново</button>
                <button onclick="returnToProfileErrors()" class="btn-glass-secondary w-full py-3.5 rounded-2xl font-semibold text-xs active:scale-[0.98] transition flex items-center justify-center gap-2">
                  <svg class="w-4 h-4 text-slate-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
                  <span>К списку ошибок в профиле</span>
                </button>
              `;
            }
          }
        }
      } else {
        if (msgBanner) msgBanner.classList.add('hidden');
        // Count actual unsolved errors belonging to this test
        const testErrorsCount = state.currentTestOriginalQuestions.filter(q => state.userErrors.has(q.id)).length;
        const isPerfect = (total > 0 && correct === total);

        if (isPerfect) {
          const resTitle = document.getElementById('result-title');
          if (resTitle) resTitle.innerText = "Идеальный результат!";
          const resSub = document.getElementById('result-subtitle');
          if (resSub) resSub.innerText = "100% правильных ответов";
          if (iconBox) iconBox.innerHTML = `<svg class="w-8 h-8 text-amber-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"/></svg>`;
          if (btnBox) {
            btnBox.innerHTML = `
              <button onclick="startQuizMode('normal')" class="btn-brand w-full py-3.5 rounded-2xl text-white font-bold text-xs active:scale-[0.98] transition shadow-lg shadow-brand-500/25 flex items-center justify-center gap-2">Пройти ещё раз</button>
              <button onclick="openTestHub()" class="btn-glass-secondary w-full py-3.5 rounded-2xl font-semibold text-xs active:scale-[0.98] transition flex items-center justify-center gap-2">
                <svg class="w-4 h-4 text-slate-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
                <span>В меню теста</span>
              </button>
              <button onclick="switchTab('home')" class="w-full py-2.5 rounded-xl text-slate-400 hover:text-white font-medium text-xs transition">На главную</button>
            `;
          }
        } else {
          const resTitle = document.getElementById('result-title');
          if (resTitle) resTitle.innerText = "Тест завершен!";
          const resSub = document.getElementById('result-subtitle');
          if (resSub) resSub.innerText = "Контрольный результат";
          if (iconBox) iconBox.innerHTML = `<svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>`;
          if (btnBox) {
            let errorButtonHtml = '';
            if (testErrorsCount > 0) {
              errorButtonHtml = `
                <button onclick="startQuizMode('errors_solve')" class="w-full py-3.5 rounded-2xl bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white font-bold text-xs active:scale-[0.98] transition shadow-lg shadow-rose-600/30 flex items-center justify-center gap-2">
                  Разобрать ошибки (${testErrorsCount})
                </button>
              `;
            }
            btnBox.innerHTML = `
              ${errorButtonHtml}
              <button onclick="startQuizMode('normal')" class="btn-brand w-full py-3.5 rounded-2xl text-white font-bold text-xs active:scale-[0.98] transition shadow-lg shadow-brand-500/25 flex items-center justify-center gap-2">
                Пройти заново
              </button>
              <button onclick="openTestHub()" class="btn-glass-secondary w-full py-3.5 rounded-2xl font-semibold text-xs active:scale-[0.98] transition flex items-center justify-center gap-2">
                <svg class="w-4 h-4 text-slate-400 group-hover:text-white transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
                <span>В меню теста</span>
              </button>
            `;
          }
        }
      }
    } catch(err) {
      console.error('doFinishQuiz execution error:', err);
      hideAllViews();
      const resView = document.getElementById('view-result');
      if (resView) resView.classList.remove('hidden');
      updateHeaderNavState();
    }
  }

  // Matrix Modal
  function toggleMatrixModal() {
    triggerHaptic('light');
    const modal = document.getElementById('modal-matrix');
    if (modal.classList.contains('hidden')) {
      const grid = document.getElementById('matrix-grid-box');
      grid.innerHTML = '';
      state.activeQuestions.forEach((q, idx) => {
        const item = document.createElement('button');
        const ans = state.userAnswers[q.id];
        const isRevealed = state.revealedAnswers.has(q.id);
        let color = "bg-app-surface border-app-border text-slate-300";
        let marker = '';
        let status = 'не отвечен';

        if (ans !== undefined) {
          if (Number(ans) === Number(getCorrectIndex(q))) {
            color = "bg-emerald-600 border-emerald-500 text-white font-bold";
            marker = '✓';
            status = 'верно';
          } else {
            color = "bg-rose-600 border-rose-500 text-white font-bold";
            marker = '×';
            status = 'ошибка';
          }
        } else if (isRevealed) {
          color = "bg-amber-500/20 border-amber-400 text-amber-200 font-bold";
          marker = '!';
          status = 'ответ открыт, добавлен в ошибки';
        }

        if (idx === state.currentQIndex) {
          color += " ring-2 ring-brand-400 ring-offset-2 ring-offset-app-card";
        }

        item.className = `relative p-3 rounded-xl border text-xs font-mono font-bold transition active:scale-95 ${color}`;
        item.setAttribute('aria-label', `Вопрос ${idx + 1}: ${status}`);
        item.title = `Вопрос ${idx + 1}: ${status}`;
        item.innerHTML = `${idx + 1}${marker ? `<span class="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-app-card border border-current text-[10px] leading-[14px]">${marker}</span>` : ''}`;
        item.onclick = () => {
          state.currentQIndex = idx;
          renderCurrentQuestion();
          toggleMatrixModal();
        };
        grid.appendChild(item);
      });
      modal.classList.remove('hidden');
    } else {
      modal.classList.add('hidden');
    }
  }

  // Start From Modal
  function openStartFromModal() {
    triggerHaptic('light');
    document.getElementById('modal-start-from').classList.remove('hidden');
  }
  function closeStartFromModal() {
    document.getElementById('modal-start-from').classList.add('hidden');
  }
  function confirmStartFrom() {
    const num = parseInt(document.getElementById('start-from-input').value) || 1;
    closeStartFromModal();
    startQuizMode('normal');
    state.currentQIndex = Math.max(0, Math.min(num - 1, state.activeQuestions.length - 1));
    renderCurrentQuestion();
  }

  function confirmResetErrors() {
    triggerHaptic('light');
    if (confirm('Вы уверены, что хотите сбросить историю ошибок по этому тесту?')) {
      state.userErrors.clear();
      localStorage.removeItem(`ohtest_errors_${state.activeTestId}`);
      try {
        fetch('/api/errors/clear', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: state.userId, test_id: state.activeTestId })
        }).catch(() => {});
      } catch(e) {}
      document.getElementById('hub-q-errors').innerText = '0';
      document.getElementById('hub-err-tag').innerText = '0';
      updateProfileErrorBadge(getAllSavedErrors().length);
      alert('История ошибок теста успешно очищена!');
    }
  }

  // Favorites
  function isQuestionFavorited(qid) {
    if (qid === undefined || qid === null) return false;
    if (!state.favorites) return false;
    return state.favorites.has(qid) || state.favorites.has(Number(qid)) || state.favorites.has(String(qid));
  }

  function toggleCurrentFavorite() {
    const q = state.activeQuestions[state.currentQIndex];
    if (!q) return;
    triggerHaptic('light');

    const qid = q.id;
    const hasFav = isQuestionFavorited(qid);

    if (hasFav) {
      state.favorites.delete(qid);
      state.favorites.delete(Number(qid));
      state.favorites.delete(String(qid));
      showToast('Удалено из избранного');
    } else {
      state.favorites.add(qid);
      showToast('★ Добавлено в избранное');
    }

    try {
      localStorage.setItem(`ohtest_favs_${state.activeTestId}`, JSON.stringify([...state.favorites]));
    } catch(e) {}

    fetch('/api/user/favorite', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ test_id: state.activeTestId, question_id: qid, is_favorite: !hasFav })
    }).catch(() => {});

    const currentlyFav = isQuestionFavorited(qid);
    updateFavUI(currentlyFav);

    const hubFavsEl = document.getElementById('hub-q-favs');
    if (hubFavsEl) {
      hubFavsEl.innerText = state.favorites.size;
      hubFavElClass(hubFavsEl, state.favorites.size);
    }
    const profFavCountEl = document.getElementById('profile-fav-count');
    if (profFavCountEl) {
      profFavCountEl.innerText = getAllSavedFavorites().length;
    }
  }

  function hubFavElClass(el, count) {
    if (!el) return;
    el.className = `text-xs font-bold font-mono ${count > 0 ? 'text-amber-400' : 'text-slate-300'}`;
  }

  function updateFavUI(isFav) {
    const btn = document.getElementById('solver-fav-btn');
    const icon = document.getElementById('solver-fav-icon');
    if (icon) {
      if (isFav) {
        icon.setAttribute('fill', '#fbbf24'); // amber-400
        icon.setAttribute('stroke', '#fbbf24');
        icon.classList.remove('text-slate-400');
        icon.classList.add('text-amber-400');
      } else {
        icon.setAttribute('fill', 'none');
        icon.setAttribute('stroke', 'currentColor');
        icon.classList.remove('text-amber-400');
        icon.classList.add('text-slate-400');
      }
    }
    if (btn) {
      if (isFav) {
        btn.className = 'w-8 h-8 rounded-full bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 active:scale-90 transition';
      } else {
        btn.className = 'w-8 h-8 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-slate-400 hover:text-amber-400 active:scale-90 transition';
      }
    }
    const headerIcon = document.getElementById('header-fav-icon');
    if (headerIcon) {
      if (isFav) {
        headerIcon.classList.add('text-amber-400', 'fill-amber-400');
      } else {
        headerIcon.classList.remove('text-amber-400', 'fill-amber-400');
      }
    }
  }

  // Flashcards (always loads all test questions + Quizlet-style touch swipe gestures)
  let touchStartX = 0;
  let touchStartY = 0;
  let touchCurrentX = 0;
  let touchIsDragging = false;
  let fcGesturesAttached = false;

  let fcLearned = [];
  let fcReview = [];
  let fcHistoryStack = []; // stores { index, question, known }
  let lastFlipTime = 0;
  let fcShuffleEnabled = false;
  let fcStarredOnlyEnabled = false;

  function initFlashcardGestures() {
    const card = document.getElementById('fc-card');
    if (!card || fcGesturesAttached) return;
    fcGesturesAttached = true;

    let touchStartX = 0;
    let touchStartY = 0;
    let touchCurrentX = 0;
    let touchIsDragging = false;

    card.addEventListener('touchstart', (e) => {
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchCurrentX = touchStartX;
      touchIsDragging = true;
      card.style.transition = 'none';
    }, { passive: true });

    card.addEventListener('touchmove', (e) => {
      if (!touchIsDragging) return;
      touchCurrentX = e.touches[0].clientX;
      const dx = touchCurrentX - touchStartX;
      const dy = e.touches[0].clientY - touchStartY;
      if (Math.abs(dx) > Math.abs(dy)) {
        const rot = (dx / 18);
        const flipRot = fcFlipped ? 180 : 0;
        card.style.transform = `translateX(${dx}px) rotate(${rot}deg) rotateY(${flipRot}deg)`;
      }
    }, { passive: true });

    card.addEventListener('touchend', (e) => {
      if (!touchIsDragging) return;
      touchIsDragging = false;
      const dx = touchCurrentX - touchStartX;
      const dy = e.changedTouches[0] ? (e.changedTouches[0].clientY - touchStartY) : 0;
      card.style.transition = 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)';

      if (Math.abs(dx) > 70) {
        const isRight = dx > 0;
        const flyX = isRight ? 450 : -450;
        const rot = isRight ? 25 : -25;
        const flipRot = fcFlipped ? 180 : 0;
        card.style.transform = `translateX(${flyX}px) rotate(${rot}deg) rotateY(${flipRot}deg)`;
        setTimeout(() => {
          card.style.transition = 'none';
          card.style.transform = fcFlipped ? 'rotateY(180deg)' : 'rotateY(0deg)';
          fcNext(isRight);
          setTimeout(() => {
            card.style.transition = 'transform 0.35s cubic-bezier(0.16, 1, 0.3, 1)';
          }, 30);
        }, 180);
      } else {
        // If it was just a tap without drag, let click event handle flipCard
        card.style.transform = fcFlipped ? 'rotateY(180deg)' : 'rotateY(0deg)';
      }
    });
  }

  function openFlashcards() {
    triggerHaptic('light');
    state.homeActiveView = 'flashcards';
    hideAllViews();
    document.getElementById('view-flashcards').classList.remove('hidden');
    updateHeaderNavState();
    updateTelegramBackButton();

    // Prepare Questions Deck
    setupFlashcardsDeck(false);

    document.getElementById('fc-active-deck').classList.remove('hidden');
    document.getElementById('fc-finish-screen').classList.add('hidden');

    renderFCCard();
    initFlashcardGestures();
    viewStack.push('flashcards');
  }

  function setupFlashcardsDeck(keepShuffle = false) {
    let pool = [...state.currentTestOriginalQuestions];
    if (fcStarredOnlyEnabled) {
      pool = pool.filter(q => isQuestionFavorited(q.id));
      if (pool.length === 0) {
        showToast('☆ В избранном нет вопросов. Показаны все карточки.');
        fcStarredOnlyEnabled = false;
        const starChk = document.getElementById('fc-opt-starred-only');
        if (starChk) starChk.checked = false;
        pool = [...state.currentTestOriginalQuestions];
      }
    }

    if (fcShuffleEnabled) {
      for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
      }
    }

    state.activeQuestions = pool;
    fcIndex = 0;
    fcLearned = [];
    fcReview = [];
    fcHistoryStack = [];
  }

  function renderFCCard() {
    if (!state.activeQuestions || state.activeQuestions.length === 0) {
      showFCFinishScreen();
      return;
    }

    const q = state.activeQuestions[fcIndex];
    fcFlipped = false;
    const card = document.getElementById('fc-card');
    if (card) {
      card.style.transition = 'none';
      card.style.transform = 'rotateY(0deg)';
    }

    const total = state.activeQuestions.length;
    document.getElementById('fc-counter').innerText = `${fcIndex + 1} / ${total}`;
    document.getElementById('fc-front-text').innerText = q.question;
    document.getElementById('fc-back-answer').innerText = getQuestionCorrectText(q);

    document.getElementById('fc-tag-known').innerText = fcLearned.length;
    document.getElementById('fc-tag-review').innerText = fcReview.length;

    // Update Star buttons (both front and back)
    const qid = q.id;
    const isFav = isQuestionFavorited(qid);
    const starBtn = document.getElementById('fc-star-btn');
    if (starBtn) {
      starBtn.innerText = isFav ? '★' : '☆';
      starBtn.className = `w-8 h-8 rounded-full flex items-center justify-center text-lg active:scale-90 transition ${isFav ? 'bg-amber-500/20 border border-amber-500/40 text-amber-400' : 'bg-white/5 border border-white/10 text-slate-400 hover:text-amber-300'}`;
    }
    const starBtnBack = document.getElementById('fc-star-btn-back');
    if (starBtnBack) {
      starBtnBack.innerText = isFav ? '★' : '☆';
      starBtnBack.className = `w-8 h-8 rounded-full flex items-center justify-center text-lg active:scale-90 transition ${isFav ? 'bg-amber-500/20 border border-amber-500/40 text-amber-400' : 'bg-white/5 border border-white/10 text-slate-400 hover:text-amber-300'}`;
    }

    // Prev Button State
    const prevBtn = document.getElementById('fc-btn-prev');
    if (prevBtn) {
      prevBtn.disabled = (fcHistoryStack.length === 0);
    }
  }

  function toggleFCCurrentStar() {
    const q = state.activeQuestions[fcIndex];
    if (!q) return;
    triggerHaptic('light');

    const qid = q.id;
    const hasFav = isQuestionFavorited(qid);

    if (hasFav) {
      state.favorites.delete(qid);
      state.favorites.delete(Number(qid));
      state.favorites.delete(String(qid));
      showToast('Удалено из избранного');
    } else {
      state.favorites.add(qid);
      showToast('★ Добавлено в избранное');
    }

    // Persist to localStorage
    try {
      const arr = Array.from(state.favorites);
      localStorage.setItem(`ohtest_favs_${state.activeTestId}`, JSON.stringify(arr));
    } catch(e) {
      console.warn('Failed saving favorites to localStorage:', e);
    }

    // Update global counters and badges
    const hubFavsEl = document.getElementById('hub-q-favs');
    if (hubFavsEl) {
      hubFavsEl.innerText = state.favorites.size;
      hubFavElClass(hubFavsEl, state.favorites.size);
    }
    const profFavsEl = document.getElementById('profile-fav-count');
    if (profFavsEl) profFavsEl.innerText = getAllSavedFavorites().length;
    updateFavUI(isQuestionFavorited(qid));

    renderFCCard();
  }

  function flipCard() {
    const now = Date.now();
    if (now - lastFlipTime < 280) return; // Prevent duplicate tap-flip
    lastFlipTime = now;
    triggerHaptic('light');
    fcFlipped = !fcFlipped;
    const c = document.getElementById('fc-card');
    if (!c) return;
    c.style.transition = 'transform 0.4s cubic-bezier(0.16, 1, 0.3, 1)';
    c.style.transform = fcFlipped ? 'rotateY(180deg)' : 'rotateY(0deg)';
  }

  function fcNext(known) {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
    const q = state.activeQuestions[fcIndex];
    fcHistoryStack.push({ index: fcIndex, question: q, known: known });

    if (known) {
      triggerHaptic('success');
      fcLearned.push(q);
    } else {
      triggerHaptic('light');
      fcReview.push(q);
    }

    document.getElementById('fc-tag-known').innerText = fcLearned.length;
    document.getElementById('fc-tag-review').innerText = fcReview.length;

    if (fcIndex < state.activeQuestions.length - 1) {
      fcIndex++;
      renderFCCard();
    } else {
      // Round Complete: Show Quizlet Summary Screen!
      showFCFinishScreen();
    }
  }

  function fcSkipNext() {
    triggerHaptic('light');
    const q = state.activeQuestions[fcIndex];
    fcHistoryStack.push({ index: fcIndex, question: q, known: null });

    if (fcIndex < state.activeQuestions.length - 1) {
      fcIndex++;
      renderFCCard();
    } else {
      showFCFinishScreen();
    }
  }

  function fcPrevCard() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
    if (fcHistoryStack.length === 0) return;
    triggerHaptic('light');
    const lastAction = fcHistoryStack.pop();

    if (lastAction.known === true) {
      const idx = fcLearned.lastIndexOf(lastAction.question);
      if (idx !== -1) fcLearned.splice(idx, 1);
    } else if (lastAction.known === false) {
      const idx = fcReview.lastIndexOf(lastAction.question);
      if (idx !== -1) fcReview.splice(idx, 1);
    }

    document.getElementById('fc-tag-known').innerText = fcLearned.length;
    document.getElementById('fc-tag-review').innerText = fcReview.length;

    fcIndex = Math.max(0, lastAction.index);
    renderFCCard();
  }

  function openFCOptionsModal() {
    triggerHaptic('light');
    const modal = document.getElementById('modal-fc-options');
    if (!modal) return;
    const shufChk = document.getElementById('fc-opt-shuffle');
    if (shufChk) shufChk.checked = fcShuffleEnabled;
    const starChk = document.getElementById('fc-opt-starred-only');
    if (starChk) starChk.checked = fcStarredOnlyEnabled;
    modal.classList.remove('hidden');
  }

  function closeFCOptionsModal() {
    triggerHaptic('light');
    const modal = document.getElementById('modal-fc-options');
    if (modal) modal.classList.add('hidden');
  }

  function toggleFCShuffle(enabled) {
    triggerHaptic('medium');
    fcShuffleEnabled = enabled;
    showToast(enabled ? '🔀 Карточки перемешаны' : 'Порядок карточек сброшен');
    setupFlashcardsDeck(false);
    renderFCCard();
  }

  function toggleFCStarredOnly(enabled) {
    triggerHaptic('medium');
    fcStarredOnlyEnabled = enabled;
    setupFlashcardsDeck(false);
    renderFCCard();
  }

  function fcRestartAllModal() {
    closeFCOptionsModal();
    fcRestartAll();
    showToast('🔄 Раунд начат заново');
  }

  function showFCFinishScreen() {
    triggerHaptic('success');
    document.getElementById('fc-active-deck').classList.add('hidden');
    document.getElementById('fc-finish-screen').classList.remove('hidden');

    document.getElementById('fc-done-known').innerText = fcLearned.length;
    document.getElementById('fc-done-review').innerText = fcReview.length;
    document.getElementById('fc-btn-review-count').innerText = fcReview.length;

    const repBtn = document.getElementById('fc-btn-repeat-review');
    if (fcReview.length === 0) {
      repBtn.classList.add('hidden');
    } else {
      repBtn.classList.remove('hidden');
    }
  }

  function fcRepeatReview() {
    if (fcReview.length === 0) return;
    triggerHaptic('light');
    state.activeQuestions = [...fcReview];
    fcIndex = 0;
    fcLearned = [];
    fcReview = [];
    fcHistoryStack = [];

    document.getElementById('fc-finish-screen').classList.add('hidden');
    document.getElementById('fc-active-deck').classList.remove('hidden');
    renderFCCard();
  }

  function fcRestartAll() {
    triggerHaptic('light');
    setupFlashcardsDeck(false);

    document.getElementById('fc-finish-screen').classList.add('hidden');
    document.getElementById('fc-active-deck').classList.remove('hidden');
    renderFCCard();
  }

  // LIVE SEARCH
  function openLiveSearch() {
    triggerHaptic('light');
    state.homeActiveView = 'search';
    hideAllViews();
    document.getElementById('view-search').classList.remove('hidden');
    updateHeaderNavState();
    updateTelegramBackButton();
    document.getElementById('live-search-input').value = '';
    handleLiveSearch();
    viewStack.push('search');
  }

  function clearSearchInput() {
    document.getElementById('live-search-input').value = '';
    handleLiveSearch();
  }

  function handleLiveSearch() {
    const val = document.getElementById('live-search-input').value.toLowerCase().trim();
    const box = document.getElementById('search-results-box');
    box.innerHTML = '';

    const matched = state.currentTestOriginalQuestions.filter(q => {
      if (!val) return true;
      return q.question.toLowerCase().includes(val) || String(q.id) === val;
    });

    document.getElementById('search-matches-pill').innerText = `${matched.length} найдено`;

    matched.forEach(q => {
      const card = document.createElement('div');
      card.className = "p-4 rounded-2xl bg-app-card border border-app-border space-y-2.5 cursor-pointer hover:border-brand-500/50 active:scale-[0.99] transition";
      card.onclick = () => openQuestionDetailModal(q, state.activeTestId, state.activeTestTitle);

      const correctText = getQuestionCorrectText(q);

      card.innerHTML = `
        <div class="flex items-center justify-between text-xs">
          <span class="font-mono font-bold text-brand-400">ВОПРОС #${q.id}</span>
          <span class="text-emerald-400 font-semibold text-[11px] truncate max-w-[200px]">✓ Ответ: ${correctText}</span>
        </div>
        <p class="text-xs sm:text-sm font-semibold text-white leading-normal line-clamp-3">${q.question}</p>
        <div class="pt-1 flex items-center justify-between text-[11px] text-slate-400">
          <span>Нажмите, чтобы просмотреть полностью</span>
          <span class="text-brand-400 font-bold">Просмотр ↗</span>
        </div>
      `;
      box.appendChild(card);
    });
  }

  // ==========================================
