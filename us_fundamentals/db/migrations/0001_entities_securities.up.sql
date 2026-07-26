-- Temporal entity, security, and listing structures (UF-030/031/032/033 targets).
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE entity (
    entity_id      TEXT PRIMARY KEY,
    cik            BIGINT NOT NULL UNIQUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Time-varying entity attributes; current state never rewrites prior intervals.
CREATE TABLE entity_history (
    entity_id      TEXT NOT NULL REFERENCES entity(entity_id),
    attribute      TEXT NOT NULL,   -- legal_name | incorporation | fiscal_year_end | entity_type | ...
    value          TEXT NOT NULL,
    valid_from     TIMESTAMPTZ NOT NULL,
    valid_to       TIMESTAMPTZ,     -- null = open interval
    source_kind    TEXT NOT NULL,   -- accession | sec_snapshot | manual_evidence
    source_ref     TEXT NOT NULL,
    confidence     REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    PRIMARY KEY (entity_id, attribute, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE security (
    security_id    TEXT PRIMARY KEY,
    entity_id      TEXT NOT NULL REFERENCES entity(entity_id),
    title          TEXT,
    share_class    TEXT,
    figi           TEXT,
    status         TEXT NOT NULL DEFAULT 'active',  -- active | inactive | delisted
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE listing (
    listing_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    security_id            TEXT NOT NULL REFERENCES security(security_id),
    ticker                 TEXT NOT NULL,
    exchange               TEXT NOT NULL,
    valid_from             DATE NOT NULL,
    valid_to               DATE,        -- null = still listed
    inference_rule_version TEXT NOT NULL,
    confidence             REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    review_status          TEXT NOT NULL DEFAULT 'unreviewed',
    allow_multi_listing    BOOLEAN NOT NULL DEFAULT false,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    -- Overlapping intervals for one security/exchange are rejected unless an
    -- explicit multi-listing rule permits them.
    CONSTRAINT listing_no_overlap EXCLUDE USING gist (
        security_id WITH =,
        exchange WITH =,
        daterange(valid_from, COALESCE(valid_to, 'infinity'::date), '[)') WITH &&
    ) WHERE (NOT allow_multi_listing)
);

CREATE INDEX listing_ticker_idx ON listing (ticker, exchange, valid_from);
