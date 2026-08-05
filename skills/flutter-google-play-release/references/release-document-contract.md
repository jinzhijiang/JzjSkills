# Release document contract

Use canonical repository files so store copy is reviewed with the code and
available before Play Console work begins.

## Store description

Preferred path:

```text
docs/store/google-play-description.md
```

For every active locale, keep:

```markdown
## <locale>

### App title
...

### Short description
...

### Full description
...
```

Record verified character counts for limited fields. State the version or date
whose shipped behavior the copy describes. Include only claims supported by
the current source and release artifact, especially for login, offline use,
ads, analytics, crash reporting, data storage, and privacy.

## Release notes

Preferred path:

```text
docs/store/google-play-release-notes.md
```

Append versions instead of replacing history:

```markdown
## <versionName> (<versionCode>)

### en-US
...

### zh-CN
...
```

Include every active store locale. Keep the notes user-facing and scoped to
shipped changes; do not expose implementation-only details or make unsupported
security claims.

## Required order

1. Inspect implemented changes and privacy/data-flow deltas.
2. Update both canonical documents.
3. Validate field lengths, locales, and claims.
4. Build and verify the AAB.
5. Copy the canonical content into Play Console.
6. Save and audit the Publishing overview.
7. Leave the final submission click to the user.
8. After the user submits, commit the scoped changes and tag the exact build.

The release tag identifies a submitted artifact, not an approval outcome.
Rejected replacement builds must increment versionCode and receive a new tag.
