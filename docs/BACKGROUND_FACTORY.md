# SELMA Labs Background Factory

Background Factory turns a short location brief into repeatable, character-free
anime background coverage. It runs before animation and never grants canon
approval by itself.

## Workflow

1. Write a location brief using `assets/location-brief.example.json`.
2. Create the strict Location Bible:

   ```powershell
   python -m cli.main background init --brief assets/location-brief.example.json --output output/preproduction/rain-station.json
   ```

3. Inspect the deterministic 12-shot coverage plan:

   ```powershell
   python -m cli.main background plan --input output/preproduction/rain-station.json --output output/preproduction/rain-station-plan.json
   ```

4. With the configured image and vision providers running, generate clean
   plates and their quality manifest:

   ```powershell
   python -m cli.main background generate --input output/preproduction/rain-station.json --manifest output/preproduction/rain-station-candidates.json
   ```

The factory produces wide, medium and close coverage from front, reverse and
both three-quarter directions. Prompts share immutable geometry, palette,
lighting and architecture. Characters, people, text, logos and perspective
drift are forbidden.

## Quality and approval

Every generated plate is inspected by the configured vision provider. Failed
plates go under `background-candidates/<location>/quarantine` and receive a new
seed for at most three attempts. Passing plates go under `source`, but remain
`human_approved: false` until an art director selects and locks them.

The manifest declares foreground/midground/background separation and requires a
depth map. A plate reports `parallax_ready: false` until a real depth extractor
has produced that artifact; SELMA Labs does not pretend that a flat image is a
finished 2.5D scene.

After an art director reviews all 12 accepted plates, the explicit approval
command records the reviewer and locks the Location Bible:

```powershell
python -m cli.main background approve --input output/preproduction/rain-station.json --manifest output/preproduction/rain-station-candidates.json --approved-by "art-director" --output output/preproduction/rain-station-locked.json
```
