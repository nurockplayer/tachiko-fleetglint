import { Fragment } from "react";
import type { FileResponse } from "../api/types";
import { formatBytes } from "../format";

const NOT_READABLE_REASON: Record<string, string> = {
  outside_allowed_roots: "outside the allowed roots",
  not_regular_file: "not a regular file",
  missing: "missing",
  not_utf8: "not UTF-8 text",
  no_path: "no path on the record",
};

export interface LogTailProps {
  file: FileResponse | null;
  loading: boolean;
  error: string | null;
}

/** The log tail: mono 12/18 on the raised surface, wrapped, redactions explicit. */
export function LogTail({ file, loading, error }: LogTailProps) {
  if (loading) return <p className="quiet">Loading log…</p>;
  if (error) return <p className="quiet">Log unavailable: {error}</p>;
  if (!file) return <p className="quiet">No log attached to this record.</p>;
  if (!file.readable) {
    return (
      <div className="log not-readable" data-log="not-readable">
        <p>Log unavailable</p>
        <p className="quiet">{NOT_READABLE_REASON[file.reason] ?? file.reason}</p>
      </div>
    );
  }

  const parts = file.text.split("[redacted]");
  return (
    <div className="log" data-log="readable">
      {file.truncated ? (
        <p className="log-note">
          Showing the last part of {formatBytes(file.size)} · {file.redactions} redacted
          span{file.redactions === 1 ? "" : "s"}
        </p>
      ) : null}
      <pre>
        {parts.map((part, index) => (
          <Fragment key={index}>
            {part}
            {index < parts.length - 1 ? (
              <span className="redacted" title="removed before display">
                [redacted]
              </span>
            ) : null}
          </Fragment>
        ))}
      </pre>
    </div>
  );
}
