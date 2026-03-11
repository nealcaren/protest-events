<script>
  import { onMount } from 'svelte'
  import { loadOrgs } from '../lib/api.js'
  import Badge from '../components/Badge.svelte'

  let organizations = []
  let sortBy = 'event_count'
  let sortAsc = false
  let searchText = ''
  let minEvents = 2

  onMount(async () => {
    organizations = await loadOrgs()
  })

  $: filtered = organizations
    .filter(o => {
      if (o.event_count < minEvents) return false
      if (searchText && !o.name.toLowerCase().includes(searchText.toLowerCase())) return false
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

<div class="org-list-page">
  <div class="page-header">
    <h1>Organizations</h1>
    <p class="subtitle">{organizations.length.toLocaleString()} organizations mentioned across protest events</p>
    <div class="header-actions">
      <a href="#/orgs/network" class="btn-network">View Network Map</a>
    </div>
  </div>

  <div class="controls">
    <input type="text" placeholder="Search organizations..." bind:value={searchText} class="search" />
    <select bind:value={minEvents}>
      <option value={1}>All orgs</option>
      <option value={2}>2+ events</option>
      <option value={5}>5+ events</option>
      <option value={10}>10+ events</option>
    </select>
    <span class="count">{filtered.length} shown</span>
  </div>

  <table>
    <thead>
      <tr>
        <th on:click={() => sort('name')} class="sortable">Organization</th>
        <th on:click={() => sort('event_count')} class="sortable num">Events</th>
        <th on:click={() => sort('issue_primary')} class="sortable">Top Issue</th>
        <th on:click={() => sort('date_start')} class="sortable">Date Range</th>
        <th class="num">Papers</th>
      </tr>
    </thead>
    <tbody>
      {#each filtered as org (org.id)}
        <tr>
          <td>
            <a href="#/orgs/{org.id}" class="name-link">{org.name}</a>
          </td>
          <td class="num">{org.event_count}</td>
          <td><Badge type="issue" value={org.issue_primary} /></td>
          <td class="dates">{org.date_start?.slice(0,4) || '?'} &mdash; {org.date_end?.slice(0,4) || '?'}</td>
          <td class="num">{org.newspapers?.length || 0}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .org-list-page { padding-top: 24px; }
  .page-header { margin-bottom: 24px; }
  h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 4px; }
  .subtitle { color: #888; margin-bottom: 12px; }
  .header-actions { margin-top: 8px; }
  .btn-network {
    display: inline-block;
    padding: 8px 18px;
    background: #1a1a1a;
    color: white;
    border-radius: 6px;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.85rem;
  }
  .btn-network:hover { background: #333; }
  .controls {
    display: flex; gap: 12px; margin-bottom: 20px; align-items: center;
  }
  .search {
    flex: 1; padding: 8px 12px; border: 1px solid #ddd;
    border-radius: 6px; font-size: 0.9rem;
  }
  select {
    padding: 8px 12px; border: 1px solid #ddd;
    border-radius: 6px; font-size: 0.85rem; background: white;
  }
  .count { font-size: 0.85rem; color: #888; white-space: nowrap; }
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
  .dates { font-size: 0.8rem; color: #888; white-space: nowrap; }
</style>
