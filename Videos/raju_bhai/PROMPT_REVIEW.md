# Raju Bhai - Prompt Review (what I changed and why)

## What is already strong in your prompt
- A clear fixed character (tiger, green jacket, RB pendant, scar) - this becomes the channel brand.
- 10 short parts that each end on a cliffhanger, then 3 long videos built from them.
- One master animation with three language voices (cheaper, identical visuals).
- Not copying the white-lion / gold-gangster look of the reference channel. Keep it that way.

## Changes I recommend (and have applied to the sample)

| # | Change | Why |
|---|--------|-----|
| 1 | **Hook in the first 2 seconds** (title + an impossible image: a bus with no driver) | Shorts are judged on "viewed vs swiped away" in the first seconds |
| 2 | **Keep each Short 40-55 s, vertical 1080x1920** | Stays inside the Shorts sweet spot and is fully watched more often |
| 3 | **Subtitles burned in, large, in the safe area** (above the Shorts buttons) | Most Shorts are watched on mute; Tamil/Hindi text must be readable |
| 4 | **End every part with a open question + "Part 2 next" card** | Drives subscribe and "watch next part" |
| 5 | **Introduce Chintu (sidekick) in Part 2, not Part 6** | Part 6 is emotional only if the audience already loves Chintu |
| 6 | **Add one recurring catchphrase** (suggestion: "Raju Bhai aa gaya" / "Ye shehar mera hai") | Fans repeat it in comments; it becomes the brand |
| 7 | **One language per upload, language in the title** (separate uploads or separate playlists) | Keeps Tamil, Hindi and English audiences from diluting each other's watch time |
| 8 | **Thumbnail formula fixed**: tiger face + 2-3 word red banner + part number | Recognisable in the feed; the situation changes each part |
| 9 | **Children-in-danger kept non-graphic**; set "Not made for kids" | Avoids limited-ads / kids-content restrictions while keeping the tension |
| 10 | **Upload order**: Part 1-3 on day 1, then one part a day | New viewers can binge; the algorithm sees session time |

## Honest limits you should know before approving more episodes

1. **Visual quality.** This machine has no GPU and no AI image/video model access. The sample uses illustrated 2D scenes with camera moves, rain, lightning, effects, neural voices and sound design. It is **not** the cinematic 3D look of your reference. For that look, each scene needs a real image/video model (Midjourney/Flux for key art, Runway/Kling/Veo/Luma for motion). The pipeline is built so those clips can be dropped in per scene (see "Upgrade path").
2. **Views are not guaranteed.** Nothing here can promise reach. What helps: consistent upload schedule, strong first 2 seconds, thumbnails, a repeatable series, and replying to comments.
3. **YouTube monetisation rules.** Channels that publish many near-identical, fully automated videos can be rejected as "inauthentic / mass-produced" content. Keep a real creative layer: your own story twists, your own voice choices, varied scenes. Also use YouTube's "altered or synthetic content" disclosure where it applies.
4. **Tamil and Hindi lines** in the sample were written by me and voiced by Microsoft neural voices. Please have a native speaker read them before publishing: natural slang matters more than accuracy.

## Upgrade path to cinematic quality (when you have access)
1. Build the **character bible images** (see `bible/CHARACTER_BIBLE.md`) in an image model and keep the seed/reference images.
2. For each scene, generate a still (image model) then animate it (image-to-video model) for 4-6 s.
3. Replace the matching scene in `tools/build_part1.py` with the clip; voice, music, subtitles and title cards stay as they are.
4. Cost control: one master video, three audio/subtitle versions, exactly as in your plan.
