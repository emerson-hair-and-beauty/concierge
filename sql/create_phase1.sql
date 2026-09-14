-- Apply once through a privileged database connection before enabling Phase 1.
BEGIN;

CREATE TABLE IF NOT EXISTS plans (
    plan_id UUID PRIMARY KEY,
    submission_id UUID NOT NULL UNIQUE,
    quiz_id UUID,
    anonymous_user_id TEXT NOT NULL,
    email TEXT NOT NULL,
    marketing_consent BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ready','failed')),
    is_mock BOOLEAN NOT NULL DEFAULT FALSE,
    plan_json JSONB,
    diagnostics JSONB NOT NULL DEFAULT '{}',
    failure_code TEXT,
    prompt_version TEXT NOT NULL DEFAULT 'phase1-v1',
    ruleset_version TEXT NOT NULL DEFAULT 'decision-state-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    CHECK ((status = 'ready') = (plan_json IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS plans_pending ON plans(created_at) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS plan_concern_codes (code TEXT PRIMARY KEY,label TEXT NOT NULL);
INSERT INTO plan_concern_codes(code,label) VALUES
    ('absorption_blocked','Blocked absorption'),('hold_loss','Loss of hold'),
    ('breakage_active','Active breakage'),('buildup_present','Product buildup'),
    ('coated_feel','Coated feel'),('scalp_sensitivity','Scalp sensitivity') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS plan_detection_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES plans(plan_id),
    user_id TEXT NOT NULL,
    concern_code TEXT REFERENCES plan_concern_codes(code),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS catalog (
    sku TEXT PRIMARY KEY,
    shopify_id TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    handle TEXT NOT NULL,
    title TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    currency TEXT NOT NULL,
    available BOOLEAN NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL,
    source_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_syncs (
    sync_id UUID PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    fingerprint TEXT NOT NULL,
    result JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS journey_events (
    id UUID PRIMARY KEY,
    quiz_id UUID,
    plan_id UUID REFERENCES plans(plan_id),
    name TEXT NOT NULL CHECK (name IN (
      'quiz_started','quiz_step_viewed','quiz_step_answered','quiz_submitted',
      'plan_viewed','plan_step_expanded','product_clicked','whatsapp_requested',
      'feedback_submitted','plan_exited','product_added_to_cart','checkout_completed')),
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    props JSONB NOT NULL DEFAULT '{}',
    CHECK (quiz_id IS NOT NULL OR plan_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS journey_quiz ON journey_events(quiz_id,occurred_at);
CREATE INDEX IF NOT EXISTS journey_plan ON journey_events(plan_id,occurred_at);
CREATE INDEX IF NOT EXISTS journey_name ON journey_events(name,occurred_at);

CREATE TABLE IF NOT EXISTS plan_feedback (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES plans(plan_id),
    rating TEXT NOT NULL CHECK (rating IN ('very_closely','somewhat','not_quite','not_sure')),
    rejected_shopify_ids JSONB NOT NULL DEFAULT '[]',
    unclear_step TEXT,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS feedback_plan ON plan_feedback(plan_id,created_at DESC,id DESC);

CREATE TABLE IF NOT EXISTS plan_email_outbox (
    plan_id UUID PRIMARY KEY REFERENCES plans(plan_id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sending','sent','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    lease_until TIMESTAMPTZ,
    claim_id UUID,
    last_error TEXT,
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS email_pending ON plan_email_outbox(next_attempt_at) WHERE status <> 'sent';

CREATE TABLE IF NOT EXISTS plan_orders (
    order_id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL,
    attribution JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION phase1_freeze_plan() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    IF OLD.status <> 'pending' AND
       (NEW.status IS DISTINCT FROM OLD.status OR NEW.plan_json IS DISTINCT FROM OLD.plan_json) THEN
        RAISE EXCEPTION 'Terminal plans are immutable';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS phase1_freeze ON plans;
CREATE TRIGGER phase1_freeze BEFORE UPDATE ON plans FOR EACH ROW EXECUTE FUNCTION phase1_freeze_plan();

CREATE OR REPLACE FUNCTION phase1_finish_plan(p_plan_id UUID, p_plan JSONB, p_diagnostics JSONB)
RETURNS BOOLEAN LANGUAGE plpgsql SET search_path = public AS $$
DECLARE completed plans;
BEGIN
    UPDATE plans SET status='ready', plan_json=p_plan, diagnostics=p_diagnostics,
        completed_at=clock_timestamp()
    WHERE plan_id=p_plan_id AND status='pending'
        AND created_at > clock_timestamp() - interval '30 seconds'
    RETURNING * INTO completed;
    IF NOT FOUND THEN RETURN FALSE; END IF;
    INSERT INTO plan_detection_events(plan_id,user_id,concern_code)
    SELECT completed.plan_id,completed.anonymous_user_id,concern->>'code'
    FROM jsonb_array_elements(p_plan->'concerns') concern;
    IF NOT FOUND THEN
        INSERT INTO plan_detection_events(plan_id,user_id,concern_code)
        VALUES(completed.plan_id,completed.anonymous_user_id,NULL);
    END IF;
    IF NOT completed.is_mock THEN
        INSERT INTO plan_email_outbox(plan_id) VALUES(p_plan_id) ON CONFLICT DO NOTHING;
    END IF;
    RETURN TRUE;
END $$;

CREATE OR REPLACE FUNCTION phase1_sweep_plans() RETURNS INTEGER
LANGUAGE plpgsql SET search_path = public AS $$
DECLARE affected INTEGER;
BEGIN
    UPDATE plans SET status='failed', failure_code='worker_lost_or_deadline', completed_at=clock_timestamp()
    WHERE status='pending' AND created_at <= clock_timestamp() - interval '35 seconds';
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END $$;

CREATE OR REPLACE FUNCTION phase1_ingest_catalog(p_batch JSONB) RETURNS JSONB
LANGUAGE plpgsql SET search_path = public AS $$
DECLARE
    previous catalog_syncs;
    stamp TIMESTAMPTZ := (p_batch->>'generated_at')::timestamptz;
    total INTEGER;
    matched INTEGER;
    count_in INTEGER := jsonb_array_length(p_batch->'products');
    result JSONB;
BEGIN
    -- Serialize refreshes so overlap and freshness checks cover the same snapshot.
    PERFORM pg_advisory_xact_lock(614092026);
    SELECT * INTO previous FROM catalog_syncs WHERE sync_id=(p_batch->>'sync_id')::uuid;
    IF FOUND THEN
        IF previous.fingerprint <> md5(p_batch::text) THEN RAISE EXCEPTION 'Sync ID reused with different data'; END IF;
        RETURN previous.result;
    END IF;
    IF stamp > clock_timestamp() + interval '5 minutes' OR
       stamp < clock_timestamp() - interval '24 hours' THEN
        RAISE EXCEPTION 'Refresh timestamp outside permitted window';
    END IF;
    IF EXISTS (SELECT 1 FROM catalog_syncs WHERE generated_at >= stamp) THEN
        RAISE EXCEPTION 'Out of order refresh';
    END IF;
    IF count_in < 1 OR count_in > 2000 THEN RAISE EXCEPTION 'Invalid catalog size'; END IF;
    SELECT count(*) INTO total FROM catalog;
    SELECT count(*) INTO matched FROM catalog c
        JOIN jsonb_array_elements(p_batch->'products') p ON c.sku=p->>'sku';
    IF p_batch->>'mode'='full' AND matched*2 < total THEN
        RAISE EXCEPTION 'Refresh matches fewer than half the existing SKUs';
    END IF;
    IF p_batch->>'mode'='full' THEN
        UPDATE catalog SET available=FALSE WHERE sku NOT IN
            (SELECT p->>'sku' FROM jsonb_array_elements(p_batch->'products') p);
    END IF;
    INSERT INTO catalog(sku,shopify_id,variant_id,handle,title,price,currency,available,synced_at,source_at)
    SELECT p->>'sku',p->>'shopify_id',p->>'variant_id',p->>'handle',p->>'title',
        (p->>'price')::numeric,p->>'currency',(p->>'available')::boolean,clock_timestamp(),stamp
    FROM jsonb_array_elements(p_batch->'products') p
    ON CONFLICT(sku) DO UPDATE SET shopify_id=excluded.shopify_id,variant_id=excluded.variant_id,
        handle=excluded.handle,title=excluded.title,price=excluded.price,currency=excluded.currency,
        available=excluded.available,synced_at=excluded.synced_at,source_at=excluded.source_at;
    result := jsonb_build_object('sync_id',p_batch->>'sync_id','accepted',count_in,'matched_existing',matched,
        'unmatched_matrix_skus',COALESCE(p_batch->'unmatched_matrix_skus','[]'::jsonb));
    INSERT INTO catalog_syncs(sync_id,generated_at,fingerprint,result)
        VALUES((p_batch->>'sync_id')::uuid,stamp,md5(p_batch::text),result);
    RETURN result;
END $$;

CREATE OR REPLACE FUNCTION phase1_claim_email() RETURNS JSONB
LANGUAGE plpgsql SET search_path = public AS $$
DECLARE job plan_email_outbox; recipient plans;
BEGIN
    UPDATE plan_email_outbox SET status='failed',last_error='delivery_lease_expired'
    WHERE status='sending' AND lease_until < clock_timestamp() AND attempts >= 5;
    SELECT * INTO job FROM plan_email_outbox
    WHERE ((status='pending' AND next_attempt_at <= clock_timestamp()) OR
           (status='sending' AND lease_until < clock_timestamp())) AND attempts < 5
    ORDER BY next_attempt_at FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN NULL; END IF;
    UPDATE plan_email_outbox SET status='sending', attempts=attempts+1,
        lease_until=clock_timestamp()+interval '60 seconds',claim_id=gen_random_uuid()
        WHERE plan_id=job.plan_id RETURNING * INTO job;
    SELECT * INTO recipient FROM plans WHERE plan_id=job.plan_id AND status='ready';
    RETURN jsonb_build_object('plan_id',job.plan_id,'claim_id',job.claim_id,'attempts',job.attempts,
        'email',recipient.email,'marketing_consent',recipient.marketing_consent);
END $$;

CREATE OR REPLACE FUNCTION phase1_email_result(p_plan_id UUID,p_claim_id UUID,p_error TEXT)
RETURNS VOID LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    UPDATE plan_email_outbox SET
        status=CASE WHEN p_error IS NULL THEN 'sent' WHEN attempts >= 5 THEN 'failed' ELSE 'pending' END,
        sent_at=CASE WHEN p_error IS NULL THEN clock_timestamp() ELSE NULL END,
        next_attempt_at=clock_timestamp()+interval '30 seconds' * power(2,attempts-1),
        last_error=p_error,lease_until=NULL
    WHERE plan_id=p_plan_id AND claim_id=p_claim_id AND status='sending';
END $$;

-- No direct browser access. All writes and reads use the backend service role.
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_syncs ENABLE ROW LEVEL SECURITY;
ALTER TABLE journey_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_email_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_concern_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_detection_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON plan_concern_codes,plan_detection_events FROM anon,authenticated;
GRANT ALL ON plan_concern_codes,plan_detection_events TO service_role;
GRANT USAGE,SELECT ON SEQUENCE plan_detection_events_id_seq TO service_role;
REVOKE ALL ON plans,catalog,catalog_syncs,journey_events,plan_feedback,plan_email_outbox,plan_orders FROM anon,authenticated;
GRANT ALL ON plans,catalog,catalog_syncs,journey_events,plan_feedback,plan_email_outbox,plan_orders TO service_role;
GRANT USAGE,SELECT ON SEQUENCE plan_feedback_id_seq TO service_role;
REVOKE ALL ON FUNCTION phase1_finish_plan(UUID,JSONB,JSONB),phase1_sweep_plans(),
    phase1_ingest_catalog(JSONB),phase1_claim_email(),phase1_email_result(UUID,UUID,TEXT),phase1_freeze_plan() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION phase1_finish_plan(UUID,JSONB,JSONB),phase1_sweep_plans(),
    phase1_ingest_catalog(JSONB),phase1_claim_email(),phase1_email_result(UUID,UUID,TEXT) TO service_role;

CREATE OR REPLACE VIEW phase1_latest_feedback WITH (security_invoker=true) AS
SELECT DISTINCT ON(plan_id) * FROM plan_feedback ORDER BY plan_id,created_at DESC,id DESC;

CREATE OR REPLACE VIEW phase1_quiz_funnel WITH (security_invoker=true) AS
WITH sessions AS (
    SELECT quiz_id,
        min(occurred_at) FILTER (WHERE name='quiz_started') AS started_at,
        min(occurred_at) FILTER (WHERE name='quiz_submitted') AS submitted_at,
        max((props->>'step_index')::integer) FILTER (WHERE name='quiz_step_viewed') AS deepest_step
    FROM journey_events WHERE quiz_id IS NOT NULL GROUP BY quiz_id
)
SELECT *, started_at IS NOT NULL AND submitted_at IS NULL AND
    started_at < now()-interval '30 minutes' AS abandoned,
    CASE WHEN submitted_at-started_at BETWEEN interval '0 seconds' AND interval '30 minutes'
         THEN extract(epoch FROM submitted_at-started_at) END AS completion_seconds
FROM sessions;

CREATE OR REPLACE VIEW phase1_order_attribution WITH (security_invoker=true) AS
SELECT o.order_id,p.plan_id,r->>'line_id' AS line_id,r->>'shopify_id' AS shopify_id,
    r->>'variant_id' AS variant_id,r->>'quantity' AS quantity,o.received_at
FROM plan_orders o CROSS JOIN LATERAL jsonb_array_elements(o.attribution) r
JOIN plans p ON p.plan_id::text=r->>'plan_id' AND p.status='ready' AND NOT p.is_mock
WHERE r->>'line_id' IS NULL OR EXISTS (
    SELECT 1 FROM jsonb_array_elements(p.plan_json->'steps') s,
        jsonb_array_elements(s->'products') product
    WHERE product->>'shopify_id'=r->>'shopify_id' AND product->>'variant_id'=r->>'variant_id'
);

CREATE OR REPLACE VIEW phase1_plan_summary WITH (security_invoker=true) AS
SELECT created_at::date AS day,source,status,count(*) AS plans,
    count(*) FILTER (WHERE diagnostics::text LIKE '%no_verified_product%') AS plans_with_product_gaps
FROM plans WHERE NOT is_mock GROUP BY created_at::date,source,status;

REVOKE ALL ON phase1_latest_feedback,phase1_quiz_funnel,phase1_order_attribution,phase1_plan_summary FROM anon,authenticated;
GRANT SELECT ON phase1_latest_feedback,phase1_quiz_funnel,phase1_order_attribution,phase1_plan_summary TO service_role;
COMMIT;
