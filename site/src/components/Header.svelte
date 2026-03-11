<script>
  import { currentPath } from '../lib/router.js'
  let path = '/'
  currentPath.subscribe(v => path = v)
</script>

<header>
  <div class="header-inner">
    <a href="#/" class="logo">Protest Events</a>
    <nav>
      <a href="#/events" class:active={path === '/events' || path.startsWith('/events/')}>Browse</a>
      <a href="#/campaigns" class:active={path === '/campaigns' || path.startsWith('/campaigns/')}>Campaigns</a>
      <a href="#/orgs" class:active={path === '/orgs' || path.startsWith('/orgs/')}>Organizations</a>
    </nav>
  </div>
</header>

<style>
  header {
    background: #1a1a1a;
    color: white;
    padding: 0 24px;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .header-inner {
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
  }
  .logo {
    color: white;
    text-decoration: none;
    font-weight: 700;
    font-size: 1.1rem;
    letter-spacing: -0.02em;
  }
  nav {
    display: flex;
    gap: 24px;
  }
  nav a {
    color: rgba(255,255,255,0.7);
    text-decoration: none;
    font-size: 0.9rem;
    font-weight: 500;
  }
  nav a:hover, nav a.active {
    color: white;
  }
</style>
