# Video Producer Plugin — User Guide

**Quick start:** Open `/video-producer` in CorvinOS Console, describe a video, click "Create", and wait for the MP4.

---

## What This Plugin Does

Turns a **text description** into a **professional narrated video** (1–3 minutes):

1. **Storyboard** — An AI reads your description and breaks it into scenes with narration
2. **Narration** — Each scene is read aloud using a natural human voice (OpenAI TTS)
3. **Slides** — Animated diagrams appear in the corvin-labs.com design (dark theme by default)
4. **Video** — Everything is assembled into an MP4 you can download and share

**Time to create:** ~2–3 minutes for a 2-minute video (rendering happens in the background)

---

## Example

**Your input:**
```
Create a 2-minute educational video explaining exponential growth.
Start with a simple definition, show a curve that grows over time,
then explain real-world examples like population and epidemiology.
End with why it matters.
```

**What happens:**
- ✅ AI writes 6 scenes with narration (~60 words each)
- ✅ Each scene gets a natural voice reading
- ✅ Scene 1: title + definition
- ✅ Scene 2–4: animated charts (line graph, exponential curve, comparison)
- ✅ Scene 5: real-world examples (text + callout boxes)
- ✅ Scene 6: summary and key takeaway
- ✅ **Result:** `exponential-growth-2min.mp4` (1920×1080, 30fps)

---

## Using the Console Panel

### Step 1: Open the Panel
Navigate to **Media** → **Video Producer** (or go to `/video-producer`)

### Step 2: Describe the Video in the Composer
Under the video stage, write what you want in the text box (or hold **Space** and speak; release to stop).
Use the paperclip to attach text, Markdown or PDF files as source material (up to 4 files, 2 MiB each).

**Best practices:**
- Be specific: "Educational video about..." vs. "Make a cool video"
- Mention the target audience: "Explain to college students"
- Say how long: "2-minute video" (videos of one to three minutes work best)
- Give structure hints: "Start with..., then explain..., end with..."

### Step 3: Choose the Narration Engine (Optional)

In **Settings** you choose how the video is narrated: **OpenAI** (default, best quality, needs an OpenAI key on the host), **Auto** (tries OpenAI, then free engines, if the key is missing or the API fails) or the legacy **gTTS** engine. The Settings panel also tells you whether OpenAI and the slide renderer (Chromium) are available on this host. Theme, frame rate and slide type are not user-selectable in the console.

### Step 4: Send

Press **Enter** (or the send button). The stage shows a progress bar while the video renders in the background,
then plays it at full width. **F** (or the fullscreen button) goes fullscreen.

### Step 5: Change a Finished Video

Select a produced video, or press **Revise** on its card, describe the change ("make scene 2 shorter") and send.
A new video is produced; the original stays and the new card carries a *revision* badge.

### Step 6: Use Your Own Look (PowerPoint Style)

By default every video looks like CorvinOS. To make videos that look like *your* deck:

1. Open the **Style** chip next to the mode switch and choose **Import from PowerPoint…**, or attach a `.pptx` / `.potx`
   file in the composer and choose **Use as style** (a different action from using it as source material).
2. The import dialog shows three sample slides rendered with the extracted look. Check or change:
   - **Name** and **Wordmark** (the wordmark is shown in the footer of every slide),
   - **Default theme** — a styled video uses this theme throughout,
   - **Decoration** (Corvin constellation, a soft minimal glow, or none),
   - the **colours** (each swatch has a colour picker; the hints under them show whether text stays readable),
   - the **fonts** — your deck's fonts are mapped to the three fonts Video Producer bundles, and you can change the mapping,
   - the **logo** (remove it, or switch off showing it large at the start), and the optional "made with CorvinOS" credit (off by default).
3. **Save** (or **Save and set as default**). Pick the style in the chip before sending; a video you revise keeps
   its original style unless you pick another.

What is read from the deck: colours, fonts and a logo picture from the master/layouts. What is **never** read: slide
text, speaker notes, comments, author names, animations, embedded fonts, linked images, background pictures. The deck
itself is not stored — only the extracted style. Macro files (`.pptm`) are refused; the limit is 25 MB.

**Decks that use PowerPoint's default colours** (most do) carry no brand colour. You will see a note and a neutral
accent — pick your own accent in the dialog. If your logo is hard to see on the chosen theme, the dialog says so.

Limits: 20 saved styles per workspace; one look per video (a styled video does not mix light and dark slides); slide
masters' background artwork is not reproduced (only colours and the logo). Slides that cannot be rendered as web slides
fall back to a plain slide that uses your palette and wordmark. A style derived from a third-party template does not
transfer the template's rights. The style used is stored next to each video (`videos/<job>/style/`).

### Step 7: Download

When the status shows ✅ **Complete**, click **Download** to get the MP4.

---

