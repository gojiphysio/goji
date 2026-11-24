# Local video benchmark

- Keep each take immutable, including failed launches. A successful encode is
  not a successful action; distinguish setup errors, inference failures and
  visual failures in the result summary.
- Hash the actual conditioning frames. Do not rerender staging underneath a
  running experiment or silently replace a take's input.
- Model comparisons use one GPU job at a time. Record background work that
  affects timing. Native FPS and actual resolved canvas belong in the report;
  comparison exports may repeat frames but must not retime or interpolate.
- Review frames between conditioning timestamps, not only the supplied
  keyframes. Compare troublesome contacts with the same source-guide frames
  before attributing the fault to the model.
- Check the resolved source-aspect canvas: Wan's rounding can reduce a target
  below the intended quality range. Label that take accordingly; requested
  dimensions alone are not the output dimensions.
- A whole-frame "nearly static" warning is not an action verdict. H3's fixed
  background triggered it while the foreground exit completed visibly. Inspect
  the action region and preserve the warning alongside the visual review.
- MLX-Gen 0.40.1's Wan backend also inspects the local folder name, even with
  `--base-model`. Use a full supported alias in a symlink/folder name. The
  first recorded Wan launch demonstrates this failure mode.
- This Homebrew ffmpeg lacks `drawtext`. Create label images and stack them;
  retain labels separately from raw takes.
- These procedural people are blockout proxies, not approved Goji cast assets.
  Judge stability separately from resemblance to the canonical cast.
- Keep H3 footage out of this public repository: access was approved for a
  Singapore-based test, and its license restricts territories for outputs too.
  Never commit HF credentials, caches or weight files.
