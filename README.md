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

ResearchAgent v1, StrategyAgent v1, and IdeaAgent v1 are implemented right now.

## Setup

Paste your YouTube Data API key into `.env`:

```env
YOUTUBE_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
OPENAI_IDEA_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_IDEA_MODEL=llama3.1
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
- `strong_fit_competitors`
- `adjacent_opportunity_videos`
- `off_context_outliers`
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
  --language english \
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

Language:

Use `--language english` to reject results whose titles appear mostly non-English/non-Latin:

```bash
python3 main.py research --topic "walnuts" --source youtube --language english
```

Competitor fit buckets:

ResearchAgent keeps the full `competitor_videos` list, then scores each video for how well it fits the intended topic context. It does not hard-delete weird high-performing videos just because they are off-context.

- `strong_fit_competitors`: direct competitors for lane and angle decisions
- `adjacent_opportunity_videos`: nearby evidence that may inspire packaging or hooks
- `off_context_outliers`: high-performing but clearly different-context videos to inspect creatively

StrategyAgent prefers `strong_fit_competitors` for niche scoring when that bucket exists.

Handoff to StrategyAgent:

StrategyAgent should read `research.json`, choose the recommended niche lane and angle, explain its rationale from the evidence, and write `strategy.json`. It may annotate research for downstream agents later, but ResearchAgent should stay evidence-only.

## StrategyAgent V1

Responsibility: read `research.json`, score niche lanes from the YouTube evidence, choose a recommended niche lane and angle, and write `strategy.json`.

It currently scores these lanes:

- `education`
- `goal_instruction`
- `review_comparison`
- `random_curiosity`
- `pov_life_as`

Inputs:

- `research.json`

Outputs:

- `strategy.json`
- `evidence_summary`
- `recommended_niche_lane`
- `recommended_angle`
- `recommended_angle_type`
- `positioning`
- `confidence`
- `key_evidence`
- `secondary_niche_lane`
- `lane_scores`
- `angle_candidates`
- `strategy_notes`
- `handoff_contract`

JSON schema:

- `schemas/strategy.schema.json`

CLI:

```bash
python3 main.py strategy \
  --research workspace/agent_runs/YYYYMMDD_HHMMSS_topic/research.json
```

StrategyAgent uses:

- query matches from competitor videos
- strong-fit competitor buckets when available
- title patterns
- breakout videos
- audience/style/manual context
- claims to verify
- saturation penalties when a lane looks common

StrategyAgent also reports confidence from the gap between the top lanes, sample size, breakout count, source errors, and whether live YouTube evidence was available. `key_evidence` lists the specific breakout videos, title patterns, and claim risks that influenced the recommendation.

It does not decide the final title, outline, script, or thumbnail package. Those belong to later agents.

## IdeaAgent V1

Responsibility: read `research.json` and `strategy.json`, generate scored candidate video ideas, select the highest-scoring idea, and write `ideas.json`.

IdeaAgent can use `template`, `ollama`, or `openai` generation. The LLM only generates raw candidates; IdeaAgent still normalizes, scores, sorts, and writes the stable `ideas.json` contract.

Inputs:

- `research.json`
- `strategy.json`
- `ideas_per_run`
- `max_candidates`

Outputs:

- `ideas.json`
- `strategy_used`
- `ideas`
- `selected_idea`
- `handoff_contract`

JSON schema:

- `schemas/ideas.schema.json`

CLI:

```bash
python3 main.py ideas \
  --research workspace/agent_runs/YYYYMMDD_HHMMSS_topic/research.json \
  --strategy workspace/agent_runs/YYYYMMDD_HHMMSS_topic/strategy.json \
  --ideas-per-run 5 \
  --provider template
```

OpenAI generation:

```bash
python3 main.py ideas \
  --research workspace/agent_runs/YYYYMMDD_HHMMSS_topic/research.json \
  --strategy workspace/agent_runs/YYYYMMDD_HHMMSS_topic/strategy.json \
  --ideas-per-run 5 \
  --provider openai \
  --model gpt-4o-mini
```

Ollama generation:

```bash
python3 main.py ideas \
  --research workspace/agent_runs/YYYYMMDD_HHMMSS_topic/research.json \
  --strategy workspace/agent_runs/YYYYMMDD_HHMMSS_topic/strategy.json \
  --ideas-per-run 3 \
  --max-candidates 5 \
  --provider ollama \
  --model llama3.1
```

For local Ollama runs, `llama3.1` gives stronger idea generation than smaller 3B models, but it can use more laptop CPU/GPU and RAM. The project does not cap Ollama context size, output length, or keep-alive settings; Ollama uses the model's own defaults.

Each idea includes:

- `working_title`
- `niche_lane`
- `angle_type`
- `viewer_promise`
- `why_it_can_work`
- `evidence_used`
- `differentiation`
- `risk_notes`
- `score`

IdeaAgent does not create the outline or script. That belongs to OutlineAgent.
