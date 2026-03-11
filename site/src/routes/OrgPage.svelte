<script>
  import { onMount } from 'svelte'
  import { loadOrg, loadEvents } from '../lib/api.js'
  import Badge from '../components/Badge.svelte'
  import EventCard from '../components/EventCard.svelte'
  import { formatPaperName } from '../lib/utils.js'

  export let id

  let org = null
  let events = []

  onMount(load)
  $: if (id) load()

  async function load() {
    org = await loadOrg(id)
    if (!org) return

    const allEvents = await loadEvents()
    const idSet = new Set(org.event_ids)
    events = allEvents
      .filter(e => idSet.has(e.id))
      .sort((a, b) => (a.date || '').localeCompare(b.date || ''))
  }

  $: coOrgs = (() => {
    if (!events.length) return []
    const counts = {}
    for (const e of events) {
      for (const o of (e.organizations || [])) {
        if (o !== org?.name) counts[o] = (counts[o] || 0) + 1
      }
    }
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20)
  })()

  $: issueEntries = org ? Object.entries(org.issue_counts || {}).sort((a, b) => b[1] - a[1]) : []
</script>

{#if org}
  <div class="org-page">
    <header>
      <Badge type="issue" value={org.issue_primary} />
      <h1>{org.name}</h1>
      <p class="meta">{org.date_start} &mdash; {org.date_end} &middot; {org.event_count} events &middot; {org.newspapers?.length || 0} newspapers</p>
    </header>

    <div class="sidebar-layout">
      <aside>
        {#if issueEntries.length > 0}
          <h3>Issues</h3>
          <ul class="issue-list">
            {#each issueEntries as [issue, count]}
              <li>
                <Badge type="issue" value={issue} />
                <span class="issue-count">{count}</span>
              </li>
            {/each}
          </ul>
        {/if}

        {#if org.newspapers?.length > 0}
          <h3>Newspapers ({org.newspapers.length})</h3>
          <ul>
            {#each org.newspapers as p}
              <li>{formatPaperName(p)}</li>
            {/each}
          </ul>
        {/if}

        {#if coOrgs.length > 0}
          <h3>Co-occurring Orgs</h3>
          <ul>
            {#each coOrgs as [name, count]}
              <li>{name} <span class="co-count">({count})</span></li>
            {/each}
          </ul>
        {/if}
      </aside>

      <div class="events-col">
        <h2>Events ({events.length})</h2>
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
  .org-page { padding-top: 32px; }
  header { margin-bottom: 32px; }
  h1 { font-size: 1.8rem; font-weight: 800; margin: 8px 0 4px; }
  .meta { color: #888; font-size: 0.9rem; }
  .sidebar-layout {
    display: grid; grid-template-columns: 260px 1fr; gap: 48px;
  }
  aside h3 {
    font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em;
    color: #888; margin: 20px 0 8px; font-weight: 600;
  }
  aside h3:first-child { margin-top: 0; }
  ul { list-style: none; padding: 0; }
  li { font-size: 0.85rem; padding: 3px 0; }
  .issue-list li {
    display: flex; align-items: center; gap: 8px;
  }
  .issue-count {
    font-size: 0.8rem; color: #888; font-variant-numeric: tabular-nums;
  }
  .co-count { color: #888; font-size: 0.8rem; }
  h2 {
    font-size: 1rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.04em; color: #888; margin-bottom: 16px;
  }
  .events-col { display: flex; flex-direction: column; gap: 12px; }

  @media (max-width: 768px) {
    .sidebar-layout { grid-template-columns: 1fr; }
  }
</style>
