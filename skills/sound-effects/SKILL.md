---
name: sound-effects
description: "Generate custom sound effects using each::sense AI. Create realistic and stylized audio for any scenario including impacts, ambiences, foley, UI sounds, nature, mechanical effects, and transitions. Powered by stable-audio-2-5 for precise audio generation. Use for: video production, game development, podcasts, apps, UI/UX, presentations, film. Triggers: sound effect, sfx, audio effect, foley, generate sound, ambient sound, ui sound, impact sound, whoosh, explosion, nature sound, notification sound, create audio"
allowed-tools: Bash(curl *), Bash(python3 *), Bash(ffmpeg *), Bash(ffprobe *), WebFetch
---

# Sound Effects

Generate custom sound effects for any use case using [each::sense](https://docs.eachlabs.ai/sense/overview) — the intelligent AI agent that automatically selects the best model for your request.

> ## ⚠️ Read this first — the each::sense endpoint may return 402 even with credits
>
> **Observed 2026-08-13**: with a funded workspace ($10 balance, single API key in that
> same workspace), every call to `eachsense-agent.core.eachlabs.run` returned
> **HTTP 402 `insufficient_balance`** — while the *standard* prediction API accepted the
> **same key** and billed the **same balance** fine.
>
> **This is not an auth problem.** Control experiment:
>
> | Request | Result |
> |---|---|
> | valid key → eachsense agent | **402** Insufficient balance |
> | valid key → `api.eachlabs.ai` | **200** |
> | deliberately wrong key → eachsense agent | **401** Invalid API key |
>
> A bad key gives 401, so the key authenticates; the beta agent service simply does not
> see the workspace balance. Adding credits does not help — it was already funded.
>
> **If you hit 402, don't burn time re-checking the key or waiting for propagation.**
> Jump straight to [Fallback: standard prediction API](#fallback-standard-prediction-api),
> which is verified working.

## Quick Start

> Requires an each::labs API key. Get one at [eachlabs.ai](https://eachlabs.ai).

### Using curl

```bash
curl -X POST https://eachsense-agent.core.eachlabs.run/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $EACHLABS_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Generate a sound effect: a heavy wooden door creaking open slowly in a stone castle hallway, with echo and reverb. 3 seconds long."}],
    "stream": false
  }'
```

### Using Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_EACHLABS_API_KEY",
    base_url="https://eachsense-agent.core.eachlabs.run/v1"
)

response = client.chat.completions.create(
    model="eachsense/beta",
    messages=[{"role": "user", "content": "Generate a sound effect: a heavy wooden door creaking open slowly in a stone castle hallway, with echo and reverb. 3 seconds long."}]
)

print(response.choices[0].message.content)
```

### With Reference Image

```bash
curl -X POST https://eachsense-agent.core.eachlabs.run/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $EACHLABS_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": [
              {"type": "text", "text": "Generate realistic sound effects that match this scene. Create the ambient soundscape a viewer would hear if they were standing in this location."},
              {"type": "image_url", "image_url": {"url": "https://example.com/forest-scene.jpg"}}
            ]
          }
    ],
    "stream": false
  }'
