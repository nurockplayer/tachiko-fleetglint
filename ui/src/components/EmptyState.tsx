const EMIT_EXAMPLE = `fleetglint emit <<'EOF'
{"v":1,"type":"run","id":"hello-1","source_id":"me@mbp","updated_at":"2026-11-06T04:00:00+09:00","state":"running","agent":"human","started_at":"2026-11-06T04:00:00+09:00"}
EOF`;

/** No sources at all: explain how to add one and offer the labelled demo. */
export function EmptyState() {
  return (
    <div className="empty">
      <h1>No sources yet</h1>
      <p>
        Fleetglint found no records and no readable sources. It only reads local
        files; nothing is sent anywhere.
      </p>
      <h2>It looked for</h2>
      <ul>
        <li>Claude Code transcripts — ~/.claude/projects</li>
        <li>Codex rollouts — ~/.codex/sessions</li>
        <li>tachiko-harness state — ~/.local/state</li>
        <li>NDJSON root — ~/.local/state/fleetglint/sources</li>
      </ul>
      <h2>Check what it sees</h2>
      <pre>fleetglint doctor</pre>
      <h2>Try labelled sample data</h2>
      <pre>fleetglint demo</pre>
      <h2>Write one record</h2>
      <pre>{EMIT_EXAMPLE}</pre>
    </div>
  );
}
