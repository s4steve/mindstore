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

  const style = document.createElement('style');
  style.textContent = `
    nav.site-nav {
      display: flex;
      gap: 0;
      padding: 0 40px;
      border-bottom: 1px solid #183448;
      flex-shrink: 0;
    }
    nav.site-nav a {
      display: inline-block;
      padding: 9px 16px 8px;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      text-decoration: none;
      color: #1e3a50;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: color 0.15s, border-color 0.15s;
    }
    nav.site-nav a:hover { color: #c0dff0; }
    nav.site-nav a.active { color: #0fbfa6; border-bottom-color: #0fbfa6; }
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

  const header = document.querySelector('header');
  if (header) header.insertAdjacentElement('afterend', nav);
})();