```

> Images are sent inside messages using the OpenAI multimodal content format. Maximum 4 images per request.

### Streaming

Set `"stream": true` for real-time SSE responses, or `"stream": false` for complete result in a single response. Streaming is useful for showing progress in UIs; non-streaming is simpler for scripts and automation.

## Available Models

| Model | Strengths | Best For |
|-------|-----------|----------|
| **stable-audio-2-5** | Precise audio generation, short-form content, high quality | Sound effects, foley, ambiences, UI sounds |
| **mureka-generate-music** | Musical sound design, tonal effects | Musical stingers, jingles, tonal transitions |

## Sound Effect Categories

| Category | Examples | Typical Duration |
|----------|----------|-----------------|
| **Nature** | Rain, thunder, wind, birds, ocean waves, fire crackling | 3-30 sec |
| **Impacts** | Punch, crash, explosion, slam, shatter, thud | 0.5-3 sec |
| **Mechanical** | Engine start, gear shift, hydraulic press, clock ticking | 1-10 sec |
| **UI / Digital** | Notification ping, button click, error buzz, level up chime | 0.1-2 sec |
| **Foley** | Footsteps, cloth rustle, paper crumple, pouring liquid | 1-5 sec |
| **Transitions** | Whoosh, swoosh, riser, reverse cymbal, stinger | 0.5-3 sec |
| **Sci-Fi** | Laser blast, warp drive, force field hum, alien chatter | 0.5-5 sec |
| **Horror** | Creaking floorboard, whisper, distant scream, heartbeat | 1-10 sec |
| **Cartoon** | Boing, splat, slide whistle, comedy honk | 0.5-2 sec |
| **Ambient** | Coffee shop murmur, office hum, city traffic, subway | 10-30 sec |

## Prompt Tips

### Sound Effect Prompt Formula

```
Generate a sound effect: [what it is] + [material/texture] + [environment/space] + [duration]
```

### Describing Sound Qualities

| Quality | Keywords |
|---------|----------|
| **Bright** | crisp, sharp, metallic, ringing, clear |
| **Dark** | deep, rumbling, low, muffled, thick |
| **Wet** | reverb, echo, spacious, cavernous, underwater |
| **Dry** | close-mic, tight, no reverb, intimate |
| **Distorted** | overdriven, gritty, clipped, saturated |
| **Clean** | pure, pristine, digital, polished |

### Duration Guidelines

Be specific about length:

```
"0.5 seconds" — quick hits, clicks, notifications
"1-3 seconds" — impacts, transitions, short effects
"5-10 seconds" — ambient loops, longer foley
"15-30 seconds" — environment ambiences, atmospheric beds
```

### Layering Instructions

Request multiple elements in one effect:

```
"A thunderclap with: initial crack, rolling rumble that
fades over 5 seconds, light rain in the background throughout"
```

## Examples

### Cinematic Impact

```bash
curl -X POST https://eachsense-agent.core.eachlabs.run/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $EACHLABS_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Generate a sound effect: cinematic deep bass impact hit followed by a reverb tail that decays over 3 seconds. Like a movie trailer boom. Massive sub-bass presence, felt in the chest. Dry initial hit, then spacious reverb."}],
    "stream": false
  }'
```

### UI Notification Sound

```bash
curl -X POST https://eachsense-agent.core.eachlabs.run/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $EACHLABS_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Generate a sound effect: a pleasant, subtle notification chime for a mobile app. Two ascending xylophone-like tones, bright and friendly. 0.5 seconds total. Clean and digital, not overly attention-grabbing. Think premium tech product."}],
    "stream": false
  }'
```

### Nature Ambience

```bash
curl -X POST https://eachsense-agent.core.eachlabs.run/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $EACHLABS_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Generate a sound effect: a peaceful forest ambience at dawn. Gentle birdsong from multiple species at varying distances, a soft breeze rustling through leaves, a distant stream trickling over rocks. 20 seconds long. Naturalistic and immersive."}],
    "stream": false
  }'
```

### Sci-Fi Laser

```bash
curl -X POST https://eachsense-agent.core.eachlabs.run/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $EACHLABS_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Generate a sound effect: a futuristic laser blaster firing three rapid shots. Each shot has a sharp zap with a synthesized sizzle tail. High-pitched, energetic, slightly different pitch for each shot. 1.5 seconds total. Sci-fi video game style."}],
    "stream": false
  }'
```

### Horror Atmosphere

```bash
curl -X POST https://eachsense-agent.core.eachlabs.run/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $EACHLABS_API_KEY" \
  -d '{
    "messages": [{"role": "user", "content": "Generate a sound effect: unsettling horror ambience for a haunted house scene. Low droning hum, occasional distant creaking wood, a faint whisper that passes from left to right, and a single slow heartbeat. 15 seconds. Dark, tense, and deeply unsettling."}],
    "stream": false
  }'
```

## Batch Sound Effect Generation

```bash
# Generate a complete UI sound kit
EFFECTS=(
  "Generate a sound effect: app launch whoosh, 0.3 seconds, bright and modern"
  "Generate a sound effect: button tap click, soft and tactile, 0.1 seconds"
  "Generate a sound effect: success completion chime, three ascending notes, 0.8 seconds, cheerful"
  "Generate a sound effect: error notification, two low descending tones, 0.5 seconds, gentle warning"
  "Generate a sound effect: message received ping, single bright bell tone, 0.3 seconds, pleasant"
)

for EFFECT in "${EFFECTS[@]}"; do
  curl -X POST https://eachsense-agent.core.eachlabs.run/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $EACHLABS_API_KEY" \
    -d "{
      \"messages\": [{\"role\": \"user\", \"content\": \"$EFFECT\"}],
      \"stream\": false
    }"
  echo "---"
done
```

## Fallback: standard prediction API

Verified working when the each::sense agent returns 402. Same key, same balance,
different endpoint — `https://api.eachlabs.ai/v1/prediction/`. It is asynchronous:
submit, then poll.

### Models

