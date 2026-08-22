// Search-ranking smoke test — replicates index.html logic against real data
const d = require('../../data/recalls.json');
const recs = d.recalls;
const hay = recs.map(r => ({
  hay: [r.product.brand_name, r.product.product_name, r.hazard_details,
        r.consumer_action.instructions, r.alert_id,
        (r.product.upc_codes||[]).join(' '), (r.product.lot_codes||[]).join(' ')]
       .join(' ').toLowerCase(),
  upc: new Set((r.product.upc_codes||[]).map(u=>u.replace(/\D/g,''))),
  r
}));
function search(q){
  const qq = q.trim().toLowerCase();
  const upcQ = /^\d{8,14}$/.test(qq.replace(/\D/g,'')) ? qq.replace(/\D/g,'') : null;
  const out = [];
  for(const h of hay){
    let s = 0;
    if(upcQ){ for(const u of h.upc) if(u===upcQ) s+=1000; if(s){out.push([s,h.r]);continue;} }
    if(!qq){ out.push([1,h.r]); continue; }
    if(h.hay.includes(qq)) s += 100;
    if((h.r.product.brand_name||'').toLowerCase().startsWith(qq)) s += 50;
    if(s) out.push([s,h.r]);
  }
  out.sort((a,b)=>b[0]-a[0] || (b[1].published_at||'').localeCompare(a[1].published_at||''));
  return out;
}
const upc = recs.find(r=>r.product.upc_codes.length)?.product.upc_codes[0].replace(/\D/g,'');
const byUPC = search(upc);
console.log('UPC "'+upc+'" ->', byUPC.length, 'hit(s); top:', byUPC[0]?.[1].alert_id, 'score', byUPC[0]?.[0]);
const byLis = search('listeria');
console.log('"listeria" ->', byLis.length, 'hit(s); top:', byLis[0]?.[1].alert_id, byLis[0]?.[1].hazard_type);
const byCheese = search('cheese');
console.log('"cheese" ->', byCheese.length, 'hit(s); top:', byCheese[0]?.[1].product.product_name?.slice(0,50));
const t0 = Date.now(); search('a');
console.log('single-char scan:', Date.now()-t0, 'ms for', recs.length, 'records');
const all = search('');
console.log('empty query ->', all.length, 'recalls (newest first:', all[0]?.[1].published_at, ')');
