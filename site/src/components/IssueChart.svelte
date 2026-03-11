<script>
  import { ISSUE_LABELS, ISSUE_COLORS } from '../lib/utils.js'

  export let issueCounts = {}

  $: sorted = Object.entries(issueCounts)
    .sort((a, b) => b[1] - a[1])
  $: maxCount = sorted.length > 0 ? sorted[0][1] : 1
</script>

<div class="chart">
  {#each sorted as [code, count]}
    <div class="bar-row">
      <span class="bar-label">{ISSUE_LABELS[code] || code}</span>
      <div class="bar-track">
        <div
          class="bar-fill"
          style="width: {(count / maxCount) * 100}%; background: {ISSUE_COLORS[code] || '#666'}"
        ></div>
      </div>
      <span class="bar-count">{count.toLocaleString()}</span>
    </div>
  {/each}
</div>

<style>
  .chart {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .bar-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .bar-label {
    font-size: 0.8rem;
    font-weight: 500;
    width: 140px;
    text-align: right;
    flex-shrink: 0;
    color: #555;
  }
  .bar-track {
    flex: 1;
    height: 20px;
    background: #f0f0f0;
    border-radius: 3px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
  }
  .bar-count {
    font-size: 0.8rem;
    font-weight: 600;
    width: 48px;
    color: #666;
    font-variant-numeric: tabular-nums;
  }
</style>
