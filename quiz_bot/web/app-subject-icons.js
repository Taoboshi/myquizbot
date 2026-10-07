(() => {
  const icons = [
    ['stethoscope', 'Медицина', '<path d="M6 3v5a4 4 0 0 0 8 0V3M4 3h4M12 3h4M10 12v2a4 4 0 0 0 8 0v-1"/><circle cx="18" cy="11" r="2"/><circle cx="10" cy="19" r="2"/>'],
    ['scan', 'Лучевая диагностика', '<path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3M7 12h10M12 7v10"/>'],
    ['hospital', 'Здравоохранение', '<path d="M4 21V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16M2 21h20M9 21v-4h6v4M12 7v6M9 10h6"/>'],
    ['heart', 'Кардиология', '<path d="M20.8 8.6c0 5.4-8.8 11-8.8 11s-8.8-5.6-8.8-11a4.6 4.6 0 0 1 8.8-1.8 4.6 4.6 0 0 1 8.8 1.8Z"/><path d="M3 12h5l2-3 3 6 2-3h6"/>'],
    ['brain', 'Неврология', '<path d="M12 5a3 3 0 0 0-5.8-1A3.5 3.5 0 0 0 4 10a3.5 3.5 0 0 0 1 6.5A3 3 0 0 0 12 18M12 5a3 3 0 0 1 5.8-1A3.5 3.5 0 0 1 20 10a3.5 3.5 0 0 1-1 6.5A3 3 0 0 1 12 18M12 4v16M8 8h2m4 2h2m-8 4h2m4 2h2"/>'],
    ['bone', 'Анатомия', '<path d="M7 7a3 3 0 1 1 2-5l6 6a3 3 0 1 1 5 4 3 3 0 0 1-4 2l-6 6a3 3 0 1 1-4-4l6-6-5-5Z"/>'],
    ['lungs', 'Пульмонология', '<path d="M12 11V4m0 7c-2-3-3-5-5-5-2 0-4 5-4 10 0 3 2 5 5 5 2 0 4-2 4-5v-5Zm0 0c2-3 3-5 5-5 2 0 4 5 4 10 0 3-2 5-5 5-2 0-4-2-4-5v-5Z"/>'],
    ['kidney', 'Нефрология', '<path d="M9 4c-3-2-6 1-6 5 0 6 4 11 8 10 2-.5 2-3 1-5-1-2-1-4 0-6 1-2 0-3-3-4Zm6 0c3-2 6 1 6 5 0 6-4 11-8 10-2-.5-2-3-1-5 1-2 1-4 0-6-1-2 0-3 3-4Z"/><path d="M12 8v10"/>'],
    ['eye', 'Офтальмология', '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'],
    ['tooth', 'Стоматология', '<path d="M7 3c2 0 3 1 5 1s3-1 5-1c3 0 4 3 3 7-1 3-2 5-3 8-.5 2-2.5 2-3 0l-1-4h-2l-1 4c-.5 2-2.5 2-3 0-1-3-2-5-3-8-1-4 0-7 3-7Z"/>'],
    ['ear', 'ЛОР', '<path d="M18 14c-1 2-3 3-4 5-1 2-4 2-5 0M8 11a4 4 0 1 1 8 0c0 3-3 3-3 6M12 3a7 7 0 0 0-7 7v2"/>'],
    ['skin', 'Дерматология', '<path d="M12 3c-4 0-7 3-7 7 0 6 4 11 7 11s7-5 7-11c0-4-3-7-7-7Z"/><circle cx="9" cy="10" r=".8"/><circle cx="15" cy="9" r=".8"/><circle cx="12" cy="14" r=".8"/>'],
    ['blood', 'Гематология', '<path d="M12 3s-6 7-6 12a6 6 0 0 0 12 0c0-5-6-12-6-12Z"/><path d="M9 15a3 3 0 0 0 3 3"/>'],
    ['pill', 'Фармакология', '<path d="M10 3h4v4h-4zM8 7h8l1 14H7L8 7Z"/><path d="M10 12h4m-2-2v4"/>'],
    ['syringe', 'Вакцинология', '<path d="m3 21 9-9m-6 3 3 3m0-9 6 6m-3-9 6 6M14 4l6 6m-4-8 4 4M4 20l-2 2"/>'],
    ['microscope', 'Микробиология', '<path d="m6 3 5 5-3 3-5-5 3-3Zm5 5 3-3m-8 9 5 5m-2-2 3-3m-9 8h16M14 4l4 4m-2-2 3-3M9 12a7 7 0 0 0 10 7"/>'],
    ['dna', 'Генетика', '<path d="M7 3c0 9 10 9 10 18M17 3c0 9-10 9-10 18M8 6h8M7 10h10m-10 4h10m-9 4h8"/>'],
    ['flask', 'Лаборатория', '<path d="M9 3h6m-5 0v7l-5.5 9a2 2 0 0 0 1.7 3h11.6a2 2 0 0 0 1.7-3L14 10V3M7 17h10"/>'],
    ['shield', 'Иммунология', '<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/>'],
    ['clipboard', 'Медицинское дело', '<path d="M9 4h6l1 2h3v15H5V6h3l1-2Z"/><path d="M9 12h6m-6 4h6m-3-7v6m-3-3h6"/>'],
    ['activity', 'Диагностика', '<path d="M3 12h4l3-8 4 16 3-8h4"/>'],
    ['baby', 'Педиатрия', '<circle cx="12" cy="8" r="5"/><path d="M9 9h.01M15 9h.01M10 12c1.3 1 2.7 1 4 0m-7 5-2 4m12-4 2 4M8 16h8v5H8z"/>'],
    ['chart', 'Статистика', '<path d="M4 19V9m5 10V5m5 14v-7m5 7V3M2 21h20"/>'],
    ['book', 'Общие дисциплины', '<path d="M4 4h6a3 3 0 0 1 3 3v14a3 3 0 0 0-3-3H4V4Zm16 0h-4a3 3 0 0 0-3 3v14a3 3 0 0 1 3-3h4V4Z"/>'],
  ];
  const byKey = Object.fromEntries(icons.map(([key, label, paths]) => [key, { key, label, paths }]));
  const validKeys = new Set(icons.map(([key]) => key));

  function iconSvg(key, className = 'w-6 h-6') {
    const icon = byKey[key] || byKey.stethoscope;
    return `<svg class="${className}" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icon.paths}</svg>`;
  }

  function suggestSubjectIcon(title = '') {
    const value = String(title).toLocaleLowerCase();
    const guesses = [
      [/лучев|radiolog|рентген|imaging/, 'scan'], [/озиз|здравоохран|public health|healthcare/, 'hospital'],
      [/серд|карди|heart|cardio/, 'heart'], [/мозг|невр|brain|neuro/, 'brain'],
      [/кост|анатом|bone|anatomy/, 'bone'], [/легк|пульмон|lung|pulmon/, 'lungs'],
      [/лекар|фармак|фармац|drug|pharma/, 'pill'], [/микроб|бактер|microb|bacter/, 'microscope'],
      [/генет|днк|genetic|dna/, 'dna'], [/глаз|офтальм|eye|ophthalm/, 'eye'],
      [/зуб|стомат|tooth|dental/, 'tooth'], [/кров|гемат|blood|hemat/, 'blood'],
      [/дет|педиатр|ребен|child|pediatr/, 'baby'], [/кож|дермат|skin|dermat/, 'skin'],
      [/иммун|вирус|вакцин|immun|virus/, 'shield'], [/лаборат|хими|лабо|lab|chem/, 'flask'],
    ];
    return guesses.find(([pattern]) => pattern.test(value))?.[1] || 'stethoscope';
  }

  window.SUBJECT_ICON_CATALOG = icons.map(([key, label]) => ({ key, label }));
  window.renderSubjectIcon = (key, fallback = '') => {
    if (validKeys.has(key)) return iconSvg(key);
    const safeText = String(fallback || '📚').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
    return `<span aria-hidden="true">${safeText}</span>`;
  };
  window.suggestSubjectIcon = suggestSubjectIcon;
})();
