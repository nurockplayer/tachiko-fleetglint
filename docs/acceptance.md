# Acceptance

Acceptance lives in [plan.yaml](../plan.yaml). To show this repository's plan in
Fleetglint, add the following to `${XDG_CONFIG_HOME:-$HOME/.config}/fleetglint/config.toml`
(or to the file you pass with `fleetglint --config`):

```toml
[plans]
paths = ["~/Developer/tachiko-fleetglint"]
```

Replace the example path with the directory containing your checkout's `plan.yaml`.
If the config already has a `[plans]` section, add the directory to its `paths` list.
With `plan-check` on Fleetglint's `PATH`, start or restart `fleetglint serve` and
open `/plans` on the board. Fleetglint loads the plan in the background.

From the repository root, you can also validate the plan with `plan-check . --json`.
