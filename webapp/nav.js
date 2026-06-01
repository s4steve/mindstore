(function () {
  const links = [
    { href: '/',             label: 'capture' },
    { href: '/tasks.html',   label: 'tasks' },
    { href: '/contacts.html',label: 'contacts' },
    { href: '/home.html',    label: 'home' },
    { href: '/wiki.html',    label: 'wiki' },
  ];

  // Inject font if not already present
  if (!document.querySelector('link[href*="IBM+Plex+Mono"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@0,400;0,500&display=swap';
    document.head.appendChild(link);
  }

  // Styled with the site's CSS variables (with light-theme fallbacks) so the
  // nav stays consistent on every page, including ones not yet migrated to
  // styles.css. The previous hard-coded dark-theme colors were invisible on
  // the light background.
  const style = document.createElement('style');
  style.textContent = `
    nav.site-nav {
      display: flex;
      gap: 2px;
      padding: 0 40px;
      border-bottom: 1px solid var(--border, #d2e0ea);
      flex-shrink: 0;
    }
    nav.site-nav a {
      display: inline-block;
      padding: 11px 16px 10px;
      font-family: var(--mono, 'JetBrains Mono', monospace);
      font-size: 10px;
      font-weight: 500;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      text-decoration: none;
      color: var(--text-3, #89a8bc);
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: color 0.16s, border-color 0.16s;
    }
    nav.site-nav a:hover { color: var(--text, #0c1f2e); }
    nav.site-nav a.active { color: var(--teal, #0a9e90); border-bottom-color: var(--teal, #0a9e90); }
    nav.site-nav .spacer { flex: 1; }
    nav.site-nav a.logout { color: var(--text-3, #89a8bc); }
    nav.site-nav a.logout:hover { color: var(--red, #cc3a3a); }
  `;
  document.head.appendChild(style);

  const nav = document.createElement('nav');
  nav.className = 'site-nav';

  const path = location.pathname;
  links.forEach(({ href, label }) => {
    const a = document.createElement('a');
    a.href = href;
    a.textContent = label;
    const isActive = href === '/' ? path === '/' || path === '/index.html' : path === href;
    if (isActive) a.classList.add('active');
    nav.appendChild(a);
  });

  const spacer = document.createElement('span');
  spacer.className = 'spacer';
  nav.appendChild(spacer);

  const logout = document.createElement('a');
  logout.href = '/api/auth/logout';
  logout.textContent = 'logout';
  logout.className = 'logout';
  nav.appendChild(logout);

  const header = document.querySelector('header');
  if (header) header.insertAdjacentElement('afterend', nav);
})();
