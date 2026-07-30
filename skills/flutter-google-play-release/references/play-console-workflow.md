# Play Console workflow and failure shields

The Console changes frequently. Use semantic labels and the current visible
page; do not hard-code coordinates or assume an old menu path.

## App creation

1. Search the developer account for an existing app/package.
2. Confirm default locale, title, app/game type, and free/paid state.
3. Review the declarations shown on the creation page.
4. Create only after unresolved irreversible decisions are confirmed.
5. Record the resulting Play app ID and verify the expected record is open.

## Store listing

- Complete the default listing before localized listings.
- Verify field-length feedback shown by the current form.
- Save and re-read the summary/preview.
- Use complete HTTPS URLs. Confirm the field did not normalize to an unintended
  HTTP URL.
- Wait for media processing. A visible filename is not proof of a successful
  processed upload.
- Track each screenshot group separately. If Play reports too many images,
  inspect for duplicates or files uploaded into the wrong group.

## App content

Complete every currently required card. Common cards include:

- privacy policy;
- app access;
- ads;
- advertising ID;
- target audience and content;
- content rating;
- Data safety;
- government, finance, health, and news-related declarations.

The list is illustrative. Treat the live Console as authoritative.

### Advertising ID

Inspect the final merged manifest for:

```text
com.google.android.gms.permission.AD_ID
```

Also inspect SDK dependencies. If neither the app nor its SDKs use advertising
ID, declare “No.” If Play reports “Advertising ID declaration incomplete,”
complete this card before review.

### Data safety

Do not copy answers from another app. Reconcile the final AAB/dependencies with
the privacy policy and form summary. Revisit the form after any SDK change.

### Target audience

Selecting under-13 age groups can activate Families policy requirements.
Separate content rating from intended audience; an “Everyone” rating does not
automatically mean the developer targets children.

### IARC

Obtain explicit user authorization before accepting IARC terms. Answer the
questionnaire from the content inventory, including mild fantasy/cartoon
violence. Save the resulting regional ratings and compare them with the listing
copy and target-audience declaration.

## AAB upload

Wait for upload and Play optimization to complete before filling or saving
dependent fields.

When browser automation exposes no `setInputFiles` on the input locator:

```javascript
const chooserPromise = tab.playwright.waitForEvent('filechooser');
await tab.playwright.getByRole('button', {name: 'Upload'}).click();
const chooser = await chooserPromise;
await chooser.setFiles('/absolute/path/app-release.aab');
```

Use the current localized button label. Never upload by guessing a hidden input
index when a file chooser event is available.

## Release notes

For multiple locales, Play accepts locale blocks. Use multiline blocks:

```text
<en-US>
Improved compatibility and performance.
</en-US>
<zh-CN>
改进兼容性和性能。
</zh-CN>
```

Adjacent single-line tags can be rejected with an error such as “duplicate
start tag.” Validate the form reports the expected number of languages.

## Save, preview, and publish

1. Save the release draft.
2. Open preview and confirm:
   - version code/name;
   - min/target SDK;
   - install/update size;
   - device-support gains/losses;
   - release-note locales;
   - track, rollout percentage, and countries.
3. Save into Publishing overview.
4. Wait for automatic checks and inspect every problem.
5. Stop before the review/publication button and present the final summary.

“Ready to publish” or “Can be published” means the artifact is eligible; it
does not mean review submission or rollout has occurred.

## Browser-state recovery

- If a single-page navigation changes the URL but leaves stale content, reload
  the resulting URL and wait for the page to finish.
- If DOM snapshot support fails, use read-only visible text/control inspection
  or screenshots.
- If the page says an account cannot publish, report that account-level blocker;
  do not keep modifying the release as though upload alone will solve it.
- Preserve the authenticated tab for handoff when final confirmation is still
  pending.
