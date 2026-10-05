(() => {
  const root = document.documentElement;
  const body = document.body;
  const toggle = document.querySelector('[data-theme-toggle]');
  const themeIcon = toggle?.querySelector('[data-theme-icon]');
  const menuToggle = document.querySelector('[data-menu-toggle]');
  const menu = document.querySelector('[data-mobile-menu]');
  const localeSwitcher = document.querySelector('[data-locale-switcher]');
  const localeToggle = localeSwitcher?.querySelector('[data-locale-toggle]');
  const localeMenu = localeSwitcher?.querySelector('[data-locale-menu]');
  const commandPalette = document.querySelector('[data-command-palette]');
  const commandSearch = commandPalette?.querySelector('[data-command-search]');
  const commandItems = [...(commandPalette?.querySelectorAll('[data-command-item]') || [])];
  const sidebar = document.querySelector('[data-app-sidebar]');
  const sidebarBackdrop = document.querySelector('[data-sidebar-backdrop]');
  const userMenu = document.querySelector('[data-user-menu]');
  const userToggle = userMenu?.querySelector('[data-user-menu-toggle]');
  const userPopover = userMenu?.querySelector('[data-user-menu-popover]');

  const readCookie = (name) => document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]+)`))?.[1];

  const setTheme = (theme) => {
    const safeTheme = theme === 'dark' ? 'dark' : 'light';
    root.dataset.theme = safeTheme;
    document.cookie = `sanova_theme=${safeTheme}; Path=/; SameSite=Lax`;
    const hidden = document.getElementById('settings-theme');
    if (hidden) hidden.value = safeTheme;
    if (themeIcon) themeIcon.innerHTML = `<use href="#i-${safeTheme === 'dark' ? 'sun' : 'moon'}"></use>`;
    if (toggle) {
      const label = safeTheme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
      toggle.setAttribute('aria-label', label);
      toggle.title = label;
    }
  };

  setTheme(readCookie('sanova_theme') || root.dataset.theme || 'light');
  toggle?.addEventListener('click', () => setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark'));

  const setLocaleMenu = (open) => {
    if (!localeMenu || !localeToggle) return;
    localeMenu.hidden = !open;
    localeToggle.setAttribute('aria-expanded', String(open));
  };

  localeToggle?.addEventListener('click', (event) => {
    event.stopPropagation();
    setLocaleMenu(localeMenu?.hidden !== false);
  });

  localeMenu?.querySelectorAll('[data-locale]').forEach((item) => {
    item.addEventListener('click', () => {
      const locale = item.getAttribute('data-locale');
      if (!['en', 'id'].includes(locale)) return;
      document.cookie = `sanova_locale=${locale}; Path=/; SameSite=Lax`;
      window.location.reload();
    });
  });

  document.addEventListener('click', (event) => {
    if (localeSwitcher && !localeSwitcher.contains(event.target)) setLocaleMenu(false);
    if (userMenu && !userMenu.contains(event.target)) setUserMenu(false);
  });

  menuToggle?.addEventListener('click', () => {
    const open = menu?.getAttribute('data-open') === 'true';
    menu?.setAttribute('data-open', String(!open));
    menuToggle.setAttribute('aria-expanded', String(!open));
  });

  menu?.querySelectorAll('a,button:not([data-theme-toggle])').forEach((item) => {
    item.addEventListener('click', () => {
      menu.setAttribute('data-open', 'false');
      menuToggle?.setAttribute('aria-expanded', 'false');
    });
  });

  const setUserMenu = (open) => {
    if (!userPopover || !userToggle) return;
    userPopover.hidden = !open;
    userToggle.setAttribute('aria-expanded', String(open));
  };
  userToggle?.addEventListener('click', (event) => {
    event.stopPropagation();
    setUserMenu(userPopover?.hidden !== false);
  });

  const closeSidebar = () => {
    sidebar?.classList.remove('open');
    if (sidebarBackdrop) sidebarBackdrop.hidden = true;
  };
  document.querySelector('[data-sidebar-toggle]')?.addEventListener('click', () => {
    sidebar?.classList.toggle('open');
    if (sidebarBackdrop) sidebarBackdrop.hidden = !sidebar?.classList.contains('open');
  });
  sidebarBackdrop?.addEventListener('click', closeSidebar);

  document.querySelector('[data-sidebar-collapse]')?.addEventListener('click', () => {
    body.classList.toggle('sidebar-collapsed');
    localStorage.setItem('sanova_sidebar_collapsed', body.classList.contains('sidebar-collapsed') ? '1' : '0');
  });
  if (localStorage.getItem('sanova_sidebar_collapsed') === '1' && window.matchMedia('(min-width: 851px)').matches) {
    body.classList.add('sidebar-collapsed');
  }
  window.matchMedia('(max-width: 850px)').addEventListener?.('change', (event) => {
    if (event.matches) body.classList.remove('sidebar-collapsed');
  });

  const openCommandPalette = () => {
    if (!commandPalette) return;
    commandPalette.hidden = false;
    commandSearch?.focus();
    commandSearch?.select();
    closeSidebar();
  };
  const closeCommandPalette = () => {
    if (!commandPalette) return;
    commandPalette.hidden = true;
    if (commandSearch) commandSearch.value = '';
    commandItems.forEach((item) => { item.hidden = false; });
  };
  document.querySelectorAll('[data-command-open]').forEach((item) => item.addEventListener('click', openCommandPalette));
  commandPalette?.querySelectorAll('[data-command-close]').forEach((item) => item.addEventListener('click', closeCommandPalette));
  const commandSelection = { index: -1 };
  const setCommandSelection = (index) => {
    const visible = commandItems.filter((item) => !item.hidden);
    if (!visible.length) { commandSelection.index = -1; return; }
    commandSelection.index = (index + visible.length) % visible.length;
    visible.forEach((item, itemIndex) => item.classList.toggle('selected', itemIndex === commandSelection.index));
    visible[commandSelection.index]?.scrollIntoView({ block: 'nearest' });
  };
  commandSearch?.addEventListener('input', () => {
    const needle = commandSearch.value.trim().toLowerCase();
    commandItems.forEach((item) => { item.hidden = needle && !item.textContent.toLowerCase().includes(needle); });
    setCommandSelection(needle ? 0 : -1);
  });
  const activateCommandSelection = () => {
    const visible = commandItems.filter((item) => !item.hidden);
    if (commandSelection.index >= 0 && visible[commandSelection.index]) visible[commandSelection.index].click();
  };

  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      if (commandPalette?.hidden) openCommandPalette(); else closeCommandPalette();
    }
    if (!commandPalette?.hidden && commandSearch === document.activeElement) {
      if (event.key === 'ArrowDown') { event.preventDefault(); setCommandSelection(commandSelection.index + 1); return; }
      if (event.key === 'ArrowUp') { event.preventDefault(); setCommandSelection(commandSelection.index - 1); return; }
      if (event.key === 'Enter') { event.preventDefault(); activateCommandSelection(); return; }
    }
    if (event.key === 'Escape') {
      closeCommandPalette();
      setLocaleMenu(false);
      setUserMenu(false);
      closeSidebar();
      closeTaskDrawer();
      document.querySelectorAll('[data-integration-row].expanded').forEach((row) => row.classList.remove('expanded'));
    }
  });

  const settingsProviders = window.sanovaAIProviders || null;
  const providerSelect = document.getElementById('settings-ai-provider');
  const modelSelect = document.getElementById('settings-ai-model');
  const syncModels = (provider, select) => {
    if (!settingsProviders || !select) return;
    const models = settingsProviders[provider] || [];
    select.innerHTML = models.map((m) => `<option value="${m.model}">${m.label}</option>`).join('');
  };
  providerSelect?.addEventListener('change', () => syncModels(providerSelect.value, modelSelect));

  const aiProvider = document.getElementById('ai-provider');
  const aiModel = document.getElementById('ai-model');
  const aiProviders = window.sanovaAIProviders || {};
  aiProvider?.addEventListener('change', () => {
    const models = aiProviders[aiProvider.value] || [];
    if (!aiModel) return;
    aiModel.innerHTML = models.map((m) => `<option value="${m.model}">${m.label}</option>`).join('');
  });

  document.querySelectorAll('[data-autogrow]').forEach((textarea) => {
    const resize = () => { textarea.style.height = 'auto'; textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`; };
    textarea.addEventListener('input', resize);
    resize();
  });

  document.querySelectorAll('[data-submit-shortcut]').forEach((textarea) => {
    textarea.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        textarea.form?.requestSubmit();
      }
    });
  });

  document.querySelectorAll('[data-hint]').forEach((button) => {
    button.addEventListener('click', () => {
      const target = document.getElementById(button.getAttribute('data-hint-target'));
      if (!target) return;
      target.value = button.getAttribute('data-hint') || '';
      target.focus();
      target.dispatchEvent(new Event('input', { bubbles: true }));
    });
  });

  const taskCards = [...document.querySelectorAll('[data-task-card]')];
  const taskSearch = document.querySelector('[data-task-search]');
  const filterButtons = [...document.querySelectorAll('[data-task-filter]')];
  let activeFilter = 'all';
  const updateTaskBoard = () => {
    const needle = (taskSearch?.value || '').trim().toLowerCase();
    taskCards.forEach((card) => {
      const matchesFilter = activeFilter === 'all' || card.dataset.taskState === activeFilter;
      const matchesSearch = !needle || card.textContent.toLowerCase().includes(needle);
      card.classList.toggle('hidden', !(matchesFilter && matchesSearch));
    });
    document.querySelectorAll('[data-board-column]').forEach((column) => {
      const state = column.getAttribute('data-board-column');
      const count = column.querySelectorAll('[data-task-card]:not(.hidden)').length;
      const countNode = column.querySelector('[data-board-count]');
      if (countNode) countNode.textContent = String(count);
      const empty = column.querySelector('[data-board-empty]');
      if (empty) empty.hidden = count !== 0;
    });
  };
  taskSearch?.addEventListener('input', updateTaskBoard);
  filterButtons.forEach((button) => button.addEventListener('click', () => {
    activeFilter = button.dataset.taskFilter || 'all';
    filterButtons.forEach((item) => item.classList.toggle('active', item === button));
    updateTaskBoard();
  }));

  const taskDrawer = document.querySelector('[data-task-drawer]');
  const drawerForm = taskDrawer?.querySelector('[data-task-webhook-form]');
  const drawerTitle = taskDrawer?.querySelector('[data-drawer-task-title]');
  const drawerId = taskDrawer?.querySelector('[data-drawer-task-id]');
  const drawerState = taskDrawer?.querySelector('[data-drawer-task-state]');
  const drawerProvider = taskDrawer?.querySelector('[data-drawer-task-provider]');
  const drawerMessage = taskDrawer?.querySelector('[data-drawer-task-message]');
  const closeTaskDrawer = () => { if (!taskDrawer) return; taskDrawer.hidden = true; taskDrawer.classList.remove('drawer-open'); };
  taskDrawer?.querySelectorAll('[data-drawer-close]').forEach((button) => button.addEventListener('click', closeTaskDrawer));
  const openTaskCard = (card) => {
    if (!taskDrawer) return;
    drawerTitle.textContent = card.dataset.taskTitle || 'Task';
    drawerId.textContent = card.dataset.taskId || '—';
    drawerState.textContent = card.dataset.taskState || '—';
    drawerProvider.textContent = card.dataset.taskProvider || '—';
    drawerMessage.textContent = card.dataset.taskMessage || 'No message recorded.';
    if (drawerForm) drawerForm.action = `/app/tasks/${encodeURIComponent(card.dataset.taskId || '')}/webhook`;
    taskDrawer.hidden = false;
    requestAnimationFrame(() => taskDrawer.classList.add('drawer-open'));
  };
  taskCards.forEach((card) => {
    card.addEventListener('click', () => openTaskCard(card));
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openTaskCard(card); }
    });
  });
  updateTaskBoard();

  document.querySelectorAll('[data-tabs]').forEach((tabset) => {
    const tabs = [...tabset.querySelectorAll('[data-tab]')];
    const panels = [...tabset.querySelectorAll('[data-tab-panel]')];
    tabs.forEach((tab) => tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-tab');
      tabs.forEach((item) => item.classList.toggle('active', item === tab));
      panels.forEach((panel) => panel.classList.toggle('active', panel.getAttribute('data-tab-panel') === target));
    }));
  });

  document.querySelectorAll('[data-integration-row]').forEach((row) => {
    row.querySelector('[data-integration-toggle]')?.addEventListener('click', () => {
      row.classList.toggle('expanded');
    });
  });
})();

