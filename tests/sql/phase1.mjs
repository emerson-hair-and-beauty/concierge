import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';

const db = new PGlite();
let checks = 0;
const check = (actual, expected) => { assert.deepEqual(actual, expected); checks++; };
const scalar = async (sql, params=[]) => Object.values((await db.query(sql, params)).rows[0])[0];
const rejected = async (sql, params=[]) => {
  await assert.rejects(db.query(sql, params)); checks++;
};
try {
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;');
  const migration = await readFile(new URL('../../sql/create_phase1.sql', import.meta.url), 'utf8');
  await db.exec(migration);
  await db.exec(migration); // Rerunning a migration must preserve existing records.
  const id = randomUUID(), submission = randomUUID();
  await db.query('INSERT INTO plans(plan_id,submission_id,anonymous_user_id,email) VALUES($1,$2,$3,$4)',
                 [id, submission, randomUUID(), 'test@example.com']);
  await rejected('INSERT INTO plans(plan_id,submission_id,anonymous_user_id,email) VALUES($1,$2,$3,$4)',
                 [randomUUID(), submission, randomUUID(), 'test@example.com']);
  const snapshot = {plan_id:id,status:'ready',summary:'A plan',steps:[{step:'cleanse',products:[
    {shopify_id:'1',variant_id:'2'}]}]};
  check(await scalar('SELECT phase1_finish_plan($1,$2,$3)', [id,snapshot,[]]), true);
  check(await scalar('SELECT count(*)::int FROM plan_email_outbox'), 1);
  check(await scalar('SELECT count(*)::int FROM plan_detection_events WHERE concern_code IS NULL'), 1);
  check(await scalar('SELECT phase1_finish_plan($1,$2,$3)', [id,{summary:'changed'},[]]), false);
  check(await scalar('SELECT plan_json FROM plans WHERE plan_id=$1', [id]), snapshot);
  await rejected("UPDATE plans SET plan_json='{}' WHERE plan_id=$1", [id]);

  const dead = randomUUID();
  await db.query("INSERT INTO plans(plan_id,submission_id,anonymous_user_id,email,created_at) VALUES($1,$2,'x','test@example.com',clock_timestamp()-interval '36 seconds')",
    [dead, randomUUID()]);
  check(await scalar('SELECT phase1_sweep_plans()'), 1);
  check(await scalar('SELECT status FROM plans WHERE plan_id=$1', [dead]), 'failed');
  check(await scalar('SELECT phase1_finish_plan($1,$2,$3)', [dead,snapshot,[]]), false);
  check(await scalar('SELECT count(*)::int FROM plan_email_outbox'), 1);

  const late = randomUUID();
  await db.query("INSERT INTO plans(plan_id,submission_id,anonymous_user_id,email,created_at) VALUES($1,$2,'x','test@example.com',clock_timestamp()-interval '31 seconds')",
    [late, randomUUID()]);
  check(await scalar('SELECT phase1_finish_plan($1,$2,$3)', [late,snapshot,[]]), false);
  check(await scalar('SELECT status FROM plans WHERE plan_id=$1', [late]), 'pending');

  const item = sku => ({sku,shopify_id:'1',variant_id:'2',handle:'cleanser',title:'Cleanser',price:'10.00',currency:'AED',available:true});
  let stamp = Date.now()-10000;
  const batch = products => ({sync_id:randomUUID(),mode:'full',generated_at:new Date(stamp+=1000).toISOString(),products});
  const first = batch([item('A'),item('B'),item('C')]);
  const result = await scalar('SELECT phase1_ingest_catalog($1)', [first]);
  check(result.accepted, 3);
  check(await scalar('SELECT phase1_ingest_catalog($1)', [first]), result);
  await rejected('SELECT phase1_ingest_catalog($1)', [{...first,products:[item('X')]}]);
  await rejected('SELECT phase1_ingest_catalog($1)', [batch([item('A')])]);
  check(await scalar('SELECT count(*)::int FROM catalog WHERE available'), 3);
  await scalar('SELECT phase1_ingest_catalog($1)', [batch([item('A'),item('B')])]);
  check(await scalar("SELECT available FROM catalog WHERE sku='C'"), false);
  await rejected('SELECT phase1_ingest_catalog($1)', [{...first,sync_id:randomUUID()}]);
  const partial = {...batch([{...item('A'),available:false}]),mode:'partial'};
  await scalar('SELECT phase1_ingest_catalog($1)', [partial]);
  check(await scalar("SELECT available FROM catalog WHERE sku='B'"), true);

  const job = await scalar('SELECT phase1_claim_email()');
  check(job.plan_id,id);
  check(await scalar('SELECT phase1_claim_email()'), null);
  await scalar('SELECT phase1_email_result($1,$2,$3)', [id,randomUUID(),null]);
  check(await scalar('SELECT status FROM plan_email_outbox WHERE plan_id=$1',[id]),'sending');
  await scalar('SELECT phase1_email_result($1,$2,$3)', [id,job.claim_id,'TimeoutError']);
  check(await scalar('SELECT status FROM plan_email_outbox WHERE plan_id=$1',[id]),'pending');
  await db.query("UPDATE plan_email_outbox SET next_attempt_at=now()-interval '1 second' WHERE plan_id=$1",[id]);
  const retry = await scalar('SELECT phase1_claim_email()');
  check(retry.attempts,2);
  await scalar('SELECT phase1_email_result($1,$2,$3)', [id,retry.claim_id,null]);
  check(await scalar('SELECT status FROM plan_email_outbox WHERE plan_id=$1',[id]),'sent');

  const event = randomUUID();
  await db.query("INSERT INTO journey_events(id,plan_id,name,occurred_at) VALUES($1,$2,'plan_viewed',now()) ON CONFLICT DO NOTHING", [event,id]);
  await db.query("INSERT INTO journey_events(id,plan_id,name,occurred_at) VALUES($1,$2,'plan_viewed',now()) ON CONFLICT DO NOTHING", [event,id]);
  check(await scalar('SELECT count(*)::int FROM journey_events'),1);
  await db.query("INSERT INTO plan_feedback(plan_id,rating) VALUES($1,'somewhat'),($1,'very_closely')",[id]);
  check(await scalar('SELECT count(*)::int FROM plan_feedback'),2);
  check(await scalar('SELECT rating FROM phase1_latest_feedback'),'very_closely');

  await db.query('INSERT INTO plan_orders(order_id,webhook_id,attribution) VALUES($1,$2,$3)', ['10','hook',[
    {plan_id:id,line_id:'1',shopify_id:'1',variant_id:'2'},
    {plan_id:id,line_id:'2',shopify_id:'999',variant_id:'999'},
    {plan_id:randomUUID(),line_id:null}]]);
  check(await scalar('SELECT count(*)::int FROM phase1_order_attribution'),1);
  await db.exec('SET ROLE anon');
  await rejected('SELECT * FROM plans');
  await rejected('SELECT * FROM phase1_plan_summary');
  await rejected('SELECT phase1_sweep_plans()');
  await db.exec('RESET ROLE; SET ROLE service_role');
  check(await scalar('SELECT count(*)::int FROM plans'),3);
  console.log(`Phase 1 SQL: ${checks} checks passed (PGlite PostgreSQL).`);
} finally {
  await db.close();
}
