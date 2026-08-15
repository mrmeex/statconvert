---
hide:
  - navigation
  - toc
---

<section class="statconvert-hero" markdown="1">
  <p class="statconvert-eyebrow">Statistical data, made portable</p>
  <h1>StatConvert</h1>
  <p class="statconvert-lede">
    StatConvert is a command-line tool and optional local browser interface for
    inspecting, validating, transforming, and converting statistical datasets between
    formats such as SPSS, Stata, SAS, R, Excel, CSV, Parquet, and more.
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
statconvert convert records.csv records.jsonl --stream --chunk-size 50000
statconvert validate survey.sav
statconvert schema survey.sav --export-contract schema.toml
statconvert validate survey.sav --schema-contract schema.toml
statconvert validate records.csv --schema-contract schema.toml --stream
statconvert transform input.csv output.csv --derive "email_clean=lower(strip(email))"
statconvert transform input.csv output.csv --derive "joined=concat(code, '-', year(parse_date(date_text, '%Y-%m-%d')))"
statconvert transform input.csv output.csv --filter-expression "is_email(email) and between(age, 18, 65)"
statconvert ui
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
  <article>
    <h2>Stream line-oriented data</h2>
    <p>Opt into chunked CSV, JSONL, and NDJSON conversion, batch, and contract-validation workflows.</p>
  </article>
  <article>
    <h2>Build safe transform recipes</h2>
    <p>Derive, filter, normalize, and recode data with ordered TOML steps and a closed expression language.</p>
  </article>
  <article>
    <h2>Work in a local browser</h2>
    <p>Install the optional UI extra and use the same workflows locally with no accounts, cloud processing, or telemetry.</p>
  </article>
</section>

<p>
  StatConvert 1.4.1 stabilizes the 1.4.0 transfer-policy workflow by deeply freezing
  nested transfer-plan data while keeping exported data independent and JSON-ready.
  It adds no features, policies, formats, ORC or database support, or runtime
  dependencies. Version 1.4.0 added complete target-aware transfer planning, five
  explicit policies, exact opt-in smallest-type application, policy-aware reports, and
  matching browser controls. Plans scan the full selected dataset and write nothing.
  Omitting a policy keeps the established conversion path unchanged; batch, streaming,
  saved-plan, default/global-policy, and legacy-emulation support remain outside this
  release.
</p>

<footer class="statconvert-home-footer">
  <span>StatConvert documentation</span>
  <a href="examples/">Examples</a>
  <a href="cli/">CLI reference</a>
  <a href="formats/">Formats</a>
  <a href="ui/">Browser UI</a>
  <a href="license/">License</a>
  <a href="https://github.com/mrmeex/statconvert/releases/latest">Latest release</a>
  <a href="https://github.com/mrmeex/statconvert">Source on GitHub</a>
</footer>
