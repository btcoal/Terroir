-- QC results, dataset releases, review state, run records (UF-050/UF-014/ADR-0005 targets).
CREATE TABLE qc_result (
    qc_result_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope          TEXT NOT NULL
        CHECK (scope IN ('filing', 'raw_fact', 'canonical_observation',
                         'listing', 'dataset')),
    target_ref     TEXT NOT NULL,   -- accession, raw_fact_id, observation_id, ...
    rule_id        TEXT NOT NULL,
    rule_version   TEXT NOT NULL,
    severity       TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'hard')),
    status         TEXT NOT NULL
        CHECK (status IN ('pass', 'pass_with_warning', 'review',
                          'quarantined', 'rejected')),
    observed_inputs JSONB NOT NULL DEFAULT '{}',
    residual       NUMERIC,
    diagnostic     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_by    TEXT,
    resolved_at    TIMESTAMPTZ,
    resolution     TEXT
);

CREATE INDEX qc_result_target_idx ON qc_result (scope, target_ref);

CREATE TABLE review_item (
    review_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind           TEXT NOT NULL,   -- mapping_proposal | source_mismatch | period_ambiguity | ...
    payload        JSONB NOT NULL,
    status         TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'approved', 'rejected', 'modified')),
    decided_by     TEXT,
    decided_at     TIMESTAMPTZ,
    rationale      TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dataset_release (
    dataset_version   TEXT PRIMARY KEY,
    status            TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'published', 'superseded', 'abandoned')),
    manifest          JSONB NOT NULL,  -- accession set ref, raw hashes ref, taxonomy
                                       -- packages, component versions, code commit
    logical_hashes    JSONB NOT NULL DEFAULT '{}',
    parser_version    TEXT NOT NULL,
    mapping_version   TEXT NOT NULL,
    qc_rule_version   TEXT NOT NULL,
    formula_version   TEXT NOT NULL,
    code_commit       TEXT NOT NULL,
    built_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE run_record (
    run_id       TEXT PRIMARY KEY,
    component    TEXT NOT NULL,
    profile      TEXT NOT NULL,
    dataset_version TEXT,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    outcome      TEXT CHECK (outcome IN ('ok', 'failed', 'interrupted')),
    context      JSONB NOT NULL DEFAULT '{}'
);
