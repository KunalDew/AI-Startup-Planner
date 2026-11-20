"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

type ReportJob = {
  job_id: string;
  status: "processing" | "completed" | "failed";
  result?: Record<string, unknown> | null;
  error?: string | null;
  completed_agents?: number;
  message?: string;
};

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const reportSections = [
  { key: "market_analysis", label: "Market research", number: "01" },
  { key: "product_roadmap", label: "Product plan", number: "02" },
  { key: "financial_projections", label: "Financial strategy", number: "03" },
  { key: "go_to_market_strategy", label: "Go-to-market", number: "04" },
] as const;

function prettyLabel(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function ReportData({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="muted">Not provided</span>;
  }

  if (typeof value === "string" || typeof value === "number") {
    return <p className="report-copy">{String(value)}</p>;
  }

  if (typeof value === "boolean") {
    return <p className="report-copy">{value ? "Yes" : "No"}</p>;
  }

  if (Array.isArray(value)) {
    return (
      <ul className="report-list">
        {value.map((item, index) => (
          <li key={index}>
            {typeof item === "object" && item !== null ? (
              <ReportData value={item} />
            ) : (
              String(item)
            )}
          </li>
        ))}
      </ul>
    );
  }

  if (typeof value === "object") {
    return (
      <dl className="data-grid">
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <div className="data-item" key={key}>
            <dt>{prettyLabel(key)}</dt>
            <dd>
              <ReportData value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return <p className="report-copy">{String(value)}</p>;
}

function ValidationCard({ validation }: { validation: unknown }) {
  if (typeof validation !== "object" || validation === null) {
    return <ReportData value={validation} />;
  }

  const data = validation as Record<string, unknown>;
  const isViable = data.is_viable;
  const score =
    typeof data.score === "number" ? `${data.score}/100` : "Not scored";

  return (
    <div className="validation-content">
      <div className="validation-metrics">
        <div>
          <span className="eyebrow">Validation score</span>
          <strong>{score}</strong>
        </div>
        <span
          className={`decision-badge ${
            isViable === true ? "approved" : "rejected"
          }`}
        >
          {isViable === true
            ? "Promising"
            : isViable === false
              ? "Needs rethinking"
              : "Reviewed"}
        </span>
      </div>
      {typeof data.critique === "string" && (
        <p className="report-copy">{data.critique}</p>
      )}
    </div>
  );
}

function BusinessReport({ result }: { result: Record<string, unknown> }) {
  if (result.status === "rejected") {
    return (
      <section className="rejection-card">
        <span className="eyebrow">Initial assessment</span>
        <h2>This idea needs another look.</h2>
        <p>
          The validation agent recommends addressing the concerns below before
          investing in a full market and product plan.
        </p>
        <ValidationCard validation={result.validation} />
      </section>
    );
  }

  const summary =
    typeof result.executive_summary === "string"
      ? result.executive_summary
      : null;

  return (
    <div className="report-layout">
      {summary && (
        <section className="summary-card">
          <div className="section-heading">
            <span className="eyebrow">The opportunity</span>
            <span className="section-number">OVERVIEW</span>
          </div>
          <h2>Executive summary</h2>
          <p>{summary}</p>
        </section>
      )}

      {result.validation_notes !== undefined && (
        <section className="report-section validation-card">
          <div className="section-heading">
            <span className="eyebrow">Idea assessment</span>
            <span className="section-number">00</span>
          </div>
          <h2>Validation</h2>
          <ValidationCard validation={result.validation_notes} />
        </section>
      )}

      <div className="report-sections">
        {reportSections.map(({ key, label, number }) =>
          result[key] === undefined || result[key] === null ? null : (
            <details className="report-section" key={key} open>
              <summary>
                <span className="section-number">{number}</span>
                <span>{label}</span>
                <span className="expand-icon" aria-hidden="true">
                  +
                </span>
              </summary>
              <div className="section-body">
                <ReportData value={result[key]} />
              </div>
            </details>
          ),
        )}
      </div>

      <details className="raw-report">
        <summary>View complete report data</summary>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </details>
    </div>
  );
}

export default function Home() {
  const [idea, setIdea] = useState("");
  const [job, setJob] = useState<ReportJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const jobId = job?.job_id;
  const jobStatus = job?.status;

  // SSE Stream integration replaces the old HTTP polling loop
  useEffect(() => {
    if (!jobId || jobStatus !== "processing") return;

    let active = true;
    const eventSource = new EventSource(`${API_URL}/reports/${jobId}/stream`);

    eventSource.onmessage = (event) => {
      if (!active) return;
      try {
        const streamData = JSON.parse(event.data);
        
        setJob((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            status: streamData.status,
            result: streamData.result,
            error: streamData.error,
            completed_agents: streamData.completed_agents,
            message: streamData.message,
          };
        });
        setRequestError(null);

        // Close stream when terminal states are reached
        if (streamData.status === "completed" || streamData.status === "failed") {
          eventSource.close();
        }
      } catch (error) {
        console.error("Error parsing SSE data:", error);
      }
    };

    eventSource.onerror = () => {
      if (active) {
        setRequestError("Lost connection to the live progress stream.");
        eventSource.close();
      }
    };

    return () => {
      active = false;
      eventSource.close();
    };
  }, [jobId, jobStatus]);

  async function submitIdea(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedIdea = idea.trim();
    if (!trimmedIdea) {
      setRequestError("Add a short description of your startup idea first.");
      return;
    }

    setSubmitting(true);
    setRequestError(null);
    setJob(null);
    try {
      const response = await fetch(`${API_URL}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idea: trimmedIdea }),
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(
          `Could not submit the idea (${response.status})${message ? `: ${message}` : "."}`,
        );
      }

      const submittedJob = (await response.json()) as ReportJob;
      if (!submittedJob.job_id) {
        throw new Error("The API did not return a job ID.");
      }
      setJob(submittedJob);
    } catch (error) {
      setRequestError(
        error instanceof Error
          ? error.message
          : "Something went wrong while submitting your idea.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function startOver() {
    setJob(null);
    setRequestError(null);
    setIdea("");
  }

  return (
    <main className="studio-shell">
      <header className="topbar">
        <Link className="brand" href="/" aria-label="Startup Research Studio home">
          <span className="brand-mark">S</span>
          <span>venture<span className="brand-light">/lab</span></span>
        </Link>
        <span className="topbar-note">AI-powered venture research</span>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <div className="hero-kicker">
            <span className="status-dot" />
            YOUR NEXT BIG IDEA, BETTER INFORMED
          </div>
          <h1>
            Make your idea
            <br />
            <span>investor-ready.</span>
          </h1>
          <p className="hero-description">
            A team of AI analysts validates your concept, sizes the market, and
            builds a practical plan to take it to market.
          </p>
          <div className="hero-footnote">
            <span>01 — Validate</span>
            <span>02 — Research</span>
            <span>03 — Build a plan</span>
          </div>
        </div>

        <div className="form-card">
          <div className="card-topline">
            <span className="eyebrow">START WITH THE SPARK</span>
            <span className="card-index">01 / 01</span>
          </div>
          <h2>What are you building?</h2>
          <p className="form-hint">
            Describe the problem, your solution, or just the early idea.
          </p>
          <form onSubmit={submitIdea}>
            <label className="sr-only" htmlFor="idea">
              Describe your startup idea
            </label>
            <textarea
              id="idea"
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              placeholder="For example: A ready-to-drink protein shake made with simple ingredients for busy professionals..."
              maxLength={10_000}
              rows={5}
              disabled={submitting || job?.status === "processing"}
            />
            <div className="form-footer">
              <span>{idea.length.toLocaleString()} / 10,000</span>
              <button
                type="submit"
                className="primary-button"
                disabled={submitting || job?.status === "processing"}
              >
                {submitting ? "Sending idea..." : "Build my business plan"}
                <span aria-hidden="true">↗</span>
              </button>
            </div>
          </form>
          <div className="privacy-note">
            <span aria-hidden="true">✳</span>
            Research is generated by your connected CrewAI workflow.
          </div>
        </div>
      </section>

      {requestError && (
        <div className="alert error-alert" role="alert">
          <strong>Connection issue</strong>
          <span>{requestError}</span>
          <small>
            Confirm the FastAPI server is running at {API_URL}, then try again.
          </small>
        </div>
      )}

      {job && (
        <section className="results" aria-live="polite">
          <div className="results-heading">
            <div>
              <span className="eyebrow">YOUR RESEARCH BRIEF</span>
              <h2>Business plan</h2>
            </div>
            <button type="button" className="text-button" onClick={startOver}>
              ← New idea
            </button>
          </div>

          {job.status === "processing" && (
            <div className="progress-card">
              <div className="spinner" aria-hidden="true" />
              <div>
                <strong>Your research team is at work.</strong>
                <p>
                  {job.message || "We're validating your idea and preparing the research. This can take a few minutes."}
                </p>
                <span className="job-id">JOB {job.job_id}</span>
              </div>
            </div>
          )}

          {job.status === "failed" && (
            <div className="alert error-alert" role="alert">
              <strong>Report generation failed</strong>
              <span>{job.error || "The workflow returned an unknown error."}</span>
              <button type="button" className="text-button" onClick={startOver}>
                Try another idea
              </button>
            </div>
          )}

          {job.status === "completed" && job.result && (
            <BusinessReport result={job.result} />
          )}
        </section>
      )}

      <footer className="site-footer">
        <span>VENTURE/LAB</span>
        <span>Think clearly. Build intentionally.</span>
      </footer>
    </main>
  );
}