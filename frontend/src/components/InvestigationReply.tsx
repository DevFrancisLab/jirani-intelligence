import type { InvestigationBrief } from "../api/client";
import {
  buildSummary,
  hasNoSupportingRecords,
  isRetrievedEvidence,
} from "../lib/brief";

type Props = {
  brief: InvestigationBrief;
};

export function InvestigationReply({ brief }: Props) {
  if (brief.clarification?.question) {
    return (
      <div className="clarification" role="status">
        {brief.clarification.question}
      </div>
    );
  }

  const summary = buildSummary(brief);
  const noRecords = hasNoSupportingRecords(brief);

  return (
    <div>
      {summary && (
        <div className="reply-section">
          <h3>Summary</h3>
          {brief.findings.map((finding, index) => (
            <p key={`${finding.statement}-${index}`} style={{ marginTop: index ? "0.55rem" : 0 }}>
              <span
                className={`badge ${
                  isRetrievedEvidence(finding.source)
                    ? "evidence"
                    : "interpretation"
                }`}
              >
                {isRetrievedEvidence(finding.source)
                  ? "Grounded in records"
                  : "AI interpretation"}
              </span>
              {finding.statement}
              {finding.record_ids.length > 0 && (
                <span style={{ color: "var(--muted)" }}>
                  {" "}
                  (cites {finding.record_ids.join(", ")})
                </span>
              )}
            </p>
          ))}
        </div>
      )}

      {noRecords && (
        <div className="empty-result" role="status">
          I couldn&apos;t find supporting records in the currently available
          sources. This doesn&apos;t establish that the information doesn&apos;t
          exist; the relevant sources may not be connected.
          {brief.next_steps[0] ? (
            <>
              {" "}
              Next step: {softenTechnicalWording(brief.next_steps[0])}
            </>
          ) : null}
        </div>
      )}

      {brief.supporting_records.length > 0 && (
        <div className="reply-section">
          <h3>Evidence</h3>
          <div className="evidence-list">
            {brief.supporting_records.map((record) => (
              <article key={record.record_id} className="evidence-card">
                <div className="evidence-meta">
                  <span className="badge evidence">Retrieved evidence</span>
                  {record.source} · {record.record_id}
                </div>
                <div className="evidence-fields">
                  {Object.entries(record.fields).map(([key, value]) => (
                    <div key={key}>
                      <strong>{key}:</strong> {value}
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>
      )}

      {(brief.uncertainty.length > 0 || brief.evidence_gaps.length > 0) &&
        !noRecords && (
          <div className="reply-section">
            <h3>What remains uncertain</h3>
            <ul>
              {[...brief.uncertainty, ...brief.evidence_gaps]
                .filter(isUserFacingNote)
                .map((item) => (
                  <li key={item}>{softenTechnicalWording(item)}</li>
                ))}
            </ul>
          </div>
        )}

      {brief.next_steps.length > 0 && !noRecords && (
        <div className="reply-section">
          <h3>Suggested next steps</h3>
          <ul>
            {brief.next_steps.filter(isUserFacingNote).map((item) => (
              <li key={item}>{softenTechnicalWording(item)}</li>
            ))}
          </ul>
        </div>
      )}

      {brief.nightshift_handoff && !brief.clarification && (
        <div className="reply-section">
          <p className="status-note">
            Deeper AI interpretation is not available through this session right
            now. Retrieved evidence above still reflects available records.
            Check Settings → System status for provider readiness.
          </p>
        </div>
      )}
    </div>
  );
}

function isUserFacingNote(text: string): boolean {
  const lower = text.toLowerCase();
  if (lower.includes("nvidia")) return false;
  if (lower.includes("stage-2")) return false;
  if (lower.includes("stage-1")) return false;
  if (lower.includes("scout intent")) return false;
  if (lower.includes("organizers")) return false;
  return true;
}

function softenTechnicalWording(text: string): string {
  return text
    .replace(/ZETARIS_SOURCES/g, "registered planning sources")
    .replace(/ZETARIS_BASE_URL/g, "the data connection settings")
    .replace(/ZETARIS_API_KEY/g, "the data access credential")
    .replace(/ZETARIS_ORG_ID/g, "the organisation setting")
    .replace(/METERLESS_[A-Z_]+/g, "the AI provider settings")
    .replace(/NY_TAXI|TPCDS|TPCH/gi, "sample databases");
}
