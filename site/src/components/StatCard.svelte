<script>
  export let label = ''
  export let value = 0
  export let format = 'number'

  $: display = format === 'number' ? value.toLocaleString() : value
</script>

<div class="stat-card">
  <div class="value">{display}</div>
  <div class="label">{label}</div>
</div>

<style>
  .stat-card {
    background: white;
    border-radius: 8px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  .value {
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1;
    color: #1a1a1a;
  }
  .label {
    font-size: 0.85rem;
    color: #888;
    margin-top: 6px;
    font-weight: 500;
  }
</style>
