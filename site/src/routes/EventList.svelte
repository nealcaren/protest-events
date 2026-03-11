<script>
  import { onMount } from 'svelte'
  import { loadEvents, loadMeta } from '../lib/api.js'
  import { buildSearchIndex, searchEvents } from '../lib/search.js'
  import { filters } from '../lib/stores.js'
  import EventCard from '../components/EventCard.svelte'
  import FacetSidebar from '../components/FacetSidebar.svelte'
  import Pagination from '../components/Pagination.svelte'

  let allEvents = []
  let meta = null
  let currentPage = 1
  const perPage = 50

  onMount(async () => {
    allEvents = await loadEvents()
    meta = await loadMeta()
    buildSearchIndex(allEvents)
  })

  $: availableIssues = [...new Set(allEvents.map(e => e.issue_primary).filter(Boolean))].sort()
  $: availableTactics = [...new Set(allEvents.flatMap(e => e.tactics || []))].sort()
  $: availablePapers = meta?.newspaper_list || []

  $: filtered = (() => {
    let result = allEvents

    if ($filters.searchText) {
      const searched = searchEvents($filters.searchText)
      if (searched) result = searched
    }

    if ($filters.issues.length > 0) {
      result = result.filter(e => $filters.issues.includes(e.issue_primary))
    }

    if ($filters.papers.length > 0) {
      result = result.filter(e =>
        e.sources?.some(s => $filters.papers.includes(s.paper))
      )
    }

    if ($filters.actorType) {
      result = result.filter(e => e.actor_type === $filters.actorType)
    }

    if ($filters.tactics.length > 0) {
      result = result.filter(e =>
        e.tactics?.some(t => $filters.tactics.includes(t))
      )
    }

    return result
  })()

  $: totalPages = Math.ceil(filtered.length / perPage)
  $: pageEvents = filtered.slice((currentPage - 1) * perPage, currentPage * perPage)

  $: if ($filters) currentPage = 1

  function handleSearch(e) {
    filters.update(f => ({ ...f, searchText: e.target.value }))
  }
</script>

<div class="browse">
  <FacetSidebar {availableIssues} {availableTactics} {availablePapers} />

  <div class="results">
    <div class="search-bar">
      <input
        type="text"
        placeholder="Search events..."
        value={$filters.searchText}
        on:input={handleSearch}
        class="search-input"
      />
      <span class="result-count">{filtered.length.toLocaleString()} events</span>
    </div>

    <div class="event-grid">
      {#each pageEvents as event (event.id)}
        <EventCard {event} />
      {/each}
    </div>

    {#if filtered.length === 0}
      <p class="no-results">No events match your filters.</p>
    {/if}

    <Pagination {currentPage} {totalPages} on:page={e => currentPage = e.detail} />
  </div>
</div>

<style>
  .browse {
    display: flex;
    gap: 32px;
    padding-top: 24px;
  }
  .results {
    flex: 1;
    min-width: 0;
  }
  .search-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 20px;
  }
  .search-input {
    flex: 1;
    padding: 10px 16px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.95rem;
    background: white;
  }
  .search-input:focus {
    outline: none;
    border-color: #1a1a1a;
  }
  .result-count {
    font-size: 0.85rem;
    color: #888;
    white-space: nowrap;
    font-weight: 500;
  }
  .event-grid {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .no-results {
    text-align: center;
    color: #888;
    padding: 48px 0;
  }

  @media (max-width: 768px) {
    .browse { flex-direction: column; }
  }
</style>
