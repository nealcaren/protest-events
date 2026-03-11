<script>
  import Badge from './Badge.svelte'
  import { formatPaperName, formatLocation } from '../lib/utils.js'

  export let event

  $: location = formatLocation(event.location_city, event.location_state)
  $: sourceCount = event.sources?.length || 0
</script>

<a href="#/events/{event.id}" class="event-card">
  <div class="card-top">
    <span class="date">{event.date}</span>
    <div class="badges">
      <Badge type="event_type" value={event.event_type} />
      <Badge type="issue" value={event.issue_primary} />
    </div>
  </div>

  <p class="description">{event.description}</p>

  <div class="card-bottom">
    {#if location}
      <span class="meta">{location}</span>
    {/if}
    {#if sourceCount > 1}
      <span class="meta">{sourceCount} sources</span>
    {:else if event.sources?.[0]}
      <span class="meta">{formatPaperName(event.sources[0].paper)}</span>
    {/if}
    {#if event.campaign_ids?.length > 0}
      <Badge type="campaign" value="Campaign" />
    {/if}
  </div>
</a>

<style>
  .event-card {
    display: block;
    background: white;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    text-decoration: none;
    color: inherit;
    transition: box-shadow 0.15s;
  }
  .event-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  }
  .card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .date {
    font-size: 0.8rem;
    color: #888;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .badges {
    display: flex;
    gap: 6px;
  }
  .description {
    font-size: 0.95rem;
    font-weight: 600;
    line-height: 1.4;
    margin: 0 0 12px;
    color: #1a1a1a;
  }
  .card-bottom {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }
  .meta {
    font-size: 0.8rem;
    color: #888;
  }
</style>
