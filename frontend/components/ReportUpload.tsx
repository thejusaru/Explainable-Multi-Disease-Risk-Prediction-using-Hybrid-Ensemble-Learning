"use client";

import { useRef, useState, type DragEvent } from "react";
import { CheckCircleIcon, FileIcon, UploadIcon } from "./Icons";

/**
 * Drag-and-drop report upload.
 *
 * Extraction fires as soon as a file is chosen, so the form fills in without a
 * second click. Rejects unsupported types client-side to avoid a round trip
 * that can only fail.
 */

const ACCEPTED_EXTENSIONS = [
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".gif",
  ".json",
  ".txt",
  ".md",
];

interface Props {
  file: File | null;
  onFile: (file: File | null) => void;
  busy: boolean;
  extracting: boolean;
  fieldsFound: string[];
}

export default function ReportUpload({
  file,
  onFile,
  busy,
  extracting,
  fieldsFound,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string | null>(null);

  function accept(candidate: File | null | undefined) {
    if (!candidate) return;
    const name = candidate.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
      setRejected(
        `"${candidate.name}" is not a supported type. Upload a PDF, image, FHIR JSON or text file.`,
      );
      return;
    }
    setRejected(null);
    onFile(candidate);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (busy) return;
    accept(event.dataTransfer.files?.[0]);
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS.join(",")}
        style={{ display: "none" }}
        onChange={(e) => accept(e.target.files?.[0])}
      />

      {!file ? (
        <div
          className={`dropzone${dragging ? " dropzone-active" : ""}`}
          onClick={() => !busy && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            if (!busy) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              if (!busy) inputRef.current?.click();
            }
          }}
        >
          <div className="dropzone-icon">
            <UploadIcon size={26} />
          </div>
          <div className="dropzone-title">
            Drop a medical report, or click to browse
          </div>
          <div className="dropzone-hint">
            PDF, photo, FHIR JSON or plain text — up to 25 MB
          </div>
        </div>
      ) : (
        <div className="file-pill">
          <span className="file-pill-icon">
            <FileIcon size={20} />
          </span>
          <div className="file-pill-body">
            <div className="file-pill-name">{file.name}</div>
            <div className="file-pill-meta">
              {(file.size / 1024).toFixed(0)} KB
              {extracting
                ? " · reading…"
                : fieldsFound.length > 0
                  ? ` · ${fieldsFound.length} field(s) read`
                  : ""}
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={busy}
            onClick={() => {
              onFile(null);
              setRejected(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
          >
            Remove
          </button>
        </div>
      )}

      {rejected && (
        <div className="banner banner-danger" style={{ marginTop: 12 }}>
          <span className="banner-icon">!</span>
          <div>{rejected}</div>
        </div>
      )}

      {fieldsFound.length > 0 && !extracting && (
        <div className="banner banner-success" style={{ marginTop: 12 }}>
          <CheckCircleIcon size={17} className="banner-icon" />
          <div>
            <strong>Details read from the report</strong>
            Check the values below and correct anything that looks wrong before
            analysing.
            <div className="chip-row">
              {fieldsFound.map((field) => (
                <span className="chip" key={field}>
                  {field}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
