# CLAUDE.md — Never Kneel (HFY long stories)

Owner: Andrii (Ukrainian, short army-style answers, the best free option). Reply in Ukrainian.
PUBLIC repo (unlimited Actions minutes): no secrets, tokens, e-mails or private notes in any file.

## What
YouTube channel **Never Kneel** (not created yet; the handle later, Andrii Nov 19): long narrated original sci-fi stories in the HFY
genre ("Humanity F*** Yeah": an old alien empire underestimates young humanity, a calm veteran answers in 2-4 words,
the hidden human trick, the empire pays). Model studied Nov 19 2026: @voidbornhumanity-u2u (Voidborn Humanity,
905 subs, 16 videos Nov 1-14, ~14k views each, 33-150 min). We copy the GENRE and the shape, never their scripts,
titles or names.
What worked there: threat + calm human reply in quotes ("Let Them Come" 40k, revenge "Erased 47 Star Systems" 32k,
"Wake the BEAST" 29k). Weak: humour / non-military heroes (1.3k), no human quote (318), 150 min (1.4k).

## Format
- Title formula (<= 100 chars): `[number/empire] [threat verb] — [human rank] [replied/said]: "[2-4 words, one CAPS]"`.
- Video 40-60 min (test: 7 min), 16:9, one AI picture per scene (~25-30 s) with Ken Burns + 0.8 s crossfades, voice,
  dark ambient music at -31 LUFS under it, final -14 LUFS.
- Thumbnail 1280x720: the hero's AI portrait in the scene, black top bar with 3-4 Bebas Neue words, the key word RED,
  a red line under the bar (ours; the model channel uses a yellow word).
- Description: 3-sentence premise + music credit + "An original story. Voice and pictures are AI-generated." +
  #HFY #HFYStories #HumansAreSpaceOrcs #SciFiStories #NeverKneel. categoryId 24.

## Code
`nk.py stories/<id>.json` -> work/<id>/final.mp4, cover.png, metadata.json. Story JSON: id, title, description,
tags, hashtags, thumb{words, key, image, seed}, cast{KEY: look} (inserted for {KEY} in every prompt: the same look
every time), style, scenes[{img, seed, text}].
Voice: TTS=edge (runner, en-US-GuyNeural) | kokoro (sandbox: the cloud proxy has no WebSocket, Edge fails there).
Pictures: IMG=cloudflare (FLUX.1 schnell, CF_ACCOUNT_ID + CF_API_TOKEN, free daily quota) | pollinations
(anonymous, 1024 px + watermark cropped: tests only).
Music: MUSIC_DIR (default music/, gitignored) = ww2-bot's music/jurgen_al (YouTube Audio Library) via ASSETS_TOKEN.
Workflow `video.yml`: manual, renders and uploads the artifact 'video'. Upload to YouTube: not built (needs the channel
+ OAuth, tools/auth_secrets.py style of ww2-long).

## Andrii's list: docs/tasks.md
