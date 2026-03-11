<script>
  import { currentPath, matchRoute } from './lib/router.js'
  import Header from './components/Header.svelte'
  import Dashboard from './routes/Dashboard.svelte'
  import EventList from './routes/EventList.svelte'
  import EventPage from './routes/EventPage.svelte'
  import CampaignList from './routes/CampaignList.svelte'
  import CampaignPage from './routes/CampaignPage.svelte'
  import OrgList from './routes/OrgList.svelte'
  import OrgPage from './routes/OrgPage.svelte'
  import OrgNetwork from './routes/OrgNetwork.svelte'

  let path = '/'
  currentPath.subscribe(v => path = v)

  $: eventParams = matchRoute(path, '/events/:id')
  $: campaignParams = matchRoute(path, '/campaigns/:id')
  $: orgParams = matchRoute(path, '/orgs/:id')
</script>

<Header />
<main>
  {#if path === '/'}
    <Dashboard />
  {:else if path === '/events'}
    <EventList />
  {:else if eventParams}
    <EventPage id={eventParams.id} />
  {:else if path === '/campaigns'}
    <CampaignList />
  {:else if campaignParams}
    <CampaignPage id={campaignParams.id} />
  {:else if path === '/orgs'}
    <OrgList />
  {:else if path === '/orgs/network'}
    <OrgNetwork />
  {:else if orgParams}
    <OrgPage id={orgParams.id} />
  {:else}
    <div class="not-found">
      <h1>Page not found</h1>
      <p><a href="#/">Back to dashboard</a></p>
    </div>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #fafafa;
    color: #1a1a1a;
    line-height: 1.6;
  }
  main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px 48px;
  }
  .not-found {
    text-align: center;
    padding: 48px 0;
  }
</style>
