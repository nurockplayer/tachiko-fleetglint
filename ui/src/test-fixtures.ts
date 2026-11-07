/*
 * Typed views over the synthetic fixtures. JSON imports widen literal fields
 * (`1` becomes `number`), so each is cast to its API shape; the fixtures are
 * hand-checked against docs/architecture.md §4.
 */
import type {
  FileReadable,
  FileNotReadable,
  RecordResponse,
  Snapshot,
} from "./api/types";
import snapshotJson from "./fixtures/snapshot.json";
import snapshotEmptyJson from "./fixtures/snapshot-empty.json";
import snapshotDemoJson from "./fixtures/snapshot-demo.json";
import recordRunJson from "./fixtures/record-run.json";
import recordJobJson from "./fixtures/record-job.json";
import fileReadableJson from "./fixtures/file-readable.json";
import fileNotReadableJson from "./fixtures/file-not-readable.json";
import { board, boardEmpty, boardSessions } from "./fixtures/board";

export { board, boardEmpty, boardSessions };
export const snapshot = snapshotJson as unknown as Snapshot;
export const snapshotEmpty = snapshotEmptyJson as unknown as Snapshot;
export const snapshotDemo = snapshotDemoJson as unknown as Snapshot;
export const recordRun = recordRunJson as unknown as RecordResponse;
export const recordJob = recordJobJson as unknown as RecordResponse;
export const fileReadable = fileReadableJson as unknown as FileReadable;
export const fileNotReadable = fileNotReadableJson as unknown as FileNotReadable;
