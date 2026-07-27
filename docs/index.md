---
hide:
  - navigation
  - toc
---

<section class="statconvert-hero" markdown="1">
  <p class="statconvert-eyebrow">Statistical data, made portable</p>
  <h1>StatConvert</h1>
  <p class="statconvert-lede">
    StatConvert is a command-line tool for inspecting, validating, transforming, and
    converting statistical datasets between formats such as SPSS, Stata, SAS, R,
    Excel, CSV, Parquet, and more.
  </p>
  <div class="statconvert-actions">
    <a class="md-button md-button--primary" href="https://github.com/mrmeex/statconvert/releases/latest">Download latest release</a>
    <a class="md-button" href="user-guide/">Read the docs</a>
    <a class="md-button" href="https://github.com/mrmeex/statconvert">View on GitHub</a>
  </div>
</section>

<section class="statconvert-command" markdown="1">
  <p class="statconvert-section-label">A clear, inspect-first workflow</p>

```powershell title="Inspect, convert, and validate"
statconvert info survey.sav
statconvert convert survey.sav survey.parquet
statconvert validate survey.sav
statconvert schema survey.sav --export-contract schema.toml
statconvert validate survey.sav --schema-contract schema.toml
```
</section>

<section class="statconvert-features" aria-label="StatConvert features">
  <article>
    <h2>Convert between formats</h2>
    <p>Move datasets between statistical, spreadsheet, text, R, and Arrow formats.</p>
  </article>
  <article>
    <h2>Preserve useful metadata</h2>
    <p>Carry supported labels, missing-value definitions, and metadata into suitable destinations or sidecars.</p>
  </article>
  <article>
    <h2>Inspect before converting</h2>
    <p>Check dimensions, types, sample rows, capabilities, and target constraints before writing output.</p>
  </article>
  <article>
    <h2>Define data-quality contracts</h2>
    <p>Export versioned TOML schema contracts and apply named rules in validation or reports.</p>
  </article>
</section>

<footer class="statconvert-home-footer">
  <span>StatConvert documentation</span>
  <a href="https://github.com/mrmeex/statconvert/releases/latest">Latest release</a>
  <a href="https://github.com/mrmeex/statconvert">Source on GitHub</a>
</footer>
