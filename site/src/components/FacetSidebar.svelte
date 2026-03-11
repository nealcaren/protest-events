<script>
  import { ISSUE_LABELS, ISSUE_COLORS } from '../lib/utils.js'
  import { filters, resetFilters } from '../lib/stores.js'

  export let availableIssues = []
  export let availableTactics = []
  export let availablePapers = []

  function toggleIssue(code) {
    filters.update(f => ({
      ...f,
      issues: f.issues.includes(code)
        ? f.issues.filter(i => i !== code)
        : [...f.issues, code]
    }))
  }

  function toggleTactic(t) {
    filters.update(f => ({
      ...f,
      tactics: f.tactics.includes(t)
        ? f.tactics.filter(x => x !== t)
        : [...f.tactics, t]
    }))
  }

  function setPaper(e) {
    filters.update(f => ({
      ...f,
      papers: e.target.value ? [e.target.value] : []
    }))
  }

  function setActorType(e) {
    filters.update(f => ({ ...f, actorType: e.target.value }))
  }

  $: hasFilters = $filters.issues.length > 0 ||
    $filters.papers.length > 0 ||
    $filters.tactics.length > 0 ||
    $filters.actorType !== '' ||
    $filters.searchText !== ''
</script>

<aside class="sidebar">
  {#if hasFilters}
    <button class="clear-btn" on:click={resetFilters}>Clear all filters</button>
  {/if}

  <div class="facet-group">
    <h3>Issue</h3>
    {#each availableIssues as code}
      <label class="checkbox-label">
        <input
          type="checkbox"
          checked={$filters.issues.includes(code)}
          on:change={() => toggleIssue(code)}
        />
        <span class="color-dot" style="background: {ISSUE_COLORS[code] || '#666'}"></span>
        {ISSUE_LABELS[code] || code}
      </label>
    {/each}
  </div>

  <div class="facet-group">
    <h3>Newspaper</h3>
    <select on:change={setPaper} value={$filters.papers[0] || ''}>
      <option value="">All newspapers</option>
      {#each availablePapers as p}
        <option value={p.slug}>{p.name}</option>
      {/each}
    </select>
  </div>

  <div class="facet-group">
    <h3>Actor Type</h3>
    <select on:change={setActorType} value={$filters.actorType}>
      <option value="">All</option>
      <option value="black_protest">Black protest</option>
      <option value="anti_black">Anti-Black</option>
      <option value="mixed">Mixed</option>
    </select>
  </div>

  <div class="facet-group">
    <h3>Tactics</h3>
    {#each availableTactics.slice(0, 10) as t}
      <label class="checkbox-label">
        <input
          type="checkbox"
          checked={$filters.tactics.includes(t)}
          on:change={() => toggleTactic(t)}
        />
        {t.replace(/_/g, ' ')}
      </label>
    {/each}
  </div>
</aside>

<style>
  .sidebar {
    width: 240px;
    flex-shrink: 0;
  }
  .facet-group {
    margin-bottom: 24px;
  }
  h3 {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #888;
    margin-bottom: 8px;
    font-weight: 600;
  }
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.85rem;
    padding: 3px 0;
    cursor: pointer;
  }
  .color-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  select {
    width: 100%;
    padding: 6px 8px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 0.85rem;
    background: white;
  }
  .clear-btn {
    width: 100%;
    padding: 8px;
    background: none;
    border: 1px solid #ddd;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    color: #888;
    margin-bottom: 16px;
  }
  .clear-btn:hover {
    background: #f5f5f5;
    color: #1a1a1a;
  }
</style>