/* ==========================================================================
   Product showcase — auto-playing cursor demo that visitors can take over
   ========================================================================== */
(() => {
  const win = document.querySelector('[data-showcase]');
  if (!win) return;

  const navs = [...win.querySelectorAll('[data-sc-nav]')];
  const panels = [...win.querySelectorAll('[data-sc-panel]')];
  const cursor = win.querySelector('[data-sc-cursor]');
  const title = win.querySelector('[data-sc-title]');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const IDLE_RESUME_MS = 7000;

  /* ---- state ---- */
  let token = 0;          // bumping this cancels the running demo
  let current = 0;
  let idleTimer = null;
  let inView = false;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const show = (index) => {
    current = index;
    navs.forEach((nav, i) => {
      const on = i === index;
      nav.classList.toggle('is-active', on);
      nav.setAttribute('aria-selected', String(on));
    });
    panels.forEach((panel, i) => panel.classList.toggle('is-active', i === index));
    if (title) title.textContent = navs[index].querySelector('span')?.textContent || '';
  };

  navs.forEach((nav, i) => nav.addEventListener('click', () => show(i)));

  /* clicking a selectable item highlights it inside its group */
  win.addEventListener('click', (event) => {
    const hit = event.target.closest('[data-hit]');
    if (!hit) return;
    const group = hit.dataset.hit;
    win.querySelectorAll(`[data-hit="${group}"]`).forEach((item) => item.classList.toggle('is-on', item === hit));
    const reply = hit.dataset.reply;
    const slot = reply && win.querySelector('[data-sc-reply]');
    if (slot) {
      slot.textContent = reply;
      slot.classList.remove('sc-fade');
      void slot.offsetWidth;
      slot.classList.add('sc-fade');
    }
  });

  /* ---- cursor helpers ---- */
  const point = (el, fx = 0.5, fy = 0.5) => {
    const w = win.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    return [r.left - w.left + r.width * fx, r.top - w.top + r.height * fy];
  };

  const placeCursor = (x, y, animate = true) => {
    if (!animate) cursor.style.transition = 'none';
    cursor.style.transform = `translate(${x}px, ${y}px)`;
    if (!animate) {
      void cursor.offsetWidth;
      cursor.style.transition = '';
    }
  };

  const ripple = (x, y) => {
    const dot = document.createElement('span');
    dot.className = 'sc-ripple';
    dot.style.left = `${x}px`;
    dot.style.top = `${y}px`;
    win.appendChild(dot);
    setTimeout(() => dot.remove(), 650);
  };

  const moveTo = async (el, my, fx = 0.4, fy = 0.5) => {
    const [x, y] = point(el, fx, fy);
    placeCursor(x, y);
    await sleep(1150);
    return my === token;
  };

  const press = async (el, my) => {
    const [x, y] = point(el, 0.4, 0.5);
    cursor.classList.add('is-click');
    ripple(x, y);
    await sleep(110);
    if (my !== token) return false;
    el.click();               // programmatic: not a trusted pointer event, so it never triggers takeover
    await sleep(140);
    cursor.classList.remove('is-click');
    return my === token;
  };

  /* ---- the scripted demo ---- */
  const demo = async (my) => {
    const start = navs[current];
    const [sx, sy] = point(win.querySelector('.sc-main'), 0.62, 0.32);
    placeCursor(sx, sy, false);
    cursor.classList.add('is-on');
    await sleep(500);

    let step = current;
    while (my === token) {
      step = (step + 1) % navs.length;
      if (!(await moveTo(navs[step], my))) return;
      if (!(await press(navs[step], my))) return;
      await sleep(850);
      if (my !== token) return;

      const target = panels[step].querySelector('[data-demo]');
      if (target) {
        if (!(await moveTo(target, my, 0.5, 0.5))) return;
        if (!(await press(target, my))) return;
      }
      await sleep(1900);
    }
    void start;
  };

  const stop = () => {
    token += 1;
    cursor.classList.remove('is-on', 'is-click');
  };

  const start = () => {
    if (reduceMotion || !inView || document.hidden) return;
    clearTimeout(idleTimer);
    token += 1;
    demo(token);
  };

  /* visitor takes over on any real interaction, demo resumes after a quiet period */
  const takeOver = (event) => {
    if (event && event.isTrusted === false) return;
    stop();
    clearTimeout(idleTimer);
    idleTimer = setTimeout(start, IDLE_RESUME_MS);
  };
  ['pointerdown', 'pointermove', 'keydown', 'focusin', 'wheel', 'touchstart'].forEach((name) =>
    win.addEventListener(name, takeOver, { passive: true })
  );

  /* only run while on screen and tab visible */
  if ('IntersectionObserver' in window) {
    new IntersectionObserver((entries) => {
      inView = entries[0].isIntersecting;
      if (inView) { if (!idleTimer) start(); else { clearTimeout(idleTimer); idleTimer = setTimeout(start, 1200); } }
      else { stop(); clearTimeout(idleTimer); idleTimer = null; }
    }, { threshold: 0.4 }).observe(win);
  } else {
    inView = true;
    start();
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { stop(); clearTimeout(idleTimer); idleTimer = null; }
    else if (inView) start();
  });

  show(0);
})();

