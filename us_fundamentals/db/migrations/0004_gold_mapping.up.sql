-- Gold: versioned mapping rules, canonical observations, comparability (UF-040/044/048 targets).
CREATE TABLE mapping_rule (
    rule_id         TEXT NOT NULL,
    rule_version    INTEGER NOT NULL,
    metric_id       TEXT NOT NULL,
    status          TEXT NOT NULL
        CHECK (status IN ('candidate', 'approved', 'rejected')),
    mapping_version TEXT NOT NULL,   -- release of the compiled rule set
    spec            JSONB NOT NULL,  -- concept, taxonomy versions, forms, period type,
                                     -- units, dimensions, roles, sign, priority, scope
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_by     TEXT,
    approved_at     TIMESTAMPTZ,
    PRIMARY KEY (rule_id, rule_version)
);

CREATE TABLE comparability_event (
    event_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id       TEXT NOT NULL REFERENCES entity(entity_id),
    event_type      TEXT NOT NULL
        CHECK (event_type IN
               ('discontinued_operations', 'reporting_currency', 'fiscal_calendar',
                'standard_adoption', 'segment_reorganization', 'reverse_merger',
                'fresh_start_accounting', 'major_acquisition', 'major_divestiture')),
    effective_period_end DATE NOT NULL,
    first_accession TEXT NOT NULL REFERENCES filing(accession),
    affected_metrics JSONB NOT NULL DEFAULT '[]',
    prior_basis_id  TEXT NOT NULL,
    new_basis_id    TEXT NOT NULL,
    evidence        JSONB NOT NULL DEFAULT '{}',
    confidence      REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    review_status   TEXT NOT NULL DEFAULT 'unreviewed'
);

CREATE TABLE canonical_observation (
    observation_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_version         TEXT NOT NULL,
    accession               TEXT NOT NULL REFERENCES filing(accession),
    entity_id               TEXT NOT NULL REFERENCES entity(entity_id),
    metric_id               TEXT NOT NULL,
    fiscal_period_id        TEXT NOT NULL,
    period_start            DATE,
    period_end              DATE,
    period_instant          DATE,
    value                   NUMERIC NOT NULL,  -- reported value, never altered to balance
    currency                TEXT,
    reported_unit           TEXT NOT NULL,
    derivation_type         TEXT NOT NULL
        CHECK (derivation_type IN
               ('direct', 'aggregated', 'derived_quarter', 'ttm', 'standardized',
                'manual_override', 'imputed')),
    source_concept          TEXT,
    source_context          TEXT,
    source_raw_fact_id      BIGINT REFERENCES raw_fact(raw_fact_id),
    mapping_rule_id         TEXT,
    mapping_rule_version    INTEGER,
    mapping_confidence      REAL CHECK (mapping_confidence BETWEEN 0 AND 1),
    formula_version         TEXT,            -- derived rows only
    qc_status               TEXT NOT NULL DEFAULT 'review'
        CHECK (qc_status IN ('pass', 'pass_with_warning', 'review',
                             'quarantined', 'rejected')),
    information_available_at TIMESTAMPTZ NOT NULL,
    comparability_basis_id  TEXT,
    comparability_status    TEXT,
    FOREIGN KEY (mapping_rule_id, mapping_rule_version)
        REFERENCES mapping_rule (rule_id, rule_version),
    -- Unresolved duplicate canonical versions cannot exist: within one dataset
    -- version, one accession contributes at most one value per metric, fiscal
    -- period, derivation type, and comparability basis. Duplicate *raw* facts
    -- remain in Silver for diagnosis.
    CONSTRAINT canonical_observation_unique
        UNIQUE NULLS NOT DISTINCT
        (dataset_version, accession, metric_id, fiscal_period_id,
         derivation_type, comparability_basis_id)
);

CREATE INDEX canonical_obs_pit_idx
    ON canonical_observation
    (metric_id, entity_id, information_available_at, period_end);
