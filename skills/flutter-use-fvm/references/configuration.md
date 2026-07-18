# Installation and configuration

Use this reference for machine setup, project pinning, cache behavior, and configuration keys.

## Installation

Prefer the standalone FVM executable to avoid Dart package dependency conflicts.

### macOS and Linux

```bash
curl -fsSL https://fvm.app/install.sh | bash
curl -fsSL https://fvm.app/install.sh | bash -s -- <fvm-version>
```

The script supports macOS x64/arm64 and Linux x64/arm64/riscv64 and requires `curl` plus `tar`. Set `FVM_INSTALL_DIR=<absolute-path-under-home>` for a custom location. It also supports `./install.sh --help`, `./install.sh --version`, and `--uninstall`.

Homebrew on macOS:

```bash
brew install fvm
```

### Windows

Use the standalone release/PowerShell path or Chocolatey on Windows x64:

```powershell
choco install fvm
```

### Pub package alternative

```bash
dart pub global activate fvm
```

Do not prefer the Pub installation when FVM will manage the machine's global Flutter SDK. It depends on the currently installed Dart SDK being compatible with the selected FVM release.

### PATH

- Install script on Bash/Zsh: prepend `<install-dir>/bin` to `PATH`; the documented default install directory is `$HOME/fvm`.
- Fish: use `fish_add_path "<install-dir>/bin"`.
- Pub on macOS/Linux: append `$HOME/.pub-cache/bin`.
- Pub on Windows: add `%USERPROFILE%\AppData\Local\Pub\Cache\bin`.

Verify with `fvm --version`. Do not fall back to bare Flutter/Dart when this verification fails.

## Project configuration: `.fvmrc`

Create or update `.fvmrc` with `fvm use <version>` instead of hand-editing it for routine version changes. Commit the file.

Documented keys:

| Key | Meaning |
| --- | --- |
| `flutter` | Default Flutter version, channel, commit, or fork selector |
| `flavors` | Map of flavor names to SDK selectors |
| `cachePath` | Project-specific SDK cache path |
| `useGitCache` | Enable Git caching; defaults to `true` |
| `gitCachePath` | Git cache directory when Git caching is enabled |
| `flutterUrl` | Flutter SDK Git repository URL |
| `privilegedAccess` | Allow operations requiring elevated/link privileges; defaults to `true` |
| `updateVscodeSettings` | Let FVM update VS Code settings; defaults to `true` |
| `updateGitIgnore` | Let FVM update `.gitignore`; defaults to `true` |
| `updateMelosSettings` | Let FVM update Melos configuration; defaults to `true` |
| `runPubGetOnSdkChanges` | Run package resolution after SDK changes; defaults to `true` |

Example:

```json
{
  "flutter": "3.19.0",
  "flavors": {
    "development": "beta",
    "production": "3.19.0"
  },
  "updateVscodeSettings": true,
  "updateGitIgnore": true,
  "updateMelosSettings": true,
  "runPubGetOnSdkChanges": true
}
```

## Generated `.fvm/` directory

FVM can create:

- `.fvm/flutter_sdk`: symlink to the selected cached SDK
- `.fvm/fvm_config.json`: deprecated compatibility config
- `.fvm/release`: internal selected release marker
- `.fvm/version`: internal FVM/config version marker
- `.fvm/versions/<selector>`: version-specific links used by some integrations

For FVM 3+, ignore the generated `.fvm/` directory by default and commit `.fvmrc`. Let `fvm use` recreate missing links. Do not hand-edit internal marker files.

## Environment variables

Apply machine or CI-wide settings with:

- `FVM_CACHE_PATH`: SDK cache directory
- `FVM_USE_GIT_CACHE`: `true` or `false`
- `FVM_GIT_CACHE_PATH`: local Git reference cache
- `FVM_FLUTTER_URL`: Flutter repository URL

Legacy/deprecated names:

- `FVM_HOME`: legacy fallback; use `FVM_CACHE_PATH`
- `FVM_GIT_CACHE`: removed/deprecated; use `FVM_FLUTTER_URL` for the repository URL

Environment variables are useful for isolated CI or offline/shared caches. Prefer project `.fvmrc` for settings that must travel with the repository.

## Global configuration

Use `fvm config` for cache, Git repository, and update-check settings. Use `fvm global <version>` only when a machine-wide default is intentionally required. FVM prints the global SDK `bin` path if it is not already on `PATH`.

Keep repository automation on `fvm flutter` and `fvm dart` even after setting a global link; visible routing prevents local shell configuration from becoming an undocumented dependency.

## Uninstallation

```bash
curl -fsSL https://fvm.app/install.sh | bash -s -- --uninstall
brew uninstall fvm
choco uninstall fvm
dart pub global deactivate fvm
```

`fvm destroy` additionally removes all cached Flutter SDKs. Run it only when the user explicitly wants cache deletion.
