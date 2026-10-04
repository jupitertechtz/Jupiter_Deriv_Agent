DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jupiter Deriv Agent</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎲</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#F3F5F8; --sheet:#FFFFFF; --ink:#18213A; --muted:#5B6479; --rule:#D5DBE5;
  --fair:#3355E0; --win:#12866B; --loss:#B8322E; --bar:#9AA6BF;
  font-family:"Schibsted Grotesk",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-variant-numeric:tabular-nums; color:var(--ink); background:var(--paper);
}
*{box-sizing:border-box}
body{margin:0;line-height:1.5}
main{max-width:920px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:2.6rem;line-height:1.05;font-weight:800;letter-spacing:-.02em;margin:0 0 10px}
h2{font-size:1.35rem;font-weight:700;margin:0 0 4px}
p{margin:0 0 12px;max-width:68ch}
.lede{font-size:1.1rem;color:var(--muted)}
.status{display:flex;flex-wrap:wrap;gap:8px 20px;margin:18px 0 0;font-size:.95rem}
.status b{font-weight:700}
section{background:var(--sheet);border:1px solid var(--rule);border-radius:6px;padding:24px;margin-top:22px}
.hint{color:var(--muted);font-size:.95rem}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:end;margin:14px 0}
label{display:flex;flex-direction:column;gap:4px;font-size:.88rem;color:var(--muted)}
input,select{font:inherit;color:var(--ink);padding:8px 10px;border:1px solid var(--rule);border-radius:4px;background:#fff;min-width:110px}
button{font:inherit;font-weight:700;padding:9px 16px;border-radius:4px;border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer}
button.ghost{background:#fff;color:var(--ink)}
button:disabled{opacity:.5;cursor:wait}
:focus-visible{outline:3px solid var(--fair);outline-offset:2px}
.msg{font-size:.95rem;margin-top:10px}
.msg.err{color:var(--loss)}
/* the digit strips: ten bars against the 10% fair line */
.markets{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:18px;margin-top:16px}
.mkt h3{font-size:1rem;margin:0;display:flex;justify-content:space-between;gap:8px}
.mkt h3 span{font-weight:400;color:var(--muted);font-size:.88rem}
.strip{position:relative;height:96px;display:grid;grid-template-columns:repeat(10,1fr);gap:3px;align-items:end;margin-top:8px;border-bottom:1px solid var(--rule)}
.strip .b{background:var(--bar);border-radius:2px 2px 0 0}
.strip .fair{position:absolute;left:0;right:0;border-top:2px solid var(--fair)}
.digits{display:grid;grid-template-columns:repeat(10,1fr);gap:3px;font-size:.75rem;color:var(--muted);text-align:center;margin-top:3px}
.mkt.flag .b{background:var(--loss)}
.verdict{margin-top:16px;padding-left:12px;border-left:3px solid var(--fair)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;margin-top:12px;font-size:.95rem}
th,td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--rule);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{font-weight:500;color:var(--muted)}
.pos{color:var(--win)} .neg{color:var(--loss)}
.figures{display:flex;flex-wrap:wrap;gap:8px 28px;margin-top:12px}
.figures div{display:flex;flex-direction:column}
.figures b{font-size:1.4rem}
.figures span{font-size:.85rem;color:var(--muted)}
@media (max-width:560px){h1{font-size:2rem}section{padding:18px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<main>
  <header>
    <h1>Jupiter Deriv Agent</h1>
    <p class="lede">Digit statistics, backtests and capped $0.50 Matches sessions for Deriv volatility indices. Every digit should land 10% of the time; the blue line marks that.</p>
    <div class="status" id="status">Checking server setup…</div>
  </header>

  <section aria-labelledby="h-markets">
    <h2 id="h-markets">Markets</h2>
    <p class="hint">Last-digit share per market. Red marks a market whose imbalance passes the corrected significance test; expect none, and re-check any that appear.</p>
    <div class="row">
      <label>Ticks per market<select id="an-ticks"><option>1000</option><option selected>2000</option><option>5000</option></select></label>
      <button id="an-run">Analyze markets</button>
    </div>
    <div id="an-out"></div>
  </section>

  <section aria-labelledby="h-bt">
    <h2 id="h-bt">Backtest</h2>
    <p class="hint">Replays recent ticks against each strategy at Deriv's current payout. Any strategy should be judged against the random baseline.</p>
    <div class="row">
      <label>Market<select id="bt-symbol"></select></label>
      <label>Ticks<select id="bt-ticks"><option>5000</option><option selected>10000</option><option>20000</option></select></label>
      <button id="bt-run">Run backtest</button>
    </div>
    <div id="bt-out"></div>
  </section>

  <section aria-labelledby="h-session">
    <h2 id="h-session">Trading session</h2>
    <p class="hint">Places up to the per-run limit of fixed-stake demo trades, then stops. Daily loss and trade caps are checked against your Deriv history before every trade.</p>
    <div class="row">
      <label>Session key<input id="key" type="password" autocomplete="off" placeholder="SESSION_KEY"></label>
      <label>Market<select id="ss-symbol"></select></label>
      <label>Trades this run<input id="ss-max" type="number" min="1" max="50" value="10"></label>
      <button id="ss-run">Start session</button>
      <button id="rs-run" class="ghost">Load results</button>
    </div>
    <div id="ss-out"></div>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
const pct = x => (x*100).toFixed(1) + '%';
const money = x => (x>0?'+':'') + x.toFixed(2);
const cls = x => x>0 ? 'pos' : x<0 ? 'neg' : '';
function el(tag, attrs={}, text){ const e=document.createElement(tag); Object.assign(e, attrs); if(text!==undefined) e.textContent=text; return e; }
function message(box, text, err){ box.replaceChildren(el('p',{className:'msg'+(err?' err':'')}, text)); }
try { $('key').value = sessionStorage.getItem('jda-key') || ''; } catch(e){}

async function api(path, opts={}){
  const key = $('key').value.trim();
  try { sessionStorage.setItem('jda-key', key); } catch(e){}
  const r = await fetch(path, {...opts, headers:{'Content-Type':'application/json','X-Session-Key':key, ...(opts.headers||{})}});
  const data = await r.json().catch(()=>({detail:'The server returned an unreadable response ('+r.status+').'}));
  if(!r.ok) throw new Error(typeof data.detail==='string' ? data.detail : 'Request failed ('+r.status+').');
  return data;
}
async function busy(btn, fn){ btn.disabled=true; const t=btn.textContent; btn.textContent='Working…'; try{ await fn(); } finally { btn.disabled=false; btn.textContent=t; } }

function table(headers, rows){
  const t=el('table'); const tr=el('tr'); headers.forEach(h=>tr.append(el('th',{},h))); t.append(el('thead')).append(tr);
  const tb=el('tbody'); rows.forEach(r=>{ const row=el('tr'); r.forEach(c=>{ const td=el('td',{},c.text??c); if(c.cls) td.className=c.cls; row.append(td); }); tb.append(row); }); t.append(tb);
  const wrap=el('div',{className:'scroll'}); wrap.append(t); return wrap;
}
function figures(items){ const f=el('div',{className:'figures'}); items.forEach(([v,l,c])=>{ const d=el('div'); const b=el('b',{},v); if(c) b.className=c; d.append(b, el('span',{},l)); f.append(d); }); return f; }

(async function init(){
  try{
    const h = await api('/api/health');
    for (const id of ['bt-symbol','ss-symbol']) h.all_symbols.forEach(s => $(id).append(el('option',{value:s, selected: s===h.symbols[0]}, s)));
    $('ss-max').value = h.limits.trades_per_run;
    const st=$('status'); st.replaceChildren();
    const item=(label,val)=>{ const s=el('span'); s.append(el('b',{},label+': '), document.createTextNode(val)); st.append(s); };
    item('Deriv token', h.token_configured ? 'set' : 'not set');
    item('Session key', h.session_key_configured ? 'set' : 'not set');
    item('Strategy', h.strategy);
    item('Stake', '$'+h.stake.toFixed(2));
    item('Daily loss cap', '$'+h.limits.max_daily_loss.toFixed(2));
  }catch(e){ $('status').textContent = e.message; }
})();

$('an-run').onclick = e => busy(e.target, async ()=>{
  const out=$('an-out'); message(out,'Fetching tick history for 10 markets…');
  try{
    const d = await api('/api/analyze?ticks='+$('an-ticks').value);
    const grid=el('div',{className:'markets'});
    const max = Math.max(0.14, ...d.markets.flatMap(m=>m.frequencies));
    d.markets.forEach(m=>{
      const card=el('div',{className:'mkt'+(m.flagged?' flag':'')});
      const h=el('h3',{},m.symbol); h.append(el('span',{}, 'p = '+(m.p_value==null?'n/a':m.p_value.toFixed(3)))); card.append(h);
      const strip=el('div',{className:'strip', role:'img', ariaLabel: m.symbol+' digit shares: '+m.frequencies.map((f,i)=>i+' '+pct(f)).join(', ')});
      m.frequencies.forEach(f=>strip.append(el('div',{className:'b', style:'height:'+(f/max*100)+'%', title:pct(f)})));
      strip.append(el('div',{className:'fair', style:'bottom:'+(0.1/max*100)+'%'}));
      const digits=el('div',{className:'digits'}); for(let i=0;i<10;i++) digits.append(el('span',{},i));
      card.append(strip, digits); grid.append(card);
    });
    const flagged = d.markets.filter(m=>m.flagged).map(m=>m.symbol);
    const v=el('p',{className:'verdict'}, (flagged.length ? 'Uneven beyond chance: '+flagged.join(', ')+'. Re-run with fresh ticks before trusting it.' : 'All markets look uniform: no digit is favoured beyond what chance produces.') + ' Testing '+d.markets.length+' markets gives a '+Math.round(d.chance_of_false_alarm*100)+'% chance of at least one false alarm at p < 0.05, so the threshold here is p < '+d.threshold.toFixed(4)+'.');
    out.replaceChildren(grid, v);
  }catch(err){ message(out, err.message, true); }
});

$('bt-run').onclick = e => busy(e.target, async ()=>{
  const out=$('bt-out'); message(out,'Replaying ticks…');
  try{
    const d = await api('/api/backtest?symbol='+$('bt-symbol').value+'&ticks='+$('bt-ticks').value);
    const rows = d.results.map(r=>[r.strategy, r.trades, r.wins, pct(r.win_rate), {text:money(r.pnl), cls:cls(r.pnl)}, r.luck_p.toFixed(3)]);
    out.replaceChildren(
      el('p',{className:'msg'}, d.symbol+': '+d.ticks+' ticks. A $'+d.stake.toFixed(2)+' stake pays $'+d.payout.toFixed(2)+', so breaking even needs '+pct(d.breakeven_rate)+' wins; chance gives 10.0%.'),
      table(['Strategy','Trades','Wins','Win rate','P&L ($)','Luck p'], rows),
      el('p',{className:'hint', style:'margin-top:10px'}, '"Luck p" is the chance of winning at least this often by guessing. Small values on one run are expected now and then.'));
  }catch(err){ message(out, err.message, true); }
});

function showResults(out, d){
  const s=d.stats, nodes=[];
  nodes.push(el('p',{className:'msg'}, (d.account.is_virtual?'Demo':'Real')+' account '+d.account.loginid+'. Balance '+d.account.balance.toFixed(2)+' '+(d.account.currency||'')+'.'));
  if(!s.trades){ nodes.push(el('p',{className:'hint'},'No settled Matches trades yet. Start a session to place the first ones.')); out.replaceChildren(...nodes); return; }
  nodes.push(figures([[String(s.trades),'trades'],[pct(s.win_rate),'win rate'],[pct(s.breakeven_rate),'needed to break even'],[money(s.pnl),'net P&L ($)',cls(s.pnl)],[money(d.today.pnl),'today ($)',cls(d.today.pnl)]]));
  nodes.push(el('p',{className:'verdict'}, s.verdict+' (luck p = '+s.luck_p.toFixed(3)+')'));
  nodes.push(table(['Time (UTC)','Market','Digit','Stake','P&L ($)'], d.recent.slice(0,20).map(r=>[new Date(r.purchase_time*1000).toISOString().slice(5,19).replace('T',' '), r.symbol, r.predicted, r.stake.toFixed(2), {text:money(r.profit), cls:cls(r.profit)}])));
  out.replaceChildren(...nodes);
}

$('ss-run').onclick = e => busy(e.target, async ()=>{
  const out=$('ss-out'); message(out,'Trading. This takes up to a minute…');
  try{
    const d = await api('/api/session',{method:'POST', body:JSON.stringify({symbol:$('ss-symbol').value, max_trades:+$('ss-max').value})});
    const nodes=[el('p',{className:'msg'}, (d.account.is_virtual?'Demo':'Real')+' account '+d.account.loginid+'. Stopped because: '+d.stop_reason+'.')];
    nodes.push(figures([[String(d.run.trades),'trades this run'],[String(d.run.wins),'won'],[money(d.run.pnl),'this run ($)',cls(d.run.pnl)],[money(d.today.pnl),'today ($), cap -'+d.today.daily_loss_cap.toFixed(2),cls(d.today.pnl)],[d.account.balance.toFixed(2),'balance']]));
    if(d.trades.length) nodes.push(table(['Contract','Market','Bet','Exit','Result','P&L ($)'], d.trades.map(t=>[String(t.contract_id), t.symbol, t.predicted, t.exit_digit??'–', t.status, {text:money(t.profit), cls:cls(t.profit)}])));
    d.errors.forEach(x=>nodes.push(el('p',{className:'msg err'}, x)));
    out.replaceChildren(...nodes);
  }catch(err){ message(out, err.message, true); }
});

$('rs-run').onclick = e => busy(e.target, async ()=>{
  const out=$('ss-out'); message(out,'Loading your Matches history from Deriv…');
  try{ showResults(out, await api('/api/results')); }catch(err){ message(out, err.message, true); }
});
</script>
</body>
</html>
"""
