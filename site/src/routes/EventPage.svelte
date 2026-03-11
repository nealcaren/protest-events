<script>
  import { onMount } from 'svelte'
  import { loadEvent, loadCampaigns, loadEvents } from '../lib/api.js'
  import Badge from '../components/Badge.svelte'
  import SourceBlock from '../components/SourceBlock.svelte'
  import EventCard from '../components/EventCard.svelte'
  import { formatLocation } from '../lib/utils.js'

  export let id

  let event = null
  let campaigns = []
  let relatedEvents = []

  onMount(load)
  $: if (id) load()

  async function load() {
    event = await loadEvent(id)
    if (!event) return

    if (event.campaign_ids?.length > 0) {
      const allCampaigns = await loadCampaigns()
      campaigns = allCampaigns.filter(c => event.campaign_ids.includes(c.id))

      const allEvents = await loadEvents()
      const relatedIds = new Set()
      for (const c of campaigns) {
        for (const eid of c.event_ids) {
          if (eid !== event.id) relatedIds.add(eid)
        }
      }
      relatedEvents = allEvents
        .filter(e => relatedIds.has(e.id))
        .sort((a, b) => a.date.localeCompare(b.date))
        .slice(0, 10)
    }
  }

  $: location = event ? formatLocation(event.location_city, event.location_state) : null
</script>

{#if event}
  <article class="event-page">
    <header>
      <div class="meta-row">
        <span class="date">{event.date}</span>
        <Badge type="event_type" value={event.event_type} />
        <Badge type="issue" value={event.issue_primary} />
        {#if event.issue_secondary}
          <Badge type="issue" value={event.issue_secondary} />
        {/if}
      </div>
      <h1>{event.description}</h1>
    </header>

    <div class="two-col">
      <div class="details">
        <h2>Details</h2>
        <dl>
          {#if location}
            <dt>Location</dt><dd>{location}</dd>
          {/if}
          {#if event.organizations?.length > 0}
            <dt>Organizations</dt><dd>{event.organizations.join(', ')}</dd>
          {/if}
          {#if event.individuals?.length > 0}
            <dt>Individuals</dt><dd>{event.individuals.join(', ')}</dd>
          {/if}
          {#if event.target}
            <dt>Target</dt><dd>{event.target}</dd>
          {/if}
          {#if event.tactics?.length > 0}
            <dt>Tactics</dt>
            <dd>
              {#each event.tactics as t}
                <Badge type="tactic" value={t.replace(/_/g, ' ')} />
              {/each}
            </dd>
          {/if}
          {#if event.size_text}
            <dt>Size</dt><dd>{event.size_text}</dd>
          {/if}
          {#if event.actor_type}
            <dt>Actor type</dt><dd>{event.actor_type.replace(/_/g, ' ')}</dd>
          {/if}
        </dl>

        {#if campaigns.length > 0}
          <h3>Campaigns</h3>
          {#each campaigns as c}
            <a href="#/campaigns/{c.id}"  class="campaign-link">
              {c.name}
            </a>
          {/each}
        {/if}
      </div>

      <div class="sources-col">
        <h2>Source Articles ({event.sources?.length || 0})</h2>
        {#each event.sources || [] as source}
          <SourceBlock {source} />
        {/each}
      </div>
    </div>

    {#if relatedEvents.length > 0}
      <section class="related">
        <h2>Related Events</h2>
        <div class="related-grid">
          {#each relatedEvents as re (re.id)}
            <EventCard event={re} />
          {/each}
        </div>
      </section>
    {/if}
  </article>
{:else}
  <p>Loading...</p>
{/if}

<style>
  .event-page {
    padding-top: 32px;
  }
  header {
    margin-bottom: 32px;
  }
  .meta-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  .date {
    font-size: 0.85rem;
    color: #888;
    font-weight: 600;
  }
  h1 {
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }
  .two-col {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 48px;
  }
  h2 {
    font-size: 1rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #888;
    margin-bottom: 16px;
  }
  h3 {
    font-size: 0.9rem;
    font-weight: 700;
    margin: 20px 0 8px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    font-size: 0.9rem;
  }
  dt {
    font-weight: 600;
    color: #888;
    white-space: nowrap;
  }
  dd {
    margin: 0;
  }
  .campaign-link {
    display: inline-block;
    padding: 4px 12px;
    background: #eee8f5;
    color: #5a3d8a;
    border-radius: 4px;
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 600;
    margin-right: 8px;
  }
  .campaign-link:hover { background: #ddd0ee; }

  .related {
    margin-top: 48px;
    padding-top: 32px;
    border-top: 1px solid #eee;
  }
  .related-grid {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  @media (max-width: 768px) {
    .two-col { grid-template-columns: 1fr; }
  }
</style>
