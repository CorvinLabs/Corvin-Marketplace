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

### Step 2: Write Your Task Description
In the **Task** text area, describe the video you want to create.

**Best practices:**
- Be specific: "Educational video about..." vs. "Make a cool video"
- Mention the target audience: "Explain to college students"
- Say how long: "2-minute video" (1–3 minutes is optimal)
- Give structure hints: "Start with..., then explain..., end with..."

### Step 3: Choose Settings (Optional)

| Setting | Default | What It Does |
|---------|---------|---|
| **TTS Engine** | OpenAI | How the video is narrated. Leave as "OpenAI" for best quality. Choose "Fallback" if you're offline. |
| **Web Slides** | On | Use animated diagrams (Chromium rendering). Turn off to use simpler static slides (faster). |
| **Theme** | Dark | Dark or light slide background. |
| **FPS** | 30 | Frames per second. Higher = smoother but slower to render. Keep at 30. |

### Step 4: Click "Create Video"

You'll see a **job ID** and a progress bar. The video renders in the background.

### Step 5: Download

When the status shows ✅ **Complete**, click **Download** to get the MP4.

---

## Troubleshooting

### ❌ "OpenAI API Error" or "Missing API Key"

**Cause:** Your host doesn't have an OpenAI API key configured.

**Fix:**
1. Contact your CorvinOS operator to add `OPENAI_API_KEY` to the environment
2. OR, temporarily switch **TTS Engine** to "Fallback" (uses a free synthesizer, slightly lower quality)

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

**Cause:** FPS set too high, or your description had too many complex visuals.

**Fix:**
- Keep **FPS** at 30 (don't increase)
- Simplify your description: fewer scenes, fewer transitions
- Use the default **Web Slides** setting

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

**Result:** 4 scenes, screenshots + screen recording, ~60 seconds

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

- **Maximum video length:** 3 minutes (6 scenes × ~30 seconds each)
- **Maximum task description:** 500 characters (be concise)
- **Rendering time:** ~2–3 minutes for a 2-minute video (happens in the background, you can work on other things)
- **Template options:** 14 pre-built slide templates (you can't customize them, but AI picks the best one per scene)

---

## Tips for Best Results

1. **Be specific:** "Explain photosynthesis to 8th graders" beats "Make a science video"
2. **Use simple language:** The AI writes clearer narration if your description is clear
3. **Focus on one idea:** A video about "climate, renewable energy, and policy" is too much for 2 minutes
4. **Mention structure:** "Start with..., then show..., end with..." helps AI write better scenes
5. **Don't worry about visuals:** The AI and templates handle that. Just describe the content.

---

## Questions?

- **How long does rendering take?** ~2–3 minutes for a 2-minute video
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

