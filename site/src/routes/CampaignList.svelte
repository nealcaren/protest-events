<script>
  import { onMount } from 'svelte'
  import { loadCampaigns } from '../lib/api.js'
  import Badge from '../components/Badge.svelte'

  let campaigns = []
  let sortBy = 'event_count'
  let sortAsc = false
  let filterNamed = ''
  let searchText = ''

  onMount(async () => {
    campaigns = await loadCampaigns()
  })

  $: filtered = campaigns
    .filter(c => {
      if (filterNamed === 'named' && !c.named) return false
      if (filterNamed === 'algorithmic' && c.named) return false
      if (searchText && !c.name.toLowerCase().includes(searchText.toLowerCase())) return false
      return true
    })
    .sort((a, b) => {
      let va = a[sortBy], vb = b[sortBy]
      if (typeof va === 'string') { va = va || ''; vb = vb || '' }
      if (sortAsc) return va > vb ? 1 : -1
      return va < vb ? 1 : -1
    })

  function sort(col) {
    if (sortBy === col) sortAsc = !sortAsc
    else { sortBy = col; sortAsc = false }
  }
</script>

<div class="campaign-list-page">
  <h1>Campaigns</h1>
  <p class="subtitle">{campaigns.length} campaigns grouping related protest events</p>

  <div class="controls">
    <input type="text" placeholder="Search campaigns..." bind:value={searchText} class="search" />
    <select bind:value={filterNamed}>
      <option value="">All campaigns</option>
      <option value="named">Named only</option>
      <option value="algorithmic">Algorithmic only</option>
    </select>
  </div>

  <table>
    <thead>
      <tr>
        <th on:click={() => sort('name')} class="sortable">Campaign</th>
        <th on:click={() => sort('event_count')} class="sortable num">Events</th>
        <th on:click={() => sort('issue_primary')} class="sortable">Issue</th>
        <th on:click={() => sort('date_start')} class="sortable">Date Range</th>
      </tr>
    </thead>
    <tbody>
      {#each filtered as c (c.id)}
        <tr>
          <td>
            <a href="#/campaigns/{c.id}"  class="name-link">{c.name}</a>
            {#if !c.named}<span class="algo-tag">auto</span>{/if}
          </td>
          <td class="num">{c.event_count}</td>
          <td><Badge type="issue" value={c.issue_primary} /></td>
          <td class="dates">{c.date_start || '?'} &mdash; {c.date_end || '?'}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .campaign-list-page { padding-top: 24px; }
  h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 4px; }
  .subtitle { color: #888; margin-bottom: 24px; }
  .controls {
    display: flex; gap: 12px; margin-bottom: 20px;
  }
  .search {
    flex: 1; padding: 8px 12px; border: 1px solid #ddd;
    border-radius: 6px; font-size: 0.9rem;
  }
  select {
    padding: 8px 12px; border: 1px solid #ddd;
    border-radius: 6px; font-size: 0.85rem; background: white;
  }
  table { width: 100%; border-collapse: collapse; background: white;
    border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  th {
    text-align: left; padding: 10px 14px; font-size: 0.8rem;
    text-transform: uppercase; letter-spacing: 0.04em; color: #888;
    border-bottom: 2px solid #eee; font-weight: 600;
  }
  th.sortable { cursor: pointer; }
  th.sortable:hover { color: #1a1a1a; }
  td { padding: 10px 14px; border-bottom: 1px solid #f0f0f0; font-size: 0.9rem; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .name-link { color: #1a1a1a; font-weight: 600; text-decoration: none; }
  .name-link:hover { text-decoration: underline; }
  .algo-tag {
    font-size: 0.65rem; background: #f0f0f0; padding: 1px 5px;
    border-radius: 3px; color: #888; margin-left: 6px;
  }
  .dates { font-size: 0.8rem; color: #888; white-space: nowrap; }
</style>