## Troubleshooting

### ❌ "OpenAI API Error" or "Missing API Key"

**Cause:** Your host doesn't have an OpenAI API key configured.

**Fix:**
1. Contact your CorvinOS operator to add `OPENAI_API_KEY` to the environment
2. OR, temporarily switch the narration engine to **Auto** in Settings (free engines take over; quality is lower)

### ❌ "Rendering failed, using fallback slide"

**Cause:** The web slide renderer (Chromium) isn't available.

**Fix:**
- This is normal and safe — the video still plays, just with simpler slides
- Contact your operator if this happens often

### ❌ "Job failed"

**Check the error message:**
- **"Storyboard generation failed"** → Your description might be too long or unclear. Try splitting it into 2 shorter videos.
- **"TTS failed for scene X"** → Narration failed. Check if the OpenAI API is reachable.
- **"FFmpeg error"** → Assembly failed. This is rare; try again or contact your operator.

### ❌ Video is jerky or low quality

**Cause:** the description asked for too many complex visuals in one video.

**Fix:**
- Split a very long description into two shorter videos
- Simplify your description: fewer scenes, fewer transitions
- Keep to one idea per scene

---

## Examples & Templates

### Example 1: Educational Explainer
```
Create a 2-minute educational video explaining how neural networks learn.
- Start with the biological brain analogy
- Show how artificial neurons work (simple diagram)
- Demonstrate training on a simple example (line chart showing error decreasing)
- End with a summary of real-world applications
Audience: high school students
```

**Result:** 5 scenes, animated diagrams, natural narration, ~90 seconds

### Example 2: Product Demo
```
Create a 1-minute video showing how to use the CorvinOS console.
- Show the main dashboard
- Click through to create a task
- Show the task completing
- End with the results
Keep it fast-paced and upbeat.
```

**Result:** about 4 animated slides, ~60 seconds. (The console does not capture live screenshots or screen recordings; the video is made of generated slides.)

### Example 3: Data Story
```
Create a 3-minute video about climate change data.
- Global temperature trend (animated line chart, 1880–2024)
- Regional comparison (bar chart: which regions warmed most)
- Future projection (area chart showing scenarios)
- Call to action
Target: policy makers
```

**Result:** 5 scenes, multiple charts, ~180 seconds

---

## What the Video Includes

✅ **Professional design:** Slides match the corvin-labs.com brand  
✅ **Natural narration:** Real human voice (OpenAI) or fallback synthesizer  
✅ **Animations:** Charts draw themselves, text fades in, shapes morph  
✅ **Proper timing:** Narration and visuals stay in sync  
✅ **High resolution:** 1920×1080 at 30fps (YouTube, presentations, etc.)

❌ **NOT included:** Subtitles or captions (by design)  
❌ **NOT included:** Background music or sound effects (narration only)  
❌ **NOT included:** Custom logos or watermarks (use ffmpeg to add after export)

---

## Output Files

When your video is ready, you get:

- `video_<jobid>.mp4` — The final video (download this)
- Metadata with job details (which AI model wrote the storyboard, which voice narrated, etc.)

---

## Limits & Constraints

- **Scenes:** at most 8 per video (6 when the storyboard is written by the local model); narration per scene is capped at 500 characters
- **Task description:** up to 4000 characters
- **Rendering time:** measured on the development host, roughly 1.5 times the video length plus narration time; it runs in the background
- **Template options:** 15 pre-built slide templates (you can't customize them, but AI picks the best one per scene). What the narration names appears at that moment and is highlighted while it is explained.

---

## Tips for Best Results

1. **Be specific:** "Explain photosynthesis to 8th graders" beats "Make a science video"
2. **Use simple language:** The AI writes clearer narration if your description is clear
3. **Focus on one idea:** A video about "climate, renewable energy, and policy" is too much for 2 minutes
4. **Mention structure:** "Start with..., then show..., end with..." helps AI write better scenes
5. **Don't worry about visuals:** The AI and templates handle that. Just describe the content.

---

## Questions?

- **How long does rendering take?** Roughly 1.5 times the video length on the development host; slower on weaker machines
- **Can I edit the video after?** Yes, download the MP4 and edit in any video editor (Final Cut Pro, DaVinci Resolve, etc.)
- **Can I add music?** Yes, after downloading: use ffmpeg or any video editor to add an audio track
- **Why no subtitles?** Subtitles change the visual design; the plugin is optimized for narration-only videos
- **Can I customize the slide design?** Not in the current version, but you can remix the output in a video editor

---

## Related Documentation

- **[Technical Details](WEB-SLIDES.md)** — How the slides are rendered, template specifications
- **[Configuration Reference](../README.md)** — Environment variables, job settings
- **[Architecture](docs/README.md)** — How the plugin works internally (for developers)

---

**Happy video making!** 🎬

