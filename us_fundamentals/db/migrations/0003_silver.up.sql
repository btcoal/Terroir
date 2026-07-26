-- Silver: complete raw XBRL structures without economic reinterpretation (UF-026 target).
CREATE TABLE xbrl_context (
    accession         TEXT NOT NULL REFERENCES filing(accession),
    context_id        TEXT NOT NULL,
    entity_identifier TEXT NOT NULL,
    period_type       TEXT NOT NULL CHECK (period_type IN ('instant', 'duration', 'forever')),
    period_start      DATE,
    period_end        DATE,
    period_instant    DATE,
    dimensions        JSONB NOT NULL DEFAULT '{}',  -- axis qname -> member qname / typed value
    PRIMARY KEY (accession, context_id)
);

CREATE TABLE xbrl_unit (
    accession   TEXT NOT NULL REFERENCES filing(accession),
    unit_id     TEXT NOT NULL,
    measures    JSONB NOT NULL,  -- {"numerator": [...], "denominator": [...]}
    PRIMARY KEY (accession, unit_id)
);

-- Duplicate facts are preserved by design: no natural uniqueness constraint.
CREATE TABLE raw_fact (
    raw_fact_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    accession       TEXT NOT NULL REFERENCES filing(accession),
    concept_qname   TEXT NOT NULL,
    concept_ns      TEXT NOT NULL,
    is_extension    BOOLEAN NOT NULL,
    context_id      TEXT NOT NULL,
    unit_id         TEXT,
    value_raw       TEXT,
    value_numeric   NUMERIC,
    is_nil          BOOLEAN NOT NULL DEFAULT false,
    decimals_raw    TEXT,           -- as reported: integer string or 'INF'
    precision_raw   TEXT,           -- nullable; retained verbatim when present
    source_document TEXT NOT NULL,
    source_line     INTEGER,
    source_fragment TEXT,
    duplicate_class TEXT,           -- null | consistent_duplicate | inconsistent_duplicate
    FOREIGN KEY (accession, context_id) REFERENCES xbrl_context (accession, context_id)
);

CREATE INDEX raw_fact_accession_concept_idx
    ON raw_fact (accession, concept_qname, context_id);

CREATE TABLE taxonomy_relationship (
    relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    accession       TEXT NOT NULL REFERENCES filing(accession),
    arc_kind        TEXT NOT NULL
        CHECK (arc_kind IN ('presentation', 'calculation', 'definition',
                            'label', 'reference')),
    linkrole        TEXT NOT NULL,
    from_qname      TEXT NOT NULL,
    to_value        TEXT NOT NULL,   -- target qname, label text, or reference parts
    order_index     DOUBLE PRECISION,
    weight          DOUBLE PRECISION,  -- calculation arcs
    preferred_label TEXT,
    arc_metadata    JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX taxonomy_relationship_accession_idx
    ON taxonomy_relationship (accession, arc_kind, linkrole);