/* ==========================================================================
   Auth pages — live greeting, validation feedback, orbit reactions
   ========================================================================== */
(() => {
  const root = document.querySelector('[data-auth]');
  if (!root) return;

  const mode = root.dataset.auth;
  let tx = {};
  try { tx = JSON.parse(root.querySelector('[data-auth-i18n]')?.textContent || '{}'); } catch (_) { tx = {}; }

  const form = root.querySelector('form');
  const email = form.querySelector('input[type=email]');
  const pass = form.querySelector('input[type=password]');
  const submit = form.querySelector('[data-submit]');
  const toggle = form.querySelector('[data-pw-toggle]');
  const orbit = root.querySelector('[data-auth-orbit]');
  const title = root.querySelector('[data-auth-title]');
  const greet = root.querySelector('[data-auth-greet]');
  const card = root.querySelector('.auth-card');
  const emailField = email.closest('.field');
  const passField = pass.closest('.field');
  const emailHint = form.querySelector('[data-hint=email]');
  const passHint = form.querySelector('[data-hint=password]');
  const strength = form.querySelector('[data-strength]');
  const checks = Object.fromEntries([...root.querySelectorAll('[data-check]')].map((li) => [li.dataset.check, li]));
  const nodes = [...(orbit?.querySelectorAll('.auth-node') || [])];
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const validEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim());
  const idleHint = passHint?.textContent || '';

  /* ---- greeting by time of day ---- */
  const hour = new Date().getHours();
  const slot = hour >= 5 && hour < 11 ? 'morning' : hour < 15 && hour >= 11 ? 'afternoon' : hour >= 15 && hour < 19 ? 'evening' : 'night';
  const greeting = tx.greet?.[slot];
  if (greet && greeting) greet.textContent = greeting;

  /* ---- headline that greets the person once the email looks real ---- */
  const baseTitle = title?.textContent || '';
  let wanted = baseTitle;
  const setTitle = (text) => {
    if (!title || text === wanted) return;
    wanted = text;
    title.classList.add('is-swapping');
    setTimeout(() => {
      title.textContent = wanted;
      title.classList.remove('is-swapping');
    }, 200);
  };
  const nameFrom = (value) => {
    const local = value.trim().split('@')[0];
    let first = local.split(/[._+\-]/)[0] || local;
    if (/^\d+$/.test(first)) first = local;
    first = first.slice(0, 18);
    return first.charAt(0).toUpperCase() + first.slice(1);
  };
  let titleTimer = null;
  const refreshTitle = () => {
    if (mode !== 'login') return;
    clearTimeout(titleTimer);
    titleTimer = setTimeout(() => {
      setTitle(validEmail(email.value) && greeting ? `${greeting}, ${nameFrom(email.value)}.` : baseTitle);
    }, 280);
  };

  /* ---- orbit + checklist ---- */
  const setState = (state) => { if (orbit) orbit.dataset.state = state; };
  let level = 0;
  const syncProgress = () => {
    const emailOk = validEmail(email.value);
    const passOk = level >= 3;
    const ready = emailOk && passOk;
    checks.email?.classList.toggle('is-done', emailOk);
    checks.pass?.classList.toggle('is-done', passOk);
    checks.ready?.classList.toggle('is-done', ready);
    const lit = Number(emailOk) + Number(passOk) + Number(ready);
    nodes.forEach((node, i) => node.classList.toggle('is-lit', i < lit));
    orbit?.classList.toggle('is-ready', ready);
  };

  /* ---- email ---- */
  email.addEventListener('input', () => {
    const ok = validEmail(email.value);
    emailField.classList.toggle('is-valid', ok);
    if (ok) {
      emailField.classList.remove('is-invalid');
      emailHint.textContent = '';
      emailHint.classList.remove('is-warn');
    }
    refreshTitle();
    syncProgress();
  });
  email.addEventListener('blur', () => {
    if (email.value && !validEmail(email.value)) {
      emailField.classList.add('is-invalid');
      emailHint.textContent = tx.email_bad || '';
      emailHint.classList.add('is-warn');
    }
  });

  /* ---- password ---- */
  const scorePassword = (value) => {
    if (!value) return 0;
    let score = 0;
    if (value.length >= 8) score += 1;
    if (value.length >= 12) score += 1;
    if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score += 1;
    if (/\d/.test(value)) score += 1;
    if (/[^A-Za-z0-9]/.test(value)) score += 1;
    return Math.max(1, Math.min(4, score));
  };
  const showPassHint = (text, warn) => {
    passHint.textContent = text;
    passHint.classList.toggle('is-warn', Boolean(warn));
  };

  pass.addEventListener('input', () => {
    passField.classList.remove('is-invalid');
    if (strength) {
      level = scorePassword(pass.value);
      strength.dataset.level = String(level);
      showPassHint(level ? tx.strength?.[level] || '' : idleHint);
    }
    syncProgress();
  });
  pass.addEventListener('focus', () => setState('locked'));
  pass.addEventListener('blur', () => {
    setState('idle');
    if (!strength || !pass.value) showPassHint(strength ? idleHint : '');
  });
  const capsCheck = (event) => {
    if (!event.getModifierState) return;
    if (event.getModifierState('CapsLock')) showPassHint(tx.caps || '', true);
    else if (passHint.classList.contains('is-warn')) showPassHint(strength && level ? tx.strength?.[level] || '' : strength ? idleHint : '');
  };
  pass.addEventListener('keydown', capsCheck);
  pass.addEventListener('keyup', capsCheck);

  toggle?.addEventListener('click', () => {
    const show = pass.type === 'password';
    pass.type = show ? 'text' : 'password';
    toggle.textContent = show ? tx.hide : tx.show;
    toggle.setAttribute('aria-pressed', String(show));
    pass.focus({ preventScroll: true });
  });

  /* ---- submit ---- */
  const nudge = (field, input) => {
    field.classList.add('is-invalid', 'shake');
    setTimeout(() => field.classList.remove('shake'), 450);
    input.focus();
  };
  form.addEventListener('submit', (event) => {
    if (form.dataset.sent) { event.preventDefault(); return; }
    if (!validEmail(email.value)) {
      event.preventDefault();
      emailHint.textContent = tx.email_bad || '';
      emailHint.classList.add('is-warn');
      nudge(emailField, email);
      return;
    }
    if (!pass.value) {
      event.preventDefault();
      nudge(passField, pass);
      return;
    }
    form.dataset.sent = '1';
    setState('sending');
    submit.classList.add('is-loading');
    submit.setAttribute('aria-busy', 'true');
    if (tx.busy) submit.textContent = tx.busy;
  });
  window.addEventListener('pageshow', (event) => {
    if (!event.persisted) return;
    delete form.dataset.sent;
    submit.classList.remove('is-loading');
    submit.removeAttribute('aria-busy');
    setState('idle');
  });

  /* ---- pointer effects (fine pointers only) ---- */
  if (!reduceMotion && window.matchMedia('(pointer: fine)').matches) {
    card?.addEventListener('pointermove', (event) => {
      const rect = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${event.clientX - rect.left}px`);
      card.style.setProperty('--my', `${event.clientY - rect.top}px`);
    });
    let frame = 0;
    root.addEventListener('pointermove', (event) => {
      if (!orbit || frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const rect = root.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - 0.5;
        const y = (event.clientY - rect.top) / rect.height - 0.5;
        orbit.style.transform = `rotateX(${(-y * 10).toFixed(2)}deg) rotateY(${(x * 14).toFixed(2)}deg)`;
      });
    });
    root.addEventListener('pointerleave', () => { if (orbit) orbit.style.transform = ''; });
  }

  /* ---- start ---- */
  syncProgress();
  if (!form.querySelector('.alert') && !root.querySelector('.alert') && !email.value && window.matchMedia('(pointer: fine)').matches) {
    setTimeout(() => email.focus({ preventScroll: true }), 650);
  }
})();
