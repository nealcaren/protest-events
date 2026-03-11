<script>
  import { onMount } from 'svelte'
  import { loadCampaign, loadEvents } from '../lib/api.js'
  import Badge from '../components/Badge.svelte'
  import EventCard from '../components/EventCard.svelte'
  import { formatPaperName } from '../lib/utils.js'

  export let id

  let campaign = null
  let events = []

  onMount(load)
  $: if (id) load()

  async function load() {
    campaign = await loadCampaign(id)
    if (!campaign) return

    const allEvents = await loadEvents()
    const idSet = new Set(campaign.event_ids)
    events = allEvents
      .filter(e => idSet.has(e.id))
      .sort((a, b) => a.date.localeCompare(b.date))
  }

  $: papers = [...new Set(events.flatMap(e => (e.sources || []).map(s => s.paper)))]
  $: orgs = [...new Set(events.flatMap(e => e.organizations || []))]
  $: individuals = [...new Set(events.flatMap(e => e.individuals || []))]
</script>

{#if campaign}
  <div class="campaign-page">
    <header>
      <Badge type="issue" value={campaign.issue_primary} />
      {#if !campaign.named}<span class="algo-tag">algorithmically detected</span>{/if}
      <h1>{campaign.name}</h1>
      <p class="date-range">{campaign.date_start} &mdash; {campaign.date_end} &middot; {events.length} events</p>
    </header>

    <div class="sidebar-layout">
      <aside>
        {#if papers.length > 0}
          <h3>Newspapers ({papers.length})</h3>
          <ul>
            {#each papers as p}
              <li>{formatPaperName(p)}</li>
            {/each}
          </ul>
        {/if}
        {#if orgs.length > 0}
          <h3>Organizations</h3>
          <ul>
            {#each orgs.slice(0, 15) as o}
              <li>{o}</li>
            {/each}
            {#if orgs.length > 15}<li class="more">+{orgs.length - 15} more</li>{/if}
          </ul>
        {/if}
        {#if individuals.length > 0}
          <h3>Individuals</h3>
          <ul>
            {#each individuals.slice(0, 15) as i}
              <li>{i}</li>
            {/each}
            {#if individuals.length > 15}<li class="more">+{individuals.length - 15} more</li>{/if}
          </ul>
        {/if}
      </aside>

      <div class="events-col">
        <h2>Events</h2>
        {#each events as event (event.id)}
          <EventCard {event} />
        {/each}
      </div>
    </div>
  </div>
{:else}
  <p>Loading...</p>
{/if}

<style>
  .campaign-page { padding-top: 32px; }
  header { margin-bottom: 32px; }
  h1 { font-size: 1.8rem; font-weight: 800; margin: 8px 0 4px; }
  .date-range { color: #888; font-size: 0.9rem; }
  .algo-tag {
    font-size: 0.7rem; background: #f0f0f0; padding: 2px 8px;
    border-radius: 3px; color: #888;
  }
  .sidebar-layout {
    display: grid; grid-template-columns: 240px 1fr; gap: 48px;
  }
  aside h3 {
    font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em;
    color: #888; margin: 20px 0 8px; font-weight: 600;
  }
  aside h3:first-child { margin-top: 0; }
  ul { list-style: none; padding: 0; }
  li { font-size: 0.85rem; padding: 3px 0; }
  .more { color: #888; font-style: italic; }
  h2 {
    font-size: 1rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.04em; color: #888; margin-bottom: 16px;
  }
  .events-col { display: flex; flex-direction: column; gap: 12px; }

  @media (max-width: 768px) {
    .sidebar-layout { grid-template-columns: 1fr; }
  }
</style>
