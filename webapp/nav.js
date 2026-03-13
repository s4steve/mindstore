(function () {
  const links = [
    { href: '/',          label: 'capture' },
    { href: '/tasks.html',    label: 'tasks' },
    { href: '/contacts.html', label: 'contacts' },
    { href: '/home.html',     label: 'home' },
  ];

  const nav = document.createElement('nav');
  nav.style.cssText = [
    'display:flex', 'gap:0', 'background:var(--bg-1)',
    'border-bottom:1px solid var(--border)',
    'padding:0 28px', 'flex-shrink:0',
  ].join(';');

  const path = location.pathname;

  links.forEach(({ href, label }) => {
    const a = document.createElement('a');
    a.href = href;
    a.textContent = label;
    const isActive = href === '/' ? path === '/' || path === '/index.html' : path === href;
    a.style.cssText = [
      'display:inline-block', 'padding:8px 16px 7px',
      'font-size:10px', 'letter-spacing:0.12em', 'text-transform:uppercase',
      'text-decoration:none', 'border-bottom:2px solid transparent',
      isActive
        ? 'color:var(--accent);border-bottom-color:var(--accent)'
        : 'color:var(--text-dim)',
    ].join(';');
    nav.appendChild(a);
  });

  const header = document.querySelector('header');
  if (header) header.insertAdjacentElement('afterend', nav);
})();
