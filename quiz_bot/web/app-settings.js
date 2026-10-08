// PRIVACY: TOGGLE HIDE IN LEADERBOARD
  async function toggleHideInRating(checked) {
    triggerHaptic('light');
    state.isHiddenInRating = checked;
    localStorage.setItem('ohtest_hide_rating', checked ? 'true' : 'false');
    if (!state.userId) {
      showToast(checked ? '🔒 Вы скрыты из рейтинга' : '👁️ Вы отображаетесь в рейтинге');
      return;
    }
    try {
      const res = await fetch('/api/user/toggle_rating_visibility', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: state.userId, is_hidden: checked })
      });
      if (res.ok) {
        showToast(checked ? '🔒 Вы скрыты из таблицы лидеров' : '👁️ Вы отображаетесь в таблице лидеров');
        if (state.activeProfileSubTab === 'rating') {
          renderRatingSubtab();
        }
      } else {
        showToast('Не удалось обновить статус на сервере');
      }
    } catch (e) {
      console.error('Error toggling rating visibility:', e);
      showToast(checked ? 'Скрыто локально' : 'Включено локально');
    }
  }

  // RESET RATING PROGRESS ON SERVER & LOCAL ATTEMPTS
  async function resetMyRatingProgress() {
    triggerHaptic('warning');
    if (!confirm('Вы уверены, что хотите сбросить свои результаты и рекорды в таблице лидеров на сервере?\n\nВаши сохранённые вопросы в «Избранном» останутся целы.')) {
      return;
    }
    triggerHaptic('heavy');
    try {
      if (state.userId) {
        const res = await fetch('/api/user/reset_rating', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: state.userId })
        });
        if (!res.ok) {
          showToast('Не удалось сбросить рейтинг на сервере');
          return;
        }
      }
      state.historyAttempts = [];
      state.activeAttempt = null;
      localStorage.removeItem('ohtest_history');
      localStorage.removeItem('ohtest_active_attempt');
      const attEl = document.getElementById('profile-attempts-count');
      if (attEl) attEl.innerText = '0';
      renderActiveAttemptBanner();
      updateHubResumeButton();
      if (state.activeProfileSubTab === 'rating') {
        renderRatingSubtab();
      } else if (state.activeProfileSubTab === 'history') {
        renderProfileSubtab('history');
      }
      showToast('✓ Ваши результаты в рейтинге сброшены!');
    } catch (e) {
      console.error('Error resetting rating:', e);
      showToast('Ошибка при сбросе рейтинга');
    }
  }

  // WORKING CLEAR CACHE FUNCTION (CLEARS LOCALSTORAGE + IN-MEMORY STATE + RESETS UI COUNTERS)
  function clearLocalAppCache() {
    if (confirm('Удалить локальные попытки, ошибки и избранное на этом устройстве? Серверная статистика и настройки сохранятся.')) {
      triggerHaptic('success');
      Object.keys(localStorage).filter(key =>
        /^ohtest_(history$|active_attempt$|errors_|favs_|resolved_errors_|fc_progress_)/.test(key)
      ).forEach(key => localStorage.removeItem(key));
      state.activeAttempt = null;
      state.historyAttempts = [];
      state.userErrors = new Set();
      state.favorites = new Set();
      state.userAnswers = {};
      state.revealedAnswers = new Set();
      state.timerSeconds = 0;
      clearInterval(state.timerInterval);
      state.activeQuestions = [...state.currentTestOriginalQuestions];
      state.currentQIndex = 0;
      fcLearned = [];
      fcReview = [];
      fcHistoryStack = [];
      if (['solver', 'result', 'flashcards'].includes(state.homeActiveView)) state.homeActiveView = 'hub';

      // Re-render UI
      renderActiveAttemptBanner();
      updateHubResumeButton();

      // Reset Profile stats
      document.getElementById('profile-attempts-count').innerText = '0';
      document.getElementById('profile-fav-count').innerText = '0';
      updateProfileErrorBadge(0);
      renderProfileSubtab(state.activeProfileSubTab || 'favs');

      // Reset Hub stats
      document.getElementById('hub-q-errors').innerText = '0';
      document.getElementById('hub-q-favs').innerText = '0';
      document.getElementById('hub-err-tag').innerText = '0';

      alert('Локальный прогресс сброшен.');
    }
  }

  // INTELLIGENT TAB NAVIGATION: RESTORES LAST ACTIVE VIEW OF THE TAB!
    // ==========================================
  // QUESTION DETAIL MODAL OVERLAY (ПОЛНЫЙ ПРОСМОТР ВОПРОСА С ИЗБРАННЫМ)
  // ==========================================
  let modalActiveQ = null;
  let modalActiveTestId = null;
  let modalActiveTestTitle = null;

    function openQuestionDetailModalById(testId, qid) {
    let q = null;
    let tTitle = testId;
    const tData = BUNDLED_TESTS[testId];
    if (tData) {
      tTitle = tData.title;
      q = (tData.questions || []).find(item => item.id == qid);
    }
    if (!q) {
      q = (state.currentTestOriginalQuestions || []).find(item => item.id == qid) || (state.activeQuestions || []).find(item => item.id == qid);
    }
    if (!q) {
      const err = getAllSavedErrors().find(e => e.testId === testId && e.question && e.question.id == qid);
      if (err) q = err.question;
      const fav = getAllSavedFavorites().find(f => f.testId === testId && f.question && f.question.id == qid);
      if (fav) q = fav.question;
    }
    if (q) {
      openQuestionDetailModal(q, testId, tTitle);
    }
  }

  function openQuestionDetailModal(q, testId, testTitle) {
    triggerHaptic('light');
    modalActiveQ = q;
    modalActiveTestId = testId || state.activeTestId;
    modalActiveTestTitle = testTitle || state.activeTestTitle;

    document.getElementById('mqd-badge').innerText = `ВОПРОС #${q.id}`;
    document.getElementById('mqd-test-title').innerText = modalActiveTestTitle || 'Тест';
    document.getElementById('mqd-question-text').innerText = q.question;

    const optList = document.getElementById('mqd-options-list');
    optList.innerHTML = '';

    const correctIdx = getCorrectIndex(q);

    (q.options || []).forEach((opt, idx) => {
      const isCorrect = (idx === correctIdx);
      const row = document.createElement('div');
      row.className = `p-3 rounded-2xl border text-xs sm:text-sm font-medium flex items-center justify-between space-x-3 transition ${isCorrect ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-200' : 'bg-app-surface border-app-border text-slate-300'}`;

      const letters = ['А', 'Б', 'В', 'Г', 'Д', 'Е'][idx] || (idx + 1);
      const badgeStyle = isCorrect ? 'badge-correct-icon bg-emerald-500 border-emerald-400 text-white font-bold' : 'bg-app-card border-app-border text-slate-400';
      const badgeIcon = isCorrect ? '✓' : letters;

      row.innerHTML = `
        <div class="flex items-start space-x-2.5 flex-1 min-w-0">
          <span class="w-6 h-6 rounded-full border flex items-center justify-center text-xs font-mono shrink-0 mt-0.5 ${badgeStyle}">${badgeIcon}</span>
          <span class="leading-snug flex-1">${opt}</span>
        </div>
        ${isCorrect ? '<span class="badge-correct px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shrink-0">Верно ✓</span>' : ''}
      `;
      optList.appendChild(row);
    });

    updateModalFavUI();
    document.getElementById('modal-question-detail').classList.remove('hidden');
  }

  function closeQuestionDetailModal() {
    triggerHaptic('light');
    document.getElementById('modal-question-detail').classList.add('hidden');
  }

  function isModalQInFavorites() {
    if (!modalActiveQ || !modalActiveTestId) return false;
    const qid = modalActiveQ.id;
    if (modalActiveTestId === state.activeTestId) {
      return isQuestionFavorited(qid);
    }
    const raw = localStorage.getItem(`ohtest_favs_${modalActiveTestId}`);
    if (!raw) return false;
    try {
      const favList = JSON.parse(raw);
      if (!Array.isArray(favList)) return false;
      return favList.some(id => id == qid);
    } catch(e) { return false; }
  }

  function updateModalFavUI() {
    const isFav = isModalQInFavorites();
    const starBtn = document.getElementById('mqd-fav-icon-btn');
    const labelBtnText = document.getElementById('mqd-fav-btn-text');
    const labelBtn = document.getElementById('mqd-fav-btn');

    if (starBtn) {
      starBtn.innerText = isFav ? '★' : '☆';
      starBtn.className = isFav ? 'p-1.5 rounded-xl bg-amber-500/20 border border-amber-500/40 text-amber-400 text-sm active:scale-90 transition' : 'p-1.5 rounded-xl bg-app-surface border border-app-border text-slate-400 text-sm active:scale-90 transition';
    }
    if (labelBtnText) {
      labelBtnText.innerText = isFav ? 'В избранном ✓' : 'В избранное';
    }
    if (labelBtn) {
      labelBtn.className = isFav ? 'px-3.5 py-2 rounded-xl bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs font-bold active:scale-95 transition flex items-center gap-1.5' : 'px-3.5 py-2 rounded-xl bg-app-surface border border-app-border text-slate-300 text-xs font-bold active:scale-95 transition flex items-center gap-1.5';
    }
  }

  function toggleModalFav() {
    if (!modalActiveQ || !modalActiveTestId) return;
    triggerHaptic('light');
    const tId = modalActiveTestId;
    const qid = modalActiveQ.id;

    let favArr = [];
    if (tId === state.activeTestId) {
      const hasFav = isQuestionFavorited(qid);
      if (hasFav) {
        state.favorites.delete(qid);
        state.favorites.delete(Number(qid));
        state.favorites.delete(String(qid));
      } else {
        state.favorites.add(qid);
      }
      favArr = [...state.favorites];
    } else {
      const raw = localStorage.getItem(`ohtest_favs_${tId}`);
      if (raw) {
        try { favArr = JSON.parse(raw); } catch(e) { favArr = []; }
      }
      const existingIdx = favArr.findIndex(id => id == qid);
      if (existingIdx !== -1) {
        favArr.splice(existingIdx, 1);
      } else {
        favArr.push(qid);
      }
    }

    localStorage.setItem(`ohtest_favs_${tId}`, JSON.stringify(favArr));
    if (tId === state.activeTestId) {
      updateFavUI(isQuestionFavorited(qid));
      const hubFavsEl = document.getElementById('hub-q-favs');
      if (hubFavsEl) {
        hubFavsEl.innerText = state.favorites.size;
        hubFavElClass(hubFavsEl, state.favorites.size);
      }
    }

    updateModalFavUI();
    const profFav = document.getElementById('profile-fav-count');
    if (profFav) profFav.innerText = getAllSavedFavorites().length;

    // Refresh subtabs if visible
    if (state.activeProfileSubTab === 'favs') renderFavsSubtab();
    if (state.activeProfileSubTab === 'errors') renderErrorsSubtab();
  }

  // ==========================================
  // SUPPORT & DEVELOPER CONTACT
  // ==========================================
  function openSupportChat() {
    triggerHaptic('light');
    const tg = window.Telegram?.WebApp;
    if (tg?.openTelegramLink) {
      tg.openTelegramLink('https://t.me/issdm');
    } else {
      window.open('https://t.me/issdm', '_blank');
    }
  }

  function openFeedbackModal() {
    triggerHaptic('light');
    document.getElementById('fb-text').value = '';
    document.getElementById('fb-contact').value = state.userUsername || (state.userId ? `ID: ${state.userId}` : '');
    document.getElementById('modal-support-feedback').classList.remove('hidden');
  }

  function closeFeedbackModal() {
    triggerHaptic('light');
    document.getElementById('modal-support-feedback').classList.add('hidden');
  }

  async function submitFeedback() {
    triggerHaptic('light');
    const text = document.getElementById('fb-text').value.trim();
    const contact = document.getElementById('fb-contact').value.trim();
    const type = document.getElementById('fb-type').value;

    if (!text) {
      alert('Пожалуйста, напишите текст сообщения.');
      return;
    }

    try {
      await fetch('/api/support/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: state.userId,
          contact: contact,
          type: type,
          message: text,
          test_id: state.activeTestId
        })
      });
    } catch(e) {}

    alert('Спасибо! Ваше сообщение принято и передано разработчику.');
    closeFeedbackModal();
  }

  let homeTabScrollTop = 0;
  let homeWindowScrollTop = 0;
  const tabScrollPositions = { profile: 0, settings: 0 };
  const tabWindowScrollPositions = { profile: 0, settings: 0 };
  let homeHeaderControls = null;

  function switchTab(tabId) {
    triggerHaptic('light');

    if (tabId === 'rating') {
      switchTab('profile');
      switchProfileTab('rating');
      return;
    }

    const previousTab = state.currentTab;
    const appBody = document.getElementById('app-body');
    if (previousTab === 'home' && tabId !== 'home') {
      homeTabScrollTop = appBody?.scrollTop || 0;
      homeWindowScrollTop = window.scrollY;
      homeHeaderControls = ['btn-grid-modal', 'btn-finish-early', 'btn-fav-toggle', 'header-admin-pill']
        .reduce((controls, id) => {
          const element = document.getElementById(id);
          if (element) controls[id] = { hidden: element.classList.contains('hidden'), display: element.style.display };
          return controls;
        }, {});
    } else if (previousTab !== 'home' && previousTab !== tabId) {
      tabScrollPositions[previousTab] = appBody?.scrollTop || 0;
      tabWindowScrollPositions[previousTab] = window.scrollY;
    }

    state.currentTab = tabId;
    if (tabId === 'home') {
      if (previousTab === 'home' || !appPreferences.restoreHome) {
        state.homeActiveView = 'home';
        viewStack = ['home'];
      }
    }

    const tabs = ['home', 'profile', 'settings'];
    document.querySelector('nav.glass').style.setProperty('--nav-active-index', String(Math.max(0, tabs.indexOf(tabId))));

    tabs.forEach(t => {
      const btn = document.getElementById('tab-' + t);
      if (!btn) return;
      if (t === tabId) btn.setAttribute('aria-current', 'page');
      else btn.removeAttribute('aria-current');
      if (t === tabId) {
        btn.className = "flex flex-col items-center space-y-1 text-brand-400 active:scale-95 transition";
        const sp = btn.querySelector('span');
        if (sp) sp.className = "text-[11px] font-bold";
      } else {
        btn.className = "flex flex-col items-center space-y-1 text-slate-400 hover:text-slate-200 active:scale-95 transition";
        const sp = btn.querySelector('span');
        if (sp) sp.className = "text-[11px] font-semibold";
      }
    });

    hideAllViews();

    if (tabId === 'home') {
      const viewIds = {
        home: 'view-home', tests: 'view-tests', hub: 'view-hub', solver: 'view-solver',
        result: 'view-result', flashcards: 'view-flashcards', search: 'view-search', admin: 'view-admin'
      };
      const activeView = document.getElementById(viewIds[state.homeActiveView]) ? state.homeActiveView : 'home';
      state.homeActiveView = activeView;
      document.getElementById(viewIds[activeView]).classList.remove('hidden');
      if (activeView === 'solver' && homeHeaderControls) {
        Object.entries(homeHeaderControls).forEach(([id, saved]) => {
          const element = document.getElementById(id);
          if (!element) return;
          element.classList.toggle('hidden', saved.hidden);
          if (saved.display) element.style.display = saved.display;
          else element.style.removeProperty('display');
        });
      }
      renderActiveAttemptBanner();
    } else if (tabId === 'profile') {
      document.getElementById('view-tab-profile').classList.remove('hidden');
    } else if (tabId === 'settings') {
      document.getElementById('view-tab-settings').classList.remove('hidden');
      if (previousTab === 'settings') openSettingsSection(null);
    }

    updateHeaderNavState();
    updateTelegramBackButton();
    if (tabId === 'profile') {
      try {
        updateProfileFullView();
      } catch(e) {
        console.error('Could not update profile view:', e);
        const disciplines = document.getElementById('profile-disciplines-list');
        const content = document.getElementById('profile-subtab-content');
        if (disciplines && !disciplines.innerHTML.trim()) {
          disciplines.innerHTML = '<div class="p-4 text-center text-xs text-rose-300">Не удалось загрузить дисциплины.</div>';
        }
        if (content && !content.innerHTML.trim()) {
          content.innerHTML = '<div class="p-6 text-center text-xs text-rose-300">Не удалось загрузить вкладку профиля.</div>';
        }
      }
    }
    if (appBody) {
      const scrollTop = tabId === 'home'
        ? (previousTab === 'home' || !appPreferences.restoreHome ? 0 : homeTabScrollTop)
        : (tabScrollPositions[tabId] || 0);
      const windowTop = tabId === 'home'
        ? (previousTab === 'home' || !appPreferences.restoreHome ? 0 : homeWindowScrollTop)
        : (tabWindowScrollPositions[tabId] || 0);
      requestAnimationFrame(() => {
        if (state.currentTab !== tabId) return;
        appBody.scrollTop = scrollTop;
        window.scrollTo(0, windowTop);
      });
    }
  }

  function hideAllViews() {
    clearTimeout(autoAdvanceTimer);
    const views = ['view-home', 'view-tests', 'view-hub', 'view-solver', 'view-result', 'view-flashcards', 'view-search', 'view-tab-profile', 'view-tab-settings', 'view-admin'];
    views.forEach(v => {
      const el = document.getElementById(v);
      if (el) el.classList.add('hidden');
    });
    // NEVER leak solver header buttons onto other views!
    const finishBtn = document.getElementById('btn-finish-early');
    if (finishBtn) finishBtn.classList.add('hidden');
    const gridBtn = document.getElementById('btn-grid-modal');
    if (gridBtn) gridBtn.classList.add('hidden');
    const favBtn = document.getElementById('btn-fav-toggle');
    if (favBtn) favBtn.classList.add('hidden');
  }

  function updateTelegramBackButton() {
    const tg = window.Telegram?.WebApp;
    if (tg?.BackButton) {
      const activeView = getCurrentActiveView();
      const isRoot = (activeView === 'view-home' || activeView === 'view-tab-profile' || activeView === 'view-tab-settings');
      if (!isRoot) {
        tg.BackButton.show();
      } else {
        tg.BackButton.hide();
      }
    }
  }

  function goBack() {
    triggerHaptic('light');
    const activeView = getCurrentActiveView();
    if (activeView === 'view-admin-person' || activeView === 'view-admin-people') {
      backAdminPeople();
      return;
    }
    if (activeView === 'view-settings-detail') {
      openSettingsSection(null);
      return;
    }
    if (activeView === 'view-solver' || activeView === 'view-flashcards' || activeView === 'view-search' || activeView === 'view-result') {
      if (state.activeTestId) {
        openTestHub();
      } else {
        state.homeActiveView = 'home';
        switchTab('home');
      }
      return;
    }
    if (activeView === 'view-hub') {
      if (state.activeSubjectId) {
        openSubjectTests(state.activeSubjectId, state.activeSubjectTitle);
      } else {
        state.homeActiveView = 'home';
        switchTab('home');
      }
      return;
    }
    if (activeView === 'view-tests' || activeView === 'view-admin') {
      state.homeActiveView = 'home';
      viewStack = ['home'];
      switchTab('home');
      return;
    }
    if (viewStack.length > 1) {
      viewStack.pop();
      const prev = viewStack[viewStack.length - 1];
      if (prev === 'hub') openTestHub();
      else if (prev === 'tests') openSubjectTests(state.activeSubjectId, state.activeSubjectTitle);
      else if (prev === 'admin') openAdminDashboard();
      else switchTab('home');
    } else {
      switchTab('home');
    }
    updateTelegramBackButton();
  }
  
