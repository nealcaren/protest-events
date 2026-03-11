<script>
  import { makeViewerUrl, formatPaperName } from '../lib/utils.js'

  export let source
</script>

<div class="source-block">
  <div class="source-header">
    <a href={makeViewerUrl(source.paper, source.date, source.page, source.chunk_idx)}
       target="_blank" rel="noopener" class="source-link">
      {formatPaperName(source.paper)}
    </a>
    <span class="source-meta">
      {source.date} &middot; p. {source.page}
      {#if source.role === 'duplicate'}
        <span class="role-badge">additional coverage</span>
      {/if}
    </span>
  </div>
  {#if source.source_text}
    <blockquote class="ocr-text">{source.source_text}</blockquote>
  {/if}
</div>

<style>
  .source-block {
    border-left: 3px solid #ddd;
    padding-left: 16px;
    margin-bottom: 20px;
  }
  .source-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }
  .source-link {
    font-weight: 700;
    color: #1a1a1a;
    text-decoration: none;
    font-size: 0.95rem;
  }
  .source-link:hover {
    text-decoration: underline;
  }
  .source-meta {
    font-size: 0.8rem;
    color: #888;
  }
  .role-badge {
    background: #f0f0f0;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 0.7rem;
    color: #666;
    margin-left: 4px;
  }
  .ocr-text {
    margin: 0;
    padding: 12px 16px;
    background: #f8f8f6;
    border-radius: 4px;
    font-size: 0.85rem;
    line-height: 1.7;
    color: #333;
    font-family: 'Georgia', serif;
    white-space: pre-wrap;
  }
</style>
