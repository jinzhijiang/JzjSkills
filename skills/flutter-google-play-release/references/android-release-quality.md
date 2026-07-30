# Android release quality

Use this reference for target SDK, edge-to-edge, large-screen/orientation, R8,
AGP, and device-compatibility findings. Verify current requirements against the
installed Flutter SDK, Android tooling, and live Play Console.

## Target and compile SDK

Do not infer compliance only from Gradle source. Verify:

1. the pinned Flutter SDK/toolchain;
2. `compileSdk` and `targetSdk` configuration;
3. the final release merged/packaged manifest;
4. Play's parsed target SDK after upload.

If a fixed target is part of the release contract, set it explicitly:

```kotlin
android {
    compileSdk = 36
    defaultConfig {
        targetSdk = 36
    }
}
```

Replace `36` with the current required/approved value. A future Flutter version
may change its default, so explicit release contracts prevent silent drift.

## Edge-to-edge

For target SDKs where Android enforces edge-to-edge, verify the app:

- draws with `WindowCompat.setDecorFitsSystemWindows(window, false)` or the
  framework-equivalent behavior;
- handles system-bar and display-cutout insets;
- tests cold start and runtime UI, not only the first Flutter frame;
- remains usable with gesture and three-button navigation.

Immersive games may intentionally hide system bars, but they still need
cutout/inset-safe controls and HUD content.

## Orientation and large screens

A fixed manifest `android:screenOrientation` can trigger Play large-screen
recommendations. Before removing it:

1. inspect runtime `SystemChrome.setPreferredOrientations`;
2. verify phone behavior remains intentional;
3. verify large-screen/Android 16 behavior where the platform may ignore
   orientation restrictions;
4. run real device/emulator checks in relevant aspect ratios.

Do not remove a restriction blindly if portrait layouts are unusable. Treat the
recommendation as a product/layout change, then validate device-support deltas
after upload.

## R8 and resource shrinking

Typical Kotlin DSL release configuration:

```kotlin
buildTypes {
    release {
        isMinifyEnabled = true
        isShrinkResources = true
    }
}
```

For supported pre-AGP-9 toolchains, optimized resource shrinking may require:

```properties
android.r8.optimizedResourceShrinking=true
```

Verify the build produces non-empty outputs such as:

```text
build/app/outputs/mapping/release/mapping.txt
build/app/outputs/mapping/release/resources.txt
build/app/outputs/mapping/release/usage.txt
```

Then run tests and smoke-test the minified release. Plugin reflection or native
registration can require keep rules.

## AGP/Gradle/Kotlin compatibility

Play may recommend an AGP version newer than the pinned Flutter SDK officially
supports. Do not force-upgrade one component solely to remove a recommendation.

Inspect the installed Flutter tool's template and compatibility checks, then
upgrade Flutter, AGP, Gradle, Kotlin, and plugins deliberately as one validated
toolchain change. Record future-migration warnings separately from release
blockers.

## Device-support delta

On the release preview, inspect device losses and gains by device class. A
target SDK or manifest change that unexpectedly removes devices is a blocker
until explained. Zero device losses plus expected gains is evidence, not a
guarantee of runtime layout correctness.

## Validation matrix

| Check | Evidence | Failure action |
|---|---|---|
| Package/version | merged manifest + Play table | stop upload/release |
| target SDK | merged manifest + Play table | rebuild |
| Permissions/AD_ID | merged manifest + SDK audit | reconcile declarations |
| Fixed orientation | merged manifest + runtime policy | validate or redesign |
| Edge-to-edge | native/Flutter code + visual test | fix insets/UI |
| R8 | build config + outputs + release smoke test | add config/keep rules |
| Toolchain | Flutter compatibility matrix + build | avoid unsupported upgrade |
| Device support | Play preview delta | investigate any unexplained loss |
