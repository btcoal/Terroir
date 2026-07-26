-- Filing inventory rows and Bronze accession manifests (UF-021/UF-012 targets).
CREATE TABLE filing (
    accession                   TEXT PRIMARY KEY,
    cik                         BIGINT NOT NULL,
    form                        TEXT NOT NULL,
    is_amendment                BOOLEAN NOT NULL DEFAULT false,
    amends_accession            TEXT REFERENCES filing(accession),
    report_period               DATE,
    filing_date                 DATE NOT NULL,
    -- UF-003 information-time fields.
    sec_acceptance_datetime     TIMESTAMPTZ NOT NULL,
    information_available_at    TIMESTAMPTZ,
    observed_first_seen_at      TIMESTAMPTZ,
    availability_method         TEXT
        CHECK (availability_method IN
               ('observed_dissemination', 'acceptance_plus_buffer', 'manual_evidence')),
    availability_policy_version TEXT,
    availability_confidence     TEXT
        CHECK (availability_confidence IN ('exact', 'modeled', 'assumed')),
    -- UF-001: eligibility and ingestion are separate axes, never collapsed.
    eligibility_status          TEXT NOT NULL
        CHECK (eligibility_status IN ('eligible', 'excluded', 'indeterminate')),
    eligibility_reasons         JSONB NOT NULL DEFAULT '[]',
    eligibility_policy_version  TEXT NOT NULL,
    ingestion_status            TEXT NOT NULL DEFAULT 'not_recorded'
        CHECK (ingestion_status IN
               ('not_recorded', 'not_attempted', 'acquired', 'retry_pending',
                'terminal_failure', 'unavailable_upstream')),
    discovery_sources           JSONB NOT NULL DEFAULT '[]',
    discovery_conflicts         JSONB NOT NULL DEFAULT '[]'
);

CREATE INDEX filing_cik_idx ON filing (cik, filing_date);
CREATE INDEX filing_form_idx ON filing (form, filing_date);

-- One row per stored/reference object in an accession's parser-input closure.
CREATE TABLE accession_object (
    accession      TEXT NOT NULL REFERENCES filing(accession),
    file_name      TEXT NOT NULL,
    role           TEXT NOT NULL,   -- index | primary_document | instance | extension_schema
                                    -- | linkbase | label | reference | header | external
    storage_class  TEXT NOT NULL
        CHECK (storage_class IN ('stored', 'optional_cold', 'reference_only')),
    source_url     TEXT NOT NULL,
    size_bytes     BIGINT,
    sha256         TEXT,
    content_type   TEXT,
    retrieved_at   TIMESTAMPTZ,
    CHECK (storage_class = 'reference_only'
           OR (sha256 IS NOT NULL AND size_bytes IS NOT NULL)),
    PRIMARY KEY (accession, file_name)
);
