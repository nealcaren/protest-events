<script>
  import { onMount } from 'svelte'
  import { loadMeta, loadCampaigns } from '../lib/api.js'
  import StatCard from '../components/StatCard.svelte'
  import IssueChart from '../components/IssueChart.svelte'

  let meta = null
  let topCampaigns = []

  onMount(async () => {
    meta = await loadMeta()
    const campaigns = await loadCampaigns()
    topCampaigns = campaigns
      .filter(c => c.named)
      .sort((a, b) => b.event_count - a.event_count)
      .slice(0, 15)
  })
</script>

<div class="dashboard">
  <section class="hero">
    <h1>Protest Events in the African American Press</h1>
    <p class="subtitle">1905&ndash;1929 &middot; Extracted from OCR text of 37 newspapers via semantic search and LLM classification</p>
    <div class="hero-actions">
      <a href="#/events"  class="btn btn-primary">Browse Events</a>
      <a href="#/campaigns"  class="btn btn-secondary">View Campaigns</a>
    </div>
  </section>

  {#if meta}
    <section class="stats">
      <StatCard label="Protest Events" value={meta.total_events} />
      <StatCard label="Campaigns" value={meta.total_campaigns} />
      <StatCard label="Newspapers" value={meta.total_newspapers} />
      <StatCard label="Date Range" value="{meta.date_range[0]?.slice(0,4)}–{meta.date_range[1]?.slice(0,4)}" format="text" />
    </section>

    <section class="two-col">
      <div>
        <h2>Events by Issue</h2>
        <IssueChart issueCounts={meta.issue_counts} />
      </div>

      <div>
        <h2>Top Campaigns</h2>
        <div class="campaign-list">
          {#each topCampaigns as c}
            <a href="#/campaigns/{c.id}"  class="campaign-row">
              <span class="campaign-name">{c.name}</span>
              <span class="campaign-count">{c.event_count} events</span>
            </a>
          {/each}
        </div>
      </div>
    </section>
  {:else}
    <p>Loading...</p>
  {/if}
</div>

<style>
  .dashboard {
    padding-top: 24px;
  }
  .hero {
    text-align: center;
    padding: 48px 0 40px;
  }
  h1 {
    font-size: 2.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.1;
    margin-bottom: 12px;
  }
  .subtitle {
    color: #666;
    font-size: 1rem;
    margin-bottom: 24px;
  }
  .hero-actions {
    display: flex;
    gap: 12px;
    justify-content: center;
  }
  .btn {
    padding: 10px 24px;
    border-radius: 6px;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
  }
  .btn-primary {
    background: #1a1a1a;
    color: white;
  }
  .btn-primary:hover { background: #333; }
  .btn-secondary {
    background: #f0f0f0;
    color: #1a1a1a;
  }
  .btn-secondary:hover { background: #e5e5e5; }

  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 48px;
  }

  .two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 48px;
  }
  h2 {
    font-size: 1.2rem;
    font-weight: 700;
    margin-bottom: 20px;
  }
  .campaign-list {
    display: flex;
    flex-direction: column;
  }
  .campaign-row {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid #eee;
    text-decoration: none;
    color: inherit;
  }
  .campaign-row:hover { background: #fafafa; }
  .campaign-name {
    font-weight: 500;
    font-size: 0.9rem;
  }
  .campaign-count {
    color: #888;
    font-size: 0.8rem;
    font-variant-numeric: tabular-nums;
  }

  @media (max-width: 768px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
    .two-col { grid-template-columns: 1fr; }
    h1 { font-size: 1.8rem; }
  }
</style>
