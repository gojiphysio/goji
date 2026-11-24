# Taxi chase control comparison

- Read `../local-benchmark/AGENTS.md` for immutable takes, visual review and private H3 delivery.
- Both input representations must come from one frozen styled animation: six stills at 0–5 seconds and its continuous clip. Retain the raw Blender motion guide separately.
- Distinguish exact indexed conditioning, ordered image references, endpoints and video references. Unsupported timestamps must never be described as supplied controls.
- Record checkpoint/runtime changes required for guidance. Ref2VA is not the installed H3 FL2VA checkpoint; Wan V2V needs a different checkpoint from Wan I2V.
- No benchmark model starts until the guide's objects, overtakes and camera have been inspected. Reject style conversion that changes the required motion.
- Keep all generated outputs private by default in this experiment. Commit only scripts, source inputs and factual manifests.
