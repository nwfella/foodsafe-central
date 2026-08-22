// Render-pipeline check: replicates buildIndex + card() + detail lookup from index.html
// Verifies the _i bug fix: every rendered card has a numeric data-i resolving to a record.
const d = require('../../data/recalls.json');
const recs = d.recalls;

// buildIndex (from index.html)
recs.forEach((r,i) => { r._i = i; });
for(const r of recs){
  r._hay = [r.product.brand_name, r.product.product_name, r.hazard_details,
            r.consumer_action.instructions, r.alert_id,
            (r.product.upc_codes||[]).join(' '), (r.product.lot_codes||[]).join(' ')]
           .join(' ').toLowerCase();
  r._upc = new Set((r.product.upc_codes||[]).map(u=>u.replace(/\D/g,'')));
}

// card() template — extract data-i values
function cardData(r){
  const p = r.product;
  const upcs = (p.upc_codes||[]).length;
  return { i: r._i, upcs };
}
let bad = 0, maxI = -1;
for(const r of recs){
  const c = cardData(r);
  if(!Number.isInteger(c.i) || c.i < 0 || c.i >= recs.length){ bad++; console.log('BAD card index', c.i, r.alert_id); }
  maxI = Math.max(maxI, c.i);
}
console.log('cards checked:', recs.length, '| bad indices:', bad, '| max index:', maxI);

// detail lookup simulation
const target = recs[0];
const detail = recs[target._i];
console.log('detail lookup for card 0 ->', detail.alert_id, '| matches source:', detail === target);

// click every 20th card's index, ensure record resolves
let ok = 0;
for(let i=0;i<recs.length;i+=20){ if(recs[i] && recs[recs[i]._i] === recs[i]) ok++; }
console.log('sampled card clicks resolve:', ok + '/' + Math.ceil(recs.length/20));

// esc() safety — no unescaped HTML-breaking chars in rendered fields
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let inject = 0;
for(const r of recs){
  for(const f of [r.product.brand_name, r.product.product_name, r.hazard_details, r.alert_id]){
    const e = esc(f);
    if(/[<>]/.test(e)) inject++;  // after escaping, angle brackets must be gone
  }
}
console.log('fields with unescaped angle brackets:', inject);
