# YouTube Agents

Local-first rebuild of the YouTube automation pipeline. This project will be built one agent at a time.

## Pipeline Target

1. ResearchAgent
2. StrategyAgent
3. IdeaAgent
4. OutlineAgent
5. ScriptAgent
6. CritiqueAgent
7. PackageAgent

Only ResearchAgent v1 is implemented right now.

## Setup

Paste your YouTube Data API key into `.env`:

```env
YOUTUBE_API_KEY=your_key_here
```

## ResearchAgent V1

Responsibility: collect clean YouTube/topic evidence from a topic. It does not choose the niche lane, final video angle, premise, or script direction.

Inputs:

- `topic`
- `audience`
- `style`
- `manual_brief`
- `youtube_settings`

Outputs:

- `research.json`
- `query_plan`
- `market_stats`
- `competitor_videos`
- `breakout_videos`
- `title_patterns`
- `viewer_pains`
- `claims_to_verify`
- `source_errors`
- `handoff_contract`

JSON schema:

- `schemas/research.schema.json`

CLI:

```bash
python3 main.py research \
  --topic "walnuts" \
  --audience "health curious adults" \
  --style "documentary explainer" \
  --content-type scriptable \
  --source youtube \
  --youtube-max-results 10 \
  --youtube-max-queries 10 \
  --youtube-comments-per-video 5
```

Offline smoke run:

```bash
python3 main.py research --topic "walnuts" --source offline
```

Tests:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests
```

Query templates:

ResearchAgent builds neutral evidence-discovery queries from templates. For `walnuts`, it can produce searches such as:

- `walnuts`
- `walnuts explained`
- `walnuts benefits`
- `walnuts risks`
- `walnuts mistakes`
- `walnuts myths`
- `walnuts what happens`
- `walnuts science`
- `walnuts beginner guide`
- `walnuts side effects`
- `what happens when you eat walnuts`
- `walnuts nutrition facts`

It can also append audience, style, manual topic context, and manual include keywords. It does not generate forced strategy-lane queries like `POV life as {topic}`.

Content type:

Use `--content-type` to filter evidence by video duration:

- `both`: keep all durations
- `shortform`: keep videos up to 60 seconds
- `midform`: keep videos from 61 to 239 seconds
- `longform`: keep videos at least 240 seconds
- `scriptable`: keep videos at least 180 seconds

For script research, start with:

```bash
python3 main.py research --topic "walnuts" --source youtube --content-type scriptable
```

Handoff to StrategyAgent:

StrategyAgent should read `research.json`, choose the recommended niche lane and angle, explain its rationale from the evidence, and write `strategy.json`. It may annotate research for downstream agents later, but ResearchAgent should stay evidence-only.
