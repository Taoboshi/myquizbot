const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
      const url = typeof input === 'string' ? input : input.url;
      if (!url.startsWith('/api/')) return nativeFetch(input, init);
      const headers = new Headers(input instanceof Request ? input.headers : undefined);
      new Headers(init.headers || {}).forEach((value, key) => headers.set(key, value));
      const initData = window.Telegram?.WebApp?.initData;
      if (initData) headers.set('X-Telegram-Init-Data', initData);
      return nativeFetch(input, { ...init, headers });
    };

    // Restore the saved theme before the first screen is rendered.
  try {
    const _earlyTheme = localStorage.getItem('ohtest_theme') || 'dark';
    document.body.classList.toggle('light-theme', _earlyTheme === 'light' || (_earlyTheme === 'system' && matchMedia('(prefers-color-scheme: light)').matches));
    let _earlyAccent = localStorage.getItem('ohtest_accent') || 'green';
    if (_earlyAccent === 'emerald') _earlyAccent = 'green';
    else if (_earlyAccent === 'amber') _earlyAccent = 'base';
    else if (_earlyAccent === 'cyan') _earlyAccent = 'blue';
    else if (_earlyAccent === 'rose') _earlyAccent = 'red';
    document.body.classList.remove('theme-base', 'theme-blue', 'theme-purple', 'theme-red');
    document.body.classList.add(`theme-${_earlyAccent}`);
  } catch(e) {}

  // Helper: Normalize correct answer index across all formats (number, string, letter)
  function getCorrectIndex(q) {
    if (!q) return 0;
    if (typeof q.correct === 'number') return q.correct;
    if (typeof q.correct_index === 'number') return q.correct_index;
    if (q.correct !== undefined && q.correct !== null) {
      const parsed = parseInt(q.correct, 10);
      if (!isNaN(parsed)) return parsed;
      if (typeof q.correct === 'string') {
        const letters = ['a', 'b', 'c', 'd', 'e', 'f', 'а', 'б', 'в', 'г', 'д', 'е'];
        const idx = letters.indexOf(q.correct.toLowerCase().trim());
        if (idx !== -1) return idx % 6;
      }
    }
    if (q.correct_index !== undefined && q.correct_index !== null) {
      const parsed = parseInt(q.correct_index, 10);
      if (!isNaN(parsed)) return parsed;
    }
    return 0;
  }

  function getQuestionCorrectText(q) {
    if (!q || !q.options) return '—';
    const cIdx = getCorrectIndex(q);
    return q.options[cIdx] || '—';
  }

  // Complete Database of all 11 real tests

  // Admin In-memory store (NO FAKE DATA)
  // Read local storage unassigned overrides and deleted subjects
  const storedDeletedSubjects = new Set(JSON.parse(localStorage.getItem('ohtest_deleted_subjects') || '[]'));
  const storedUnassignedTests = new Set(JSON.parse(localStorage.getItem('ohtest_unassigned_tests') || '[]'));

  // Restore cached subjects & tests metadata from localStorage
  const cachedSubjectsRaw = localStorage.getItem('ohtest_cached_subjects');
  const cachedTestsMetaRaw = localStorage.getItem('ohtest_cached_tests_meta');
  let initialSubjects = [];
  let initialTestsMeta = [];
  try {
    const parsedSubjects = cachedSubjectsRaw ? JSON.parse(cachedSubjectsRaw) : [];
    const parsedTestsMeta = cachedTestsMetaRaw ? JSON.parse(cachedTestsMetaRaw) : [];
    if (Array.isArray(parsedSubjects)) initialSubjects = parsedSubjects;
    if (Array.isArray(parsedTestsMeta)) initialTestsMeta = parsedTestsMeta;
  } catch(e) {}

  // Admin In-memory store (Synchronized from backend / localStorage cache)
  const adminStore = {
    users: [],
    frequentErrors: [],
    subjects: initialSubjects.filter(s => s && typeof s === 'object' && !storedDeletedSubjects.has(s.id)),
    testsMeta: initialTestsMeta.filter(t => t && typeof t === 'object')
  };

  // User State
  let state = {
    currentTab: 'home',
    homeActiveView: 'home', // 'home' | 'tests' | 'hub' | 'solver' | 'result' | 'flashcards' | 'search'
    catalogLoaded: initialTestsMeta.length > 0,
    catalogLoadFailed: false,
    activeProfileSubTab: 'favs', // 'favs' | 'errors' | 'history' | 'rating'
    showAllErrors: false,
    activeSubjectId: 'luchevaya_diagnostika',
    activeSubjectTitle: 'Основы лучевой диагностики',
    activeTestId: 'luchevaya_razdel_2',
    activeTestTitle: 'Заболевания легких и средостения',
    currentTestOriginalQuestions: [...BUNDLED_TESTS['luchevaya_razdel_2'].questions],
    activeQuestions: [...BUNDLED_TESTS['luchevaya_razdel_2'].questions],
    currentMode: 'normal',
    trainingCount: 10,
    currentQIndex: 0,
    userAnswers: {},
    revealedAnswers: new Set(),
    userErrors: new Set(),
    favorites: new Set(),
    unlockedCodeTests: new Set(JSON.parse(localStorage.getItem('ohtest_unlocked_tests') || '[]')),
    timerSeconds: 0,
    timerInterval: null,
    activeAttempt: null,
    isAdmin: false,
    userId: null,
    userName: 'Студент',
    userUsername: '',
    userAvatar: '',
    historyAttempts: [],
    favoriteReviewQueue: [],
    isHiddenInRating: localStorage.getItem('ohtest_hide_rating') === 'true',
  };

  function getCatalogVisibleTests() {
    const subjectIds = new Set((adminStore.subjects || []).map(subject => subject.id));
    return (adminStore.testsMeta || []).filter(test =>
      test && test.subject_id && test.subject_id !== 'default' && subjectIds.has(test.subject_id) && (state.isAdmin || (test.access_type || 'public') !== 'admin_only')
    );
  }

  function formatTestCount(count) {
    const value = Math.max(0, Math.floor(Number(count) || 0));
    const lastTwo = value % 100;
    const lastOne = value % 10;
    const noun = lastOne === 1 && lastTwo !== 11
      ? 'тест'
      : lastOne >= 2 && lastOne <= 4 && (lastTwo < 12 || lastTwo > 14)
        ? 'теста'
        : 'тестов';
    return `${value} ${noun}`;
  }

  let pinnedSubjects = new Set(JSON.parse(localStorage.getItem('ohtest_pinned_subjects') || '[]'));
  let pinnedTests = new Set(JSON.parse(localStorage.getItem('ohtest_pinned_tests') || '[]'));
  let pinActionTarget = null;

  function attachLongPress(el, onLongPress) {
    let timer = null;
    let hasTriggered = false;

    el.addEventListener('touchstart', (e) => {
      hasTriggered = false;
      timer = setTimeout(() => {
        hasTriggered = true;
        triggerHaptic('medium');
        onLongPress();
      }, 450);
    }, { passive: true });

    el.addEventListener('touchmove', () => {
      if (timer) clearTimeout(timer);
    }, { passive: true });

    el.addEventListener('touchend', (e) => {
      if (timer) clearTimeout(timer);
      if (hasTriggered) {
        e.preventDefault();
      }
    });

    el.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      onLongPress();
    });
  }

  function showPinActionModal(type, id, title) {
    pinActionTarget = { type, id, title };
    const modal = document.getElementById('modal-pin-action');
    const titleEl = document.getElementById('pin-modal-title');
    const descEl = document.getElementById('pin-modal-desc');
    const btnEl = document.getElementById('pin-modal-toggle-btn');

    const isPinned = (type === 'subject') ? pinnedSubjects.has(id) : pinnedTests.has(id);
    const itemTypeRu = (type === 'subject') ? 'предмет' : 'тест';

    titleEl.innerText = title;
    if (isPinned) {
      descEl.innerText = `Этот ${itemTypeRu} сейчас закреплен вверху списка. Открепить?`;
      btnEl.innerText = 'Открепить';
      btnEl.className = "w-full py-2.5 rounded-xl bg-app-surface border border-app-border text-slate-300 hover:text-white font-bold text-xs transition";
    } else {
      descEl.innerText = `Закрепить этот ${itemTypeRu} в самом верху списка на главной?`;
      btnEl.innerText = '📌 Закрепить вверху';
      btnEl.className = "w-full py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs shadow-md transition";
    }

    modal.classList.remove('hidden');
  }

  function closePinActionModal() {
    document.getElementById('modal-pin-action').classList.add('hidden');
    pinActionTarget = null;
  }

  function confirmTogglePin() {
    if (!pinActionTarget) return;
    triggerHaptic('light');
    const { type, id } = pinActionTarget;
    if (type === 'subject') {
      if (pinnedSubjects.has(id)) {
        pinnedSubjects.delete(id);
      } else {
        pinnedSubjects.add(id);
      }
      localStorage.setItem('ohtest_pinned_subjects', JSON.stringify([...pinnedSubjects]));
      renderHomeSubjects();
    } else {
      if (pinnedTests.has(id)) {
        pinnedTests.delete(id);
      } else {
        pinnedTests.add(id);
      }
      localStorage.setItem('ohtest_pinned_tests', JSON.stringify([...pinnedTests]));
      openSubjectTests(state.activeSubjectId, state.activeSubjectTitle);
    }
    closePinActionModal();
  }

  let viewStack = ['home'];
  let fcIndex = 0;
  let fcFlipped = false;

  // Telegram WebApp Initialization
  window.addEventListener('DOMContentLoaded', async () => {
    // Reapply saved theme after settings controls are available.
    setThemeMode(localStorage.getItem('ohtest_theme') || 'dark', true);
    let savedAccent = localStorage.getItem('ohtest_accent') || 'green';
    if (savedAccent === 'emerald') savedAccent = 'green';
    else if (savedAccent === 'amber') savedAccent = 'base';
    else if (savedAccent === 'cyan') savedAccent = 'blue';
    else if (savedAccent === 'rose') savedAccent = 'red';
    setAccentColor(savedAccent, true);

    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      try {
        const isL = document.body.classList.contains('light-theme');
        tg.setHeaderColor(isL ? '#f8fafc' : '#090b11');
        tg.setBackgroundColor(isL ? '#f8fafc' : '#090b11');
      } catch(e) {}

      if (tg.BackButton) {
        tg.BackButton.onClick(() => goBack());
      }

      if (tg.initDataUnsafe?.user) {
        const u = tg.initDataUnsafe.user;
        state.userId = u.id;
        state.userName = [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username || 'Студент';
        state.userUsername = u.username ? '@' + u.username : '';
      }
    }

    // Local Storage restore
    try {
      const savedHistory = localStorage.getItem('ohtest_history');
      if (savedHistory) {
        const parsedHistory = JSON.parse(savedHistory);
        state.historyAttempts = Array.isArray(parsedHistory) ? parsedHistory.filter(item => item && typeof item === 'object') : [];
      }
      const savedFavs = localStorage.getItem(`ohtest_favs_${state.activeTestId}`);
      if (savedFavs) state.favorites = new Set(JSON.parse(savedFavs));
      const savedErrors = localStorage.getItem(`ohtest_errors_${state.activeTestId}`);
      if (savedErrors) state.userErrors = new Set(JSON.parse(savedErrors));

      const customName = localStorage.getItem('ohtest_custom_name');
      if (customName) state.userName = customName;
      const customAvatar = localStorage.getItem('ohtest_custom_avatar');
      if (customAvatar) state.userAvatar = customAvatar;

      const savedHideRating = localStorage.getItem('ohtest_hide_rating');
      if (savedHideRating !== null) {
        state.isHiddenInRating = (savedHideRating === 'true');
        const hideEl = document.getElementById('set-hide-rating');
        if (hideEl) hideEl.checked = state.isHiddenInRating;
      }
    } catch(e) {}

    removePreviouslySyncedServerStats();

    // Update Profile UI
    document.getElementById('profile-name').innerText = state.userName;
    document.getElementById('profile-username').innerText = state.userUsername || 'Telegram User';
    document.getElementById('profile-id').innerText = state.userId ? `ID: ${state.userId}` : 'Локальный режим';
    renderProfileAvatarElement(document.getElementById('profile-avatar'), state.userAvatar, state.userName);
    document.getElementById('profile-attempts-count').innerText = state.historyAttempts.length;
    document.getElementById('profile-fav-count').innerText = state.favorites.size;
    updateProfileErrorBadge(getAllSavedErrors().length);

    // Check Saved Active Attempt
    restoreActiveAttemptState();

    // Render Initial Home INSTANTLY (Zero-wait UI from bundled data)
    renderHomeSubjects();
    renderActiveAttemptBanner();
    updateHubResumeButton();
    updateHeaderNavState();

    // Dynamic Header Scroll Shrink & Tap-to-top setup
    setupHeaderScrollObserver();

    // Fetch server updates & check admin in background (non-blocking)
    checkBootstrapAndAdmin().then(() => {
      state.catalogLoaded = true;
      renderHomeSubjects();
      updateHubResumeButton();
      const profFavsEl = document.getElementById('profile-fav-count');
      if (profFavsEl) profFavsEl.innerText = getAllSavedFavorites().length;
      if (state.currentTab === 'profile') updateProfileFullView();
    });
  });

  // Smooth scroll to top of app-body
  function scrollToAppTop() {
    triggerHaptic('light');
    const bodyEl = document.getElementById('app-body');
    if (bodyEl) {
      bodyEl.scrollTo({ top: 0, behavior: 'smooth' });
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function showHeaderElement(el) {
    if (!el) return;
    el.classList.remove('hidden');
    el.style.removeProperty('display');
  }

  function hideHeaderElement(el) {
    if (!el) return;
    el.classList.add('hidden');
    el.style.setProperty('display', 'none', 'important');
  }

  // Detect which view is currently active in the DOM
  function getCurrentActiveView() {
    // 1. If currently in Profile tab and profile view is visible
    if (state.currentTab === 'profile') {
      const p = document.getElementById('view-tab-profile');
      if (p && !p.classList.contains('hidden') && p.style.display !== 'none') {
        return 'view-tab-profile';
      }
    }
    // 2. If currently in Settings tab and settings view is visible
    if (state.currentTab === 'settings') {
      const s = document.getElementById('view-tab-settings');
      if (s && !s.classList.contains('hidden') && s.style.display !== 'none') {
        return state.settingsSection ? 'view-settings-detail' : 'view-tab-settings';
      }
    }

    // 3. Check nested views where Back button replaces Logo
    const nestedViews = [
      'view-tests', 'view-hub', 'view-solver', 'view-result',
      'view-flashcards', 'view-search', 'view-admin'
    ];
    for (const v of nestedViews) {
      const el = document.getElementById(v);
      if (el && !el.classList.contains('hidden') && el.style.display !== 'none') {
        return v;
      }
    }

    // 4. Default to home catalog
    return 'view-home';
  }

  // Header Title & Logo/Back state manager:
  // - Main 3 tabs (Главная, Профиль, Настройки): Shows Logo, hides Back btn, shows text ("Главная", "Профиль", "Настройки")
  // - Subpages / Nested views: Hides Logo, shows Back btn (replacing logo in same 36x36 slot), hides text completely!
  function updateHeaderNavState() {
    const logoEl = document.getElementById('header-logo-icon');
    const backEl = document.getElementById('nav-back-btn');
    const titleContainer = document.getElementById('header-title-container');
    const titleEl = document.getElementById('header-title');
    const subEl = document.getElementById('header-subtitle');
    const searchBtn = document.getElementById('header-search-btn');

    const activeView = getCurrentActiveView();
    const isMainTabRoot = (activeView === 'view-home') ||
                          (activeView === 'view-tab-profile') ||
                          (activeView === 'view-tab-settings');

    if (isMainTabRoot) {
      // 1. Root main screen: Show Logo, Hide Back button
      showHeaderElement(logoEl);
      hideHeaderElement(backEl);

      // 2. Show Title text strictly for the 3 main screens
      showHeaderElement(titleContainer);
      if (titleEl) {
        if (activeView === 'view-home') titleEl.innerText = "Главная";
        else if (activeView === 'view-tab-profile') titleEl.innerText = "Профиль";
        else if (activeView === 'view-tab-settings') titleEl.innerText = "Настройки";
      }
      if (subEl) {
        subEl.innerText = '';
        hideHeaderElement(subEl);
      }

      // 3. Search button (лупа): ONLY on Home catalog; strictly hidden on Profile & Settings
      if (activeView === 'view-home') {
        showHeaderElement(searchBtn);
      } else {
        hideHeaderElement(searchBtn);
      }
    } else {
      // Nested screen: Logo is hidden, Back button replaces Logo in exact 36x36 slot
      hideHeaderElement(logoEl);
      showHeaderElement(backEl);

      // Title text completely hidden on all nested screens
      hideHeaderElement(titleContainer);
      if (titleEl) titleEl.innerText = '';
      if (subEl) {
        subEl.innerText = '';
        hideHeaderElement(subEl);
      }

      // Search button (лупа) only on screens with contextual list search:
      if (activeView === 'view-tests' || activeView === 'view-hub' || activeView === 'view-solver') {
        showHeaderElement(searchBtn);
      } else {
        hideHeaderElement(searchBtn);
      }
    }
  }

  // Setup scroll listener for app-body and window to toggle header-scrolled class
  function setupHeaderScrollObserver() {
    const bodyEl = document.getElementById('app-body');
    const headerEl = document.getElementById('app-header');
    const navEl = document.querySelector('nav.glass');
    if (!headerEl) return;
    const onScroll = () => {
      const scrollY = (bodyEl ? bodyEl.scrollTop : 0) || window.scrollY || 0;
      if (navEl) navEl.classList.toggle('nav-scrolled', scrollY > 12);
      if (scrollY > 12) {
        headerEl.classList.add('header-scrolled');
      } else {
        headerEl.classList.remove('header-scrolled');
      }
    };
    if (bodyEl) bodyEl.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  // Context-aware Search Button: searches info strictly on the CURRENT page!
  function handleHeaderSearchClick() {
    triggerHaptic('light');
    const btn = document.getElementById('header-search-btn');
    if (btn) btn.blur(); // Remove focus so it never stays glowing

    const activeView = getCurrentActiveView();
    // 1. Inside Solver, Flashcards, or Hub: search questions of this specific test
    if (activeView === 'view-solver' || activeView === 'view-hub' || activeView === 'view-flashcards') {
      openLiveSearch();
      return;
    }

    // 2. On Subject Tests list: search tests within this specific subject
    if (activeView === 'view-tests') {
      toggleInlineSearch('subject-tests-search-wrap', 'subject-tests-search', filterSubjectTestsByQuery);
      return;
    }

    // 3. On Home Catalog: search subjects on the catalog page
    if (activeView === 'view-home') {
      toggleInlineSearch('home-catalog-search-wrap', 'home-catalog-search', filterCatalogByQuery);
      return;
    }
  }

  function toggleInlineSearch(wrapId, inputId, filterFn) {
    const wrap = document.getElementById(wrapId);
    const input = document.getElementById(inputId);
    if (!wrap || !input) return;
    const opening = wrap.classList.contains('hidden');
    wrap.classList.toggle('hidden', !opening);
    if (opening) {
      setTimeout(() => input.focus(), 0);
    } else {
      input.value = '';
      filterFn('');
    }
  }

  function clearInlineSearch(inputId, filterFn) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.value = '';
    filterFn('');
    input.focus();
  }

  // Filter tests inside view-tests for the current subject
  function filterSubjectTestsByQuery(q) {
    const container = document.getElementById('tests-items-container');
    if (!container) return;
    const cards = container.querySelectorAll('.p-4');
    let matched = 0;
    const query = (q || '').toLocaleLowerCase('ru').trim();
    cards.forEach(card => {
      const txt = card.innerText.toLocaleLowerCase('ru');
      if (!query || txt.includes(query)) {
        card.style.display = '';
        matched++;
      } else {
        card.style.display = 'none';
      }
    });
    document.getElementById('subject-tests-search-empty')?.classList.toggle('hidden', !query || matched > 0);
  }

  // Filter subjects inside view-home for the catalog page
  function filterCatalogByQuery(q) {
    const list = document.getElementById('home-subjects-list');
    if (!list) return;
    const cards = list.querySelectorAll('.p-4');
    let matchedCount = 0;
    const query = (q || '').toLocaleLowerCase('ru').trim();
    cards.forEach(card => {
      const txt = card.innerText.toLocaleLowerCase('ru');
      if (!query || txt.includes(query)) {
        card.style.display = '';
        matchedCount++;
      } else {
        card.style.display = 'none';
      }
    });
    document.getElementById('home-search-empty')?.classList.toggle('hidden', !query || matchedCount > 0);
  }

    // THEME MODE SWITCHER (СВЕТЛАЯ / ТЕМНАЯ ТЕМА)
  function setThemeMode(mode, skipSave = false) {
    if (!skipSave) triggerHaptic('light');
    const isLight = mode === 'light' || (mode === 'system' && matchMedia('(prefers-color-scheme: light)').matches);
    if (isLight) {
      document.body.classList.add('light-theme');
    } else {
      document.body.classList.remove('light-theme');
    }
    if (!skipSave) {
      localStorage.setItem('ohtest_theme', mode);
    }
    updateThemeUI(isLight);
    const themeControl = document.getElementById('settings-theme-mode');
    if (themeControl) themeControl.value = mode;
  }

  function toggleTheme() {
    const isLight = document.body.classList.contains('light-theme');
    setThemeMode(isLight ? 'dark' : 'light');
  }

  function updateThemeUI(isLight) {
    const btnDark = document.getElementById('theme-btn-dark');
    const btnLight = document.getElementById('theme-btn-light');
    if (btnDark && btnLight) {
      if (isLight) {
        btnLight.className = "px-2.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 bg-white text-slate-900 shadow-sm";
        btnDark.className = "px-2.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 text-slate-400 hover:text-slate-600";
      } else {
        btnDark.className = "px-2.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 bg-white/15 text-white shadow-sm";
        btnLight.className = "px-2.5 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 text-slate-400 hover:text-white";
      }
    }
    try {
      window.Telegram?.WebApp?.setHeaderColor(isLight ? '#f8fafc' : '#090c13');
      window.Telegram?.WebApp?.setBackgroundColor(isLight ? '#f8fafc' : '#090c13');
    } catch(e) {}
  }

  // ACCENT COLOR SWITCHER (5 АКЦЕНТНЫХ ФОНОВ БЕЗ НЕОНА)
  const ACCENT_NAMES = {
    base: 'Базовый',
    green: 'Зеленый',
    blue: 'Синий',
    purple: 'Фиолетовый',
    red: 'Красный'
  };

  function setAccentColor(color, skipSave = false) {
    // Map legacy accents if any
    if (color === 'emerald') color = 'green';
    else if (color === 'cyan') color = 'blue';
    else if (color === 'amber') color = 'base';
    else if (color === 'rose') color = 'red';

    const validAccents = ['base', 'green', 'blue', 'purple', 'red'];
    if (!validAccents.includes(color)) color = 'green';

    // Remove any previous accent class
    validAccents.forEach(a => document.body.classList.remove(`theme-${a}`));

    // Add selected accent class
    document.body.classList.add(`theme-${color}`);

    if (!skipSave) {
      triggerHaptic('light');
      localStorage.setItem('ohtest_accent', color);
    }

    updateAccentUI(color);
  }

  function updateAccentUI(activeColor) {
    const badge = document.getElementById('accent-name-badge');
    if (badge) {
      badge.innerText = ACCENT_NAMES[activeColor] || 'Базовый';
    }

    const swatches = document.querySelectorAll('.accent-swatch');
    swatches.forEach(swatch => {
      const swColor = swatch.getAttribute('data-accent');
      const isSelected = (swColor === activeColor);
      const circle = swatch.querySelector('.rounded-full');
      const check = swatch.querySelector('.swatch-check');
      swatch.classList.toggle('accent-swatch-active', isSelected);

      if (isSelected) {
        swatch.classList.add('bg-white/10', 'border-white/20');
        if (circle) {
          circle.classList.add('ring-2', 'ring-white', 'scale-105');
          circle.classList.remove('border-transparent');
          circle.classList.add('border-white/60');
        }
        if (check) check.classList.remove('hidden');
      } else {
        swatch.classList.remove('bg-white/10', 'border-white/20');
        if (circle) {
          circle.classList.remove('ring-2', 'ring-white', 'scale-105');
          circle.classList.remove('border-white/60');
          circle.classList.add('border-transparent');
        }
        if (check) check.classList.add('hidden');
      }
    });
  }

  // Haptic feedback helper
  function triggerHaptic(type = 'light') {
    if (!document.getElementById('set-haptic')?.checked) return;
    try {
      const h = window.Telegram?.WebApp?.HapticFeedback;
      if (h) {
        if (type === 'success') h.notificationOccurred('success');
        else if (type === 'error') h.notificationOccurred('error');
        else h.impactOccurred('light');
      }
    } catch(e) {}
  }

  // Admin Access Verification
  async function checkBootstrapAndAdmin() {
    document.getElementById('settings-admin-block').classList.add('hidden');

    try {
      const bParams = new URLSearchParams();
      if (state.userId) bParams.set('user_id', state.userId);
      if (state.userName) bParams.set('name', state.userName);
      if (state.userUsername) bParams.set('username', state.userUsername.replace('@', ''));
      const tgU = window.Telegram?.WebApp?.initDataUnsafe?.user;
      if (tgU?.first_name) bParams.set('first_name', tgU.first_name);
      if (tgU?.last_name) bParams.set('last_name', tgU.last_name);
      const url = `/api/bootstrap?${bParams.toString()}`;
      const res = await fetch(url);
      if (!res.ok) {
        state.catalogLoadFailed = true;
        return;
      }
      state.catalogLoadFailed = false;
      {
        const data = await res.json();
        applyServerPreferences(data.preferences || {});
        if (data.user_profile && typeof data.user_profile === 'object') {
          const serverProfile = data.user_profile;
          const telegramUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
          const telegramName = [telegramUser?.first_name, telegramUser?.last_name].filter(Boolean).join(' ')
            || telegramUser?.username
            || 'Студент';
          let localCustomName = '';
          let localCustomAvatar = '';
          try {
            localCustomName = localStorage.getItem('ohtest_custom_name') || '';
            localCustomAvatar = localStorage.getItem('ohtest_custom_avatar') || '';
          } catch(e) {}

          state.userName = serverProfile.display_name || localCustomName || telegramName;
          state.userAvatar = serverProfile.avatar || localCustomAvatar;

          if (!serverProfile.display_name && localCustomName && state.userId) {
            try {
              const migrationResponse = await fetch('/api/user/profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ display_name: localCustomName, avatar: localCustomAvatar })
              });
              const migrationResult = await migrationResponse.json().catch(() => ({}));
              if (migrationResponse.ok && migrationResult.profile) {
                state.userName = migrationResult.profile.display_name;
                state.userAvatar = migrationResult.profile.avatar || '';
              } else {
                console.warn('Could not sync the existing local profile:', migrationResult.error || migrationResponse.status);
              }
            } catch(e) {
              console.warn('Could not sync the existing local profile:', e);
            }
          }

          try {
            if (serverProfile.display_name) {
              localStorage.setItem('ohtest_custom_name', state.userName);
              if (state.userAvatar) localStorage.setItem('ohtest_custom_avatar', state.userAvatar);
              else localStorage.removeItem('ohtest_custom_avatar');
            } else if (!localCustomName) {
              localStorage.removeItem('ohtest_custom_name');
              localStorage.removeItem('ohtest_custom_avatar');
            }
          } catch(e) {}
          const profileName = document.getElementById('profile-name');
          const profileAvatar = document.getElementById('profile-avatar');
          if (profileName) profileName.innerText = state.userName;
          if (profileAvatar) renderProfileAvatarElement(profileAvatar, state.userAvatar, state.userName);
        }
        if (data.is_admin) {
          state.isAdmin = true;
          /* header-admin-pill hidden */
          document.getElementById('settings-admin-block')?.classList.remove('hidden');
        } else {
          state.isAdmin = false;
          document.getElementById('settings-admin-block')?.classList.add('hidden');
        }
        if (data.is_hidden_in_rating !== undefined) {
          state.isHiddenInRating = Boolean(data.is_hidden_in_rating);
          localStorage.setItem('ohtest_hide_rating', state.isHiddenInRating ? 'true' : 'false');
          const hideEl = document.getElementById('set-hide-rating');
          if (hideEl) hideEl.checked = state.isHiddenInRating;
        }
        const subjects = Array.isArray(data.subjects) ? data.subjects : [];
        const unassignedTests = Array.isArray(data.unassigned_tests) ? data.unassigned_tests : [];
        const catalogTestCount = subjects.reduce((count, subject) => count + (subject.tests || []).length, 0) + unassignedTests.length;
        const reportedTestCount = Number(data.total_loaded_tests || 0);
        const hasCatalogPayload = subjects.length > 0 || unassignedTests.length > 0;
        const hasCompleteCatalog = hasCatalogPayload && (!reportedTestCount || catalogTestCount >= reportedTestCount);
        if (hasCompleteCatalog) {
          const delSet = new Set(JSON.parse(localStorage.getItem('ohtest_deleted_subjects') || '[]'));
          const unSet = new Set(JSON.parse(localStorage.getItem('ohtest_unassigned_tests') || '[]'));

          adminStore.subjects = subjects
            .filter(s => !delSet.has(s.id))
            .map(s => ({
              id: s.id,
              title: s.title,
              emoji: s.emoji || '📚',
              tests_count: s.tests_count || 0
            }));

          const loadedMeta = [];
          subjects.forEach(s => {
            const isSubDeleted = delSet.has(s.id);
            (s.tests || []).forEach(t => {
              const isUnassigned = isSubDeleted || unSet.has(t.id);
              loadedMeta.push({
                id: t.id,
                title: t.title,
                subject_id: isUnassigned ? 'default' : s.id,
                subject_emoji: s.emoji || '📚',
                questions_count: t.questions_count,
                study_mode: t.study_mode || 'test',
                access_type: t.access_type || 'public',
                access_code: t.access_code || ''
              });
            });
          });
          unassignedTests.forEach(t => {
            loadedMeta.push({
              id: t.id,
              title: t.title,
              subject_id: 'default',
              questions_count: t.questions_count,
              study_mode: t.study_mode || 'test',
              access_type: t.access_type || 'public',
              access_code: t.access_code || ''
            });
          });
          adminStore.testsMeta = loadedMeta;

          // Persist actual data to localStorage cache
          try {
            localStorage.setItem('ohtest_cached_subjects', JSON.stringify(adminStore.subjects));
            localStorage.setItem('ohtest_cached_tests_meta', JSON.stringify(adminStore.testsMeta));
          } catch(e) {}
        }
      }
    } catch(e) {
      state.catalogLoadFailed = true;
      state.isAdmin = false;
      document.getElementById('settings-admin-block')?.classList.add('hidden');
    }
  }

