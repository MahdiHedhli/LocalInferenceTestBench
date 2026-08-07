# CLI contract: Guided benchmark failure reporting

## Arguments

`litb run` adds:

```text
--failure-report {ask,none}
```

- `ask` is the default. It offers an issue draft only for an eligible failure on an interactive
  stdin/stdout terminal.
- `none` disables failure reporting.
- `litb check`, `prepare-submission`, and `publish-submission` do not accept this option.

There is no supported non-interactive open/submit flag. Ordinary non-TTY runs cannot trigger the
handoff.

## Output and prompt

For an eligible interactive failure, stdout contains:

1. a fixed explanation that this is an execution compatibility signal, not a model score;
2. the complete, sorted failure draft JSON;
3. a fixed exclusion list;
4. a disclosure that opening the composer transmits the draft to GitHub and can enter browser or
   network history, while GitHub Submit is separate;
5. `Open this sanitized draft in GitHub? [y/N]`.

Only one ASCII `y` or `Y`, after trimming surrounding ASCII whitespace, opens a browser. Enter, EOF,
Ctrl-C while the optional prompt is active, words such as `yes`, Unicode lookalikes, and any other
value decline.

## Exit status

The pre-existing benchmark/configuration/submission/publication status remains authoritative.
Successful, false, or exceptional browser handoff never changes it. The optional path may print only
a fixed categorical handoff message and never exception text.

## Network and mutation boundary

Before exact consent, this feature performs no browser or GitHub request. It may best-effort read the
existing local public descriptor. After consent it calls the standard-library browser helper once
with the fixed `https://github.com/MahdiHedhli/LITB/issues/new` origin/path and
`title`/`body` query. That navigation transmits the draft but does not create an issue. The user must
click GitHub Submit for public mutation.