| Purpose | Model | Notes |
|---|---|---|
| **Sound effects** | `bytedance-seed-audio-1-0` | Only model in the standard catalogue that turns **plain text** into arbitrary audio. Despite the TTS-looking parameters it does produce isolated transients (verified: a 0.15 s wooden click inside a 1.6 s file), not speech |
| **Music / BGM** | `ace-step-1-5-text-to-music` | `duration` 10–600 s, optional `bpm` |

List everything with `curl -H "X-API-Key: $EACHLABS_API_KEY" https://api.eachlabs.ai/v1/models?limit=2000`
and check each candidate's `output_type` — only three models output audio.

### Submit and poll

```bash
PID=$(curl -s -X POST https://api.eachlabs.ai/v1/prediction/ \
  -H "Content-Type: application/json" -H "X-API-Key: $EACHLABS_API_KEY" \
  -d '{
    "model": "bytedance-seed-audio-1-0",
    "version": "0.0.1",
    "input": {"prompt": "a small walnut peg tapping a thick wooden board once, warm, dry, 0.12 seconds"}
  }' | python3 -c "import json,sys; print(json.load(sys.stdin)['predictionID'])")

# poll until status is success / error
until [ "$(curl -s -H "X-API-Key: $EACHLABS_API_KEY" \
    "https://api.eachlabs.ai/v1/prediction/$PID" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")" != "running" ]; do
  sleep 6
done

curl -s -H "X-API-Key: $EACHLABS_API_KEY" "https://api.eachlabs.ai/v1/prediction/$PID" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['output'][0])"
```

`output` is a list whose first item is the audio URL. **Only one prediction may run at a
time per account** — a second submit while one is active returns **429
`wait for an active execution to finish before retrying`**, so generate serially with a
short pause between items.

### Post-processing is not optional

Raw output is roughly 1.6 s long with silence on both ends and a low level. Three fixes:

1. **Trim the silence.** A 0.58 s tail of silence means the game plays the click half a
   second late.
2. **Normalise.** Levels vary wildly between generations — one effect came out at
   −14 dBFS peak while its siblings hit 0 dBFS.
3. **Convert** to mono mp3 at your target bitrate.

**Do not use ffmpeg's `silenceremove` for step 1.** It thresholds on absolute dB, and the
noise floor differs per generation: at `-50dB` it over-trimmed some files and did nothing
to others (measured: one file kept a 0.58 s tail, another kept a 0.32 s lead). Locate the
content window **from the samples themselves** — decode to mono PCM, find the first and
last sample above ~6 % of the peak, then cut with a few ms of lead-in and a short
fade-out:

```bash
# after computing START/DUR/GAIN from the decoded samples
ffmpeg -y -ss "$START" -t "$DUR" -i raw.wav \
  -af "volume=$GAIN,afade=t=out:st=$FADE_ST:d=0.03" -ac 1 -b:a 96k out.mp3
```

A complete working implementation of this pipeline (prompts in files, submit, poll,
sample-accurate trim, normalise, budget check) is at
`tool/gen_audio.py` in the `flutter_color_squeeze_out` project.

### If the model output is too quiet

Some prompts yield material so soft that even 8× gain leaves it ~14 dB below the others.
Rewriting the prompt beats amplifying noise — add *"clear, close-miked, well recorded,
present and clearly audible (not distant or timid)"* and regenerate.

## Common Pitfalls

- **No duration** lets the model guess length, which may not fit your project. Always specify duration.
- **Too vague** ("a cool sound") produces generic results. Describe the sound with physical detail.
- **Expecting exact replication** of specific copyrighted sounds is unreliable. Describe the characteristics instead.
- **Ignoring the environment** produces context-free sounds. Mention reverb, room size, and distance for realism.
- **Overloaded requests** with too many simultaneous elements may produce muddy audio. Layer complex scenes from individual effects.
- **Shipping the raw output** as-is. It carries silence on both ends and inconsistent
  loudness — in a game that reads as "the button lags" and "some sounds are missing".
  Always trim and normalise; see [Fallback](#fallback-standard-prediction-api).
- **Assuming a 402 means you need to top up.** Check the control cases first: a bad key
  returns 401, so 402 with a valid key means the service cannot see your balance, and
  adding more credits changes nothing.

## Related Skills

- [Music Generation](../music-generation/SKILL.md) — Generate instrumental music and background tracks
- [Voice Generation](../voice-generation/SKILL.md) — Generate voice audio to layer with sound effects
- [Video Generation](../video-generation/SKILL.md) — Create videos with matched audio
- [Song Generation](../song-generation/SKILL.md) — Full song production with effects

## Documentation

- [each::sense Overview](https://docs.eachlabs.ai/sense/overview)
- [each::labs API](https://docs.eachlabs.ai)
