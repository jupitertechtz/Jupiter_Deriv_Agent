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
.strip .b.pick{background:var(--fair)}
#auto-run.on{background:var(--ink);color:#fff}
#auto-status{font-weight:500}
.counters{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;justify-content:space-between;margin:6px 0 10px;padding:10px 12px;border:1px solid var(--rule);border-radius:4px}
.counters .hint{margin:0}
.sub{margin-top:20px;padding-top:16px;border-top:1px solid var(--rule)}
.sub h3{font-size:1.05rem;margin:0 0 4px}
input[type=number]{width:130px}
.mode{display:inline-flex;border:1px solid var(--ink);border-radius:4px;overflow:hidden;margin-top:6px}
.mode label{flex-direction:row;align-items:center;gap:0;color:var(--ink);font-size:.95rem}
.mode input{position:absolute;opacity:0;min-width:0;width:1px;height:1px}
.mode span{padding:8px 18px;cursor:pointer;font-weight:700}
.mode input:checked+span{background:var(--ink);color:#fff}
.mode input:focus-visible+span{outline:3px solid var(--fair);outline-offset:-3px}
.mode input:disabled+span{opacity:.45;cursor:not-allowed}
body.live .mode input:checked+span{background:var(--loss)}
body.live #ss-run, body.live #auto-run.on{background:var(--loss);border-color:var(--loss)}
.liveflag{display:none;margin-top:10px;padding:10px 12px;border-left:3px solid var(--loss);color:var(--loss);font-weight:500}
body.live .liveflag{display:block}
.decision{display:inline-block;font-weight:800;letter-spacing:.04em;padding:4px 10px;border-radius:4px;border:2px solid currentColor;margin-right:10px}
.decision.MATCH{color:var(--win)} .decision.WAIT{color:var(--ink)} .decision.SKIP{color:var(--muted)}
.engine-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:14px}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px;margin-top:8px}
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

  <section aria-labelledby="h-engine">
    <h2 id="h-engine">Adaptive Digit Engine</h2>
    <p class="hint">Five models (short-term, long-term, recency-weighted, and 1st/2nd-order transitions) blended with weights that learn from every tick. Each prediction is made before the next digit is known and scored against the 10% baseline. The engine only says MATCH when its walk-forward accuracy beats break-even, could not plausibly be luck, and has held for many consecutive ticks; otherwise WAIT or SKIP.</p>
    <div class="row">
      <label>Market<select id="en-symbol"></select></label>
      <button id="en-run">Analyze market</button>
      <button id="en-scan" class="ghost">Scan all markets</button>
    </div>
    <div id="en-out"></div>
  </section>

  <section aria-labelledby="h-bt">
    <h2 id="h-bt">Backtest</h2>
    <p class="hint">Replays recent ticks against each strategy at Deriv's current payout. "Backtest selected market" tests the market you choose. "Backtest best-payout market" finds the market paying the most right now, tests it, and compares every other market at its own payout. Judge any strategy against the random baseline.</p>
    <div class="row">
      <label>Market<select id="bt-symbol"></select></label>
      <label>Ticks<select id="bt-ticks"><option>5000</option><option selected>10000</option><option>20000</option></select></label>
      <button id="bt-run">Backtest selected market</button>
      <button id="bt-best" class="ghost">Backtest best-payout market</button>
    </div>
    <div id="bt-out"></div>
  </section>

  <section aria-labelledby="h-session">
    <h2 id="h-session">Trading session</h2>
    <p class="hint">Places up to the per-run limit of fixed-stake trades, then stops. Daily loss and trade caps are checked against that account's Deriv history before every trade.</p>
    <div role="radiogroup" aria-label="Account" class="mode">
      <label><input type="radio" name="acct" value="demo" checked><span>Demo</span></label>
      <label><input type="radio" name="acct" value="real" id="acct-real"><span>Live</span></label>
    </div>
    <p class="hint" id="live-hint" style="margin-top:8px"></p>
    <p class="liveflag">Live mode: trades use real money from your Deriv account.</p>
    <div class="row">
      <label>Session key<input id="key" type="password" autocomplete="off" placeholder="SESSION_KEY"></label>
      <label>Market<select id="ss-symbol"></select></label>
      <label>Trades this run<input id="ss-max" type="number" min="1" max="50" value="10"></label>
      <label>Strategy<select id="strategy"></select></label>
      <label>Stake per trade ($)<input id="stake" type="number" min="0.35" max="5" step="0.01" value="0.50"></label>
      <label>Daily loss limit ($)<input id="dloss" type="number" min="0.5" step="0.5" value="5"></label>
      <label>Stop after losses in a row<input id="lrow" type="number" min="1" step="1" value="25"></label>
      <label>Max trades per day<input id="tday" type="number" min="1" step="1" value="100"></label>
      <button id="ss-run">Start session</button>
      <button id="auto-run" class="ghost">Start auto-trading</button>
      <button id="rs-run" class="ghost">Load results</button>
    </div>
    <p class="hint" id="auto-hint">Market "Auto: best payout" re-checks every market&#39;s payout before each trade, trades the highest-paying one, and rotates between markets that tie for the best payout. Every market gives each digit the same 1-in-10 chance; a higher payout only means losing a little less. Auto-trading repeats runs until a limit is hit or you press Stop, and stops if you close this page.</p>
    <div class="counters" aria-live="polite">
      <div id="ctr-text" class="hint">Limit counters: run a session or load results to see them.</div>
      <button id="ctr-reset" class="ghost">Reset counters</button>
    </div>
    <div id="auto-status" class="msg" aria-live="polite"></div>
    <div id="ss-out"></div>

    <div class="sub" aria-labelledby="h-prob">
      <h3 id="h-prob">Match probability</h3>
      <p class="hint">The digit the agent would bet on next for the selected market and stake, with the real odds and Deriv's current payout.</p>
      <div class="row"><button id="pr-run" class="ghost">Check probability</button><button id="po-run" class="ghost">Compare market payouts</button></div>
      <div id="pr-out"></div>
    </div>
  </section>
</main>
<script>
const $ = id => document.getElementById(id);
const pct = x => (x*100).toFixed(1) + '%';
const money = x => (x>0?'+':'') + x.toFixed(2);
const cls = x => x>0 ? 'pos' : x<0 ? 'neg' : '';
const MARKET_NAMES = {R_10:'Volatility 10 Index', R_25:'Volatility 25 Index', R_50:'Volatility 50 Index', R_75:'Volatility 75 Index', R_100:'Volatility 100 Index',
  '1HZ10V':'Volatility 10 (1s) Index', '1HZ25V':'Volatility 25 (1s) Index', '1HZ50V':'Volatility 50 (1s) Index', '1HZ75V':'Volatility 75 (1s) Index', '1HZ100V':'Volatility 100 (1s) Index'};
const mname = s => MARKET_NAMES[s] || s;
const STRAT_NAMES = {adaptive:'Adaptive engine (gated)', adaptive_ungated:'Adaptive engine (no gate)', coldest:'Coldest digit', hottest:'Hottest digit', repeat_last:'Repeat last digit', random:'Random (baseline)'};
const sname = s => STRAT_NAMES[s] || s;
const GATE_NAMES = {uniform:'forecast near uniform', samples:'not enough walk-forward predictions', below_breakeven:'accuracy not above break-even', not_significant:'accuracy could be luck', small_edge:'edge too small', persistence:'evidence not yet persistent', passed:'passed', no_data:'no data'};
const pct2 = x => x==null ? '–' : (x*100).toFixed(2)+'%';
function el(tag, attrs={}, text){ const e=document.createElement(tag); Object.assign(e, attrs); if(text!==undefined) e.textContent=text; return e; }
function message(box, text, err){ box.replaceChildren(el('p',{className:'msg'+(err?' err':'')}, text)); }
try { $('key').value = sessionStorage.getItem('jda-key') || ''; } catch(e){}
const resetKey = () => 'jda-reset-'+account();
function resetTime(){
  let t=null; try{ t=+localStorage.getItem(resetKey())||null; }catch(e){}
  const midnight=Math.floor(Date.UTC(new Date().getUTCFullYear(),new Date().getUTCMonth(),new Date().getUTCDate())/1000);
  return t && t>midnight ? t : null;
}
const utcTime = t => new Date(t*1000).toISOString().slice(11,16)+' UTC';
function showCounters(today, caps){
  if(!today) return;
  const from = resetTime() ? 'since your reset at '+utcTime(resetTime()) : 'since 00:00 UTC';
  const lrCap = caps?.losses_in_row_cap ?? +$('lrow').value, tdCap = caps?.daily_trade_cap ?? +$('tday').value, dlCap = caps?.daily_loss_cap ?? +$('dloss').value;
  $('ctr-text').textContent = (account()==='real'?'Live':'Demo')+' counters '+from+': P&L '+money(today.pnl)+' of -'+Number(dlCap).toFixed(2)+' limit, '+today.trades+' of '+tdCap+' trades, '+(today.losses_in_row??0)+' of '+lrCap+' losses in a row.';
}
function tradeSettings(){
  const st=$('stake'), dl=$('dloss'), stake=+st.value, dloss=+dl.value;
  if(!(stake>=+st.min && stake<=+st.max)) throw new Error('Stake must be between $'+(+st.min).toFixed(2)+' and $'+(+st.max).toFixed(2)+'.');
  if(!(dloss>0 && dloss<=+dl.max)) throw new Error('Daily loss limit must be above $0 and at most $'+(+dl.max).toFixed(2)+'.');
  if(dloss<stake) throw new Error('Daily loss limit is smaller than one stake, so no trade could be placed.');
  const lrow=+$('lrow').value, tday=+$('tday').value;
  if(!(Number.isInteger(lrow) && lrow>=1 && lrow<=+$('lrow').max)) throw new Error('Losses in a row must be a whole number from 1 to '+(+$('lrow').max).toLocaleString()+'.');
  if(!(Number.isInteger(tday) && tday>=1 && tday<=+$('tday').max)) throw new Error('Max trades per day must be a whole number from 1 to '+(+$('tday').max).toLocaleString()+'.');
  return {stake, daily_loss_limit:dloss, max_losses_in_row:lrow, max_trades_per_day:tday, count_since:resetTime(), strategy:$('strategy').value};
}
const account = () => document.querySelector('input[name=acct]:checked').value;
function setMode(v){
  document.querySelector('input[name=acct][value='+v+']').checked = true;
  document.body.classList.toggle('live', v==='real');
  $('ss-run').textContent = v==='real' ? 'Start LIVE session' : 'Start session';
  $('ss-out').replaceChildren();
  $('ctr-text').textContent='Limit counters: run a session or load results to see them.';
}
document.querySelectorAll('input[name=acct]').forEach(r => r.addEventListener('change', e => {
  if (e.target.value==='real' && !confirm('Switch to LIVE trading?\n\nEvery trade will use real money. Matches pays below fair odds, so expect to lose over time. The daily loss cap still applies.')) { setMode('demo'); return; }
  setMode(e.target.value);
}));

async function api(path, opts={}){
  const key = $('key').value.trim();
  try { sessionStorage.setItem('jda-key', key); } catch(e){}
  const r = await fetch(path, {...opts, headers:{'Content-Type':'application/json','X-Session-Key':key, ...(opts.headers||{})}});
  const data = await r.json().catch(()=>({detail:'The server returned an unreadable response ('+r.status+').'}));
  if(!r.ok) throw new Error(typeof data.detail==='string' ? data.detail : 'Request failed ('+r.status+').');
  return data;
}
async function busy(btn, fn){ btn.disabled=true; const t=btn.textContent; btn.textContent='Working…'; try{ await fn(); } finally { btn.disabled=false; btn.textContent = btn.id==='ss-run' ? (account()==='real'?'Start LIVE session':'Start session') : t; } }

function table(headers, rows){
  const t=el('table'); const thead=el('thead'); const tr=el('tr'); headers.forEach(h=>tr.append(el('th',{},h))); thead.append(tr); t.append(thead);
  const tb=el('tbody'); rows.forEach(r=>{ const row=el('tr'); r.forEach(c=>{ const td=el('td',{},c.text??c); if(c.cls) td.className=c.cls; row.append(td); }); tb.append(row); }); t.append(tb);
  const wrap=el('div',{className:'scroll'}); wrap.append(t); return wrap;
}
function figures(items){ const f=el('div',{className:'figures'}); items.forEach(([v,l,c])=>{ const d=el('div'); const b=el('b',{},v); if(c) b.className=c; d.append(b, el('span',{},l)); f.append(d); }); return f; }

(async function init(){
  try{
    const h = await api('/api/health');
    for (const id of ['bt-symbol','ss-symbol']) h.all_symbols.forEach(s => $(id).append(el('option',{value:s, selected: s===h.symbols[0]}, mname(s))));
    $('ss-symbol').prepend(el('option',{value:'auto'}, 'Auto: best payout'));
    h.all_symbols.forEach(x => $('en-symbol').append(el('option',{value:x, selected: x===h.symbols[0]}, mname(x))));
    h.strategies.forEach(x => $('strategy').append(el('option',{value:x}, sname(x))));
    $('ss-max').value = h.limits.trades_per_run;
    window.JDA_STRATEGY = h.strategy;
    const stIn=$('stake'), dlIn=$('dloss'), lrIn=$('lrow'), tdIn=$('tday');
    stIn.min=h.min_stake; stIn.max=h.max_stake; dlIn.max=h.max_daily_loss_ceiling; lrIn.max=h.max_losses_in_row_ceiling; tdIn.max=h.max_trades_per_day_ceiling;
    let saved={}; try{ saved=JSON.parse(localStorage.getItem('jda-settings')||'{}'); }catch(e){}
    stIn.value=Number(saved.stake ?? h.stake).toFixed(2);
    dlIn.value=saved.dloss ?? h.limits.max_daily_loss;
    lrIn.value=saved.lrow ?? h.limits.max_consecutive_losses;
    tdIn.value=saved.tday ?? h.limits.max_trades_per_day;
    $('strategy').value = saved.strategy && h.strategies.includes(saved.strategy) ? saved.strategy : 'adaptive';
    [stIn,dlIn,lrIn,tdIn,$('strategy')].forEach(x=>x.addEventListener('change',()=>{ try{ localStorage.setItem('jda-settings', JSON.stringify({stake:+stIn.value, dloss:+dlIn.value, lrow:+lrIn.value, tday:+tdIn.value, strategy:$('strategy').value})); }catch(e){} }));
    if (!h.live_enabled) { $('acct-real').disabled = true; $('acct-real').dataset.locked='1'; $('live-hint').textContent = 'Live is switched off on the server. To allow it, set LIVE_TRADING_CONFIRM in Vercel (see README) and redeploy.'; }
    else { $('live-hint').textContent = 'Live is allowed on the server. Choose Live to trade with real money.'; }
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
      const h=el('h3',{},mname(m.symbol)); h.append(el('span',{}, 'p = '+(m.p_value==null?'n/a':m.p_value.toFixed(3)))); card.append(h);
      const strip=el('div',{className:'strip', role:'img', ariaLabel: mname(m.symbol)+' digit shares: '+m.frequencies.map((f,i)=>i+' '+pct(f)).join(', ')});
      m.frequencies.forEach(f=>strip.append(el('div',{className:'b', style:'height:'+(f/max*100)+'%', title:pct(f)})));
      strip.append(el('div',{className:'fair', style:'bottom:'+(0.1/max*100)+'%'}));
      const digits=el('div',{className:'digits'}); for(let i=0;i<10;i++) digits.append(el('span',{},i));
      card.append(strip, digits); grid.append(card);
    });
    const flagged = d.markets.filter(m=>m.flagged).map(m=>mname(m.symbol));
    const v=el('p',{className:'verdict'}, (flagged.length ? 'Uneven beyond chance: '+flagged.join(', ')+'. Re-run with fresh ticks before trusting it.' : 'All markets look uniform: no digit is favoured beyond what chance produces.') + ' Testing '+d.markets.length+' markets gives a '+Math.round(d.chance_of_false_alarm*100)+'% chance of at least one false alarm at p < 0.05, so the threshold here is p < '+d.threshold.toFixed(4)+'.');
    out.replaceChildren(grid, v);
  }catch(err){ message(out, err.message, true); }
});

function btStake(){ try{ return '&stake='+tradeSettings().stake; }catch(e){ return ''; } }
function strategyRows(results){ return results.map(r=>[sname(r.strategy), r.trades, r.wins, r.trades? pct(r.win_rate) : 'no trades', {text:money(r.pnl), cls:cls(r.pnl)}, r.trades? r.luck_p.toFixed(3) : '–']); }

function decisionBadge(d){ return el('span',{className:'decision '+d}, d); }
function probStrip(probs, pick){
  const max=Math.max(0.14,...probs);
  const strip=el('div',{className:'strip',role:'img',ariaLabel:'Engine probability per digit, digit '+pick+' highlighted'});
  probs.forEach((x,i)=>strip.append(el('div',{className:'b'+(i===pick?' pick':''),style:'height:'+(x/max*100)+'%',title:i+': '+pct2(x)})));
  strip.append(el('div',{className:'fair',style:'bottom:'+(0.1/max*100)+'%'}));
  const digits=el('div',{className:'digits'}); for(let i=0;i<10;i++) digits.append(el('span',{},i));
  const wrap=el('div',{style:'max-width:420px;margin-top:12px'}); wrap.append(strip,digits); return wrap;
}

$('en-run').onclick = e => busy(e.target, async ()=>{
  const out=$('en-out'); message(out,'Replaying recent ticks through the engine, walk-forward…');
  try{
    const d=await api('/api/engine?symbol='+$('en-symbol').value+btStake());
    const head=el('div',{className:'engine-head'}); head.append(decisionBadge(d.decision), el('span',{}, mname(d.symbol)+': next digit '+d.digit));
    const nodes=[head, el('p',{className:'msg'}, d.reason)];
    nodes.push(figures([
      [pct2(d.p_best),'model probability of digit '+d.digit],[(d.edge>=0?'+':'')+pct2(d.edge),'edge over 10%'],[pct2(d.separation),'lead over 2nd digit'],
      [pct2(d.walk_forward_accuracy),'walk-forward accuracy'],[pct2(d.breakeven),'needed to break even'+(d.breakeven_known?'':' (payout unknown)')],
      [d.luck_p.toFixed(3),'luck p'],[String(d.samples),'walk-forward predictions'],[d.entropy.toFixed(3),'forecast entropy (1 = no idea)'],
      [d.calibration.toFixed(2),'calibration'],[d.score.toFixed(4),'decision score']]));
    nodes.push(probStrip(d.probabilities, d.digit));
    const two=el('div',{className:'two'});
    const ra=d.rolling_accuracy;
    two.append(table(['Window','Accuracy','vs 10%'], ['50','100','500','1000'].map(k=>[k+' predictions', pct2(ra[k]), ra[k]==null?'–':{text:((ra[k]-0.1)*100>=0?'+':'')+((ra[k]-0.1)*100).toFixed(1)+' pts', cls:cls(ra[k]-0.1)}])));
    two.append(table(['Model','Weight'], Object.entries(d.weights).sort((a,b)=>b[1]-a[1]).map(([m,w])=>[m, pct(w)])));
    nodes.push(two);
    nodes.push(el('p',{className:'verdict'}, 'Every prediction above was made before the digit it was scored on. On a fair random market, accuracy stays near 10% and the forecast stays near uniform, so the engine holds back.'));
    out.replaceChildren(...nodes);
  }catch(err){ message(out, err.message, true); }
});

$('en-scan').onclick = e => busy(e.target, async ()=>{
  const out=$('en-out'); message(out,'Running the engine on all ten markets. This can take up to a minute…');
  try{
    const d=await api('/api/engine/scan'+(btStake()?'?'+btStake().slice(1):''));
    const counts={MATCH:0,WAIT:0,SKIP:0}; d.markets.forEach(m=>counts[m.decision]++);
    const nodes=[el('p',{className:'msg'}, d.any_match ? 'Markets passing the evidence gate: '+d.markets.filter(m=>m.decision==='MATCH').map(m=>mname(m.symbol)).join(', ')+'.' : 'No market passes the evidence gate right now ('+counts.WAIT+' WAIT, '+counts.SKIP+' SKIP). The engine would not trade.')];
    nodes.push(table(['Market','Decision','Digit','P(best)','Edge','Forecast entropy','Walk-forward acc.','Break-even','Luck p','Samples','Score','Why'],
      d.markets.map(m=>[mname(m.symbol), m.decision, m.digit, pct2(m.p_best), (m.edge>=0?'+':'')+pct2(m.edge), m.entropy.toFixed(3), pct2(m.walk_forward_accuracy), pct2(m.breakeven), m.luck_p.toFixed(3), m.samples, m.score.toFixed(4), m.reason])));
    out.replaceChildren(...nodes);
  }catch(err){ message(out, err.message, true); }
});

$('bt-best').onclick = e => busy(e.target, async ()=>{
  const out=$('bt-out');
  const ticks=Math.min(+$('bt-ticks').value, 10000);
  message(out,'Checking every market\'s payout and replaying '+ticks.toLocaleString()+' ticks on each. This can take up to a minute…');
  try{
    const d = await api('/api/backtest/best-payout?ticks='+ticks+btStake());
    const best=d.markets.filter(m=>m.best), top=best[0];
    const nodes=[];
    nodes.push(el('p',{className:'msg'}, d.all_equal
      ? 'All '+d.markets.length+' markets pay $'+d.top_payout.toFixed(2)+' on a $'+d.stake.toFixed(2)+' stake, so they tie for the highest payout. Showing '+mname(top.symbol)+' first.'
      : 'Highest payout: '+best.map(m=>mname(m.symbol)).join(', ')+' at $'+d.top_payout.toFixed(2)+' on a $'+d.stake.toFixed(2)+' stake, which needs '+pct(top.breakeven_rate)+' wins to break even. Chance gives 10.0% on every market.'));
    if(ticks < +$('bt-ticks').value) nodes.push(el('p',{className:'hint'},'Limited to 10,000 ticks per market so all ten finish in time.'));
    nodes.push(el('h3',{style:'font-size:1rem;margin:16px 0 0'}, 'Highest-payout market: '+mname(top.symbol)+' ('+top.ticks.toLocaleString()+' ticks)'));
    nodes.push(table(['Strategy','Trades','Wins','Win rate','P&L ($)','Luck p'], strategyRows(top.results)));
    const chosen = $('strategy').value || window.JDA_STRATEGY;
    const strat = top.results.some(r=>r.strategy===chosen) ? chosen : top.results[0].strategy;
    const pick=(m,n)=>m.results.find(r=>r.strategy===n);
    nodes.push(el('h3',{style:'font-size:1rem;margin:18px 0 0'}, 'All markets, best payout first'));
    nodes.push(table(['Market','Payout','Break-even',sname(strat)+' win rate',sname(strat)+' P&L ($)','Random win rate','Random P&L ($)'],
      d.markets.map(m=>{ const a=pick(m,strat), r=pick(m,'random');
        return [mname(m.symbol)+(m.best && !d.all_equal?' (best)':''), '$'+m.payout.toFixed(2), pct(m.breakeven_rate), a.trades? pct(a.win_rate) : 'no trades', {text:money(a.pnl),cls:cls(a.pnl)}, r?pct(r.win_rate):'–', r?{text:money(r.pnl),cls:cls(r.pnl)}:'–']; })));
    if(d.unavailable.length) nodes.push(el('p',{className:'hint',style:'margin-top:8px'}, 'No payout right now for: '+d.unavailable.map(mname).join(', ')+'.'));
    nodes.push(el('p',{className:'verdict'}, 'A higher payout lowers the break-even rate but does not raise the 10% chance of a match. A strategy only has an edge if it beats "random" on several markets and on fresh data. "Adaptive engine (gated)" with no trades means the evidence gate never opened, so it lost nothing.'));
    out.replaceChildren(...nodes);
  }catch(err){ message(out, err.message, true); }
});

$('bt-run').onclick = e => busy(e.target, async ()=>{
  const out=$('bt-out'); message(out,'Replaying ticks…');
  try{
    const d = await api('/api/backtest?symbol='+$('bt-symbol').value+'&ticks='+$('bt-ticks').value+btStake());
    const rows = strategyRows(d.results);
    out.replaceChildren(
      el('p',{className:'msg'}, mname(d.symbol)+': '+d.ticks+' ticks. A $'+d.stake.toFixed(2)+' stake pays $'+d.payout.toFixed(2)+', so breaking even needs '+pct(d.breakeven_rate)+' wins; chance gives 10.0%.'),
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
  nodes.push(table(['Time (UTC)','Market','Digit','Stake','P&L ($)'], d.recent.slice(0,20).map(r=>[new Date(r.purchase_time*1000).toISOString().slice(5,19).replace('T',' '), mname(r.symbol), r.predicted, r.stake.toFixed(2), {text:money(r.profit), cls:cls(r.profit)}])));
  out.replaceChildren(...nodes);
}

function sessionNodes(d){
  if(d.auto_selected && d.symbol) lastAutoSymbol=d.symbol;
  const used=Object.entries(d.markets_used||{});
  const where = d.auto_selected ? (used.length ? 'auto: best payout, traded on '+used.map(([m,n])=>mname(m)+' ('+n+')').join(', ') : 'auto: best payout') : mname(d.symbol);
  const nodes=[el('p',{className:'msg'}, (d.account.is_virtual?'Demo':'Real')+' account '+d.account.loginid+', '+where+'. Stopped because: '+d.stop_reason+'.')];
  nodes.push(figures([['$'+d.stake.toFixed(2),'stake'],[String(d.run.trades),'trades this run'],[String(d.run.wins),'won'],[money(d.run.pnl),'this run ($)',cls(d.run.pnl)],[money(d.today.pnl),'today ($), limit -'+d.today.daily_loss_cap.toFixed(2),cls(d.today.pnl)],[d.account.balance.toFixed(2),'balance']]));
  if(d.trades.length) nodes.push(table(['Contract','Market','Bet','Exit','Result','P&L ($)'], d.trades.map(t=>[String(t.contract_id), mname(t.symbol), t.predicted, t.exit_digit??'–', t.status, {text:money(t.profit), cls:cls(t.profit)}])));
  if(d.engine){
    const sk=Object.entries(d.engine.skipped_because||{}).sort((a,b)=>b[1]-a[1]).map(([g,n])=>GATE_NAMES[g]+' ('+n+')').join(', ');
    nodes.push(el('p',{className:'verdict'}, 'Adaptive engine checked '+d.engine.checks+' times'+(d.run.trades? ' and traded only when a market passed the evidence gate.' : ' and found no market that passed the evidence gate.')+(sk?' Held back because: '+sk+'.':'')));
    nodes.push(table(['Market','Decision','Digit','P(best)','Walk-forward acc.','Break-even','Samples','Why'],
      d.engine.latest.map(r=>[mname(r.symbol), r.decision, r.digit, pct(r.p_best), pct(r.walk_forward_accuracy), pct(r.breakeven), r.samples, r.reason])));
  }
  d.errors.forEach(x=>nodes.push(el('p',{className:'msg err'}, x)));
  return nodes;
}
let lastAutoSymbol=null;
function sessionBody(ts){ return JSON.stringify({symbol:$('ss-symbol').value, max_trades:+$('ss-max').value, account:account(), last_symbol:lastAutoSymbol, ...ts}); }

let autoOn=false, autoTotals=null;
function setAuto(on){
  autoOn=on; const b=$('auto-run'); b.classList.toggle('on',on);
  b.textContent = on ? 'Stop auto-trading' : 'Start auto-trading';
  ['ss-run','rs-run','pr-run','po-run','ss-symbol','strategy','stake','dloss','lrow','tday','ss-max','ctr-reset'].forEach(id=>$(id).disabled=on);
  document.querySelectorAll('input[name=acct]').forEach(r=>r.disabled = on || (r.value==='real' && r.dataset.locked==='1'));
}
$('auto-run').onclick = async ()=>{
  if(autoOn){ autoOn=false; $('auto-status').textContent='Stopping after the current run finishes…'; return; }
  let ts; try{ ts=tradeSettings(); }catch(err){ message($('ss-out'), err.message, true); return; }
  if(account()==='real' && !confirm('Start LIVE auto-trading with real money?\n\nStake $'+ts.stake.toFixed(2)+', daily loss limit $'+ts.daily_loss_limit.toFixed(2)+'. Runs repeat until a limit is hit or you press Stop.')) return;
  autoTotals={runs:0,trades:0,wins:0,pnl:0}; setAuto(true);
  const status=$('auto-status');
  try{
    while(autoOn){
      status.textContent='Auto-trading: run '+(autoTotals.runs+1)+' in progress… ('+autoTotals.trades+' trades, '+money(autoTotals.pnl)+' so far)';
      const d=await api('/api/session',{method:'POST', body:sessionBody(ts)});
      autoTotals.runs++; autoTotals.trades+=d.run.trades; autoTotals.wins+=d.run.wins; autoTotals.pnl=Math.round((autoTotals.pnl+d.run.pnl)*100)/100;
      $('ss-out').replaceChildren(...sessionNodes(d)); showCounters(d.today, d.today);
      if(!d.can_continue || d.run.trades===0){ status.textContent = (d.engine && d.run.trades===0 && d.can_continue) ? 'Auto-trading paused: no market passed the evidence gate during the last run.' : 'Auto-trading stopped: '+d.stop_reason+'.'; autoOn=false; break; }
    }
  }catch(err){ status.textContent='Auto-trading stopped by an error.'; message($('ss-out'), err.message, true); }
  if(status.textContent.startsWith('Stopping') || status.textContent.startsWith('Auto-trading: run')) status.textContent='Auto-trading stopped by you.';
  status.textContent += ' Totals: '+autoTotals.runs+' runs, '+autoTotals.trades+' trades, '+autoTotals.wins+' won, net P&L '+money(autoTotals.pnl)+'.';
  setAuto(false);
};

$('ctr-reset').onclick = e => busy(e.target, async ()=>{
  let cur=null;
  try{ cur=await api('/api/results?account='+account()+(resetTime()?'&since='+resetTime():'')); }catch(err){}
  const t=cur?.today, what = t ? 'Current counters: P&L '+money(t.pnl)+', '+t.trades+' trades, '+t.losses_in_row+' losses in a row.\n\n' : '';
  if(!confirm('Reset the limit counters for the '+(account()==='real'?'LIVE':'demo')+' account?\n\n'+what+'Counting restarts from now, so the daily loss limit, trade limit and losses-in-a-row limit start again from zero. Your Deriv history and results are not changed. Counters also reset automatically at 00:00 UTC.')) return;
  try{ localStorage.setItem(resetKey(), String(Math.floor(Date.now()/1000))); }catch(err){}
  showCounters({pnl:0,trades:0,losses_in_row:0});
});

$('po-run').onclick = e => busy(e.target, async ()=>{
  const out=$('pr-out'); message(out,'Asking Deriv for the payout on every market…');
  try{
    const d=await api('/api/payouts?stake='+tradeSettings().stake);
    const rows=d.markets.map(m=> m.payout ? [mname(m.symbol)+(m.best && !d.all_equal?' (best)':''), '$'+m.payout.toFixed(2), pct(m.breakeven_rate), {text:money(m.expected_per_trade), cls:cls(m.expected_per_trade)}] : [mname(m.symbol),'–','–','unavailable']);
    const note = d.all_equal ? 'Every market pays the same right now, so auto mode rotates through all of them. ' : 'Auto mode trades the best-paying market and rotates between markets tied for best. ';
    out.replaceChildren(el('p',{className:'msg'},'Payouts for a $'+d.stake.toFixed(2)+' Matches bet. '+note+'The chance of a match is 10% on every market.'), table(['Market','Payout','Break-even','Expected per trade ($)'], rows));
  }catch(err){ message(out, err.message, true); }
});

$('ss-run').onclick = e => busy(e.target, async ()=>{
  let ts; try{ ts=tradeSettings(); }catch(err){ message($('ss-out'), err.message, true); return; }
  if (account()==='real' && !confirm('Place up to '+$('ss-max').value+' REAL-money trades of $'+ts.stake.toFixed(2)+' each now? Daily loss limit: $'+ts.daily_loss_limit.toFixed(2)+'.')) return;
  const out=$('ss-out'); message(out,'Trading. This takes up to a minute…'); $('auto-status').textContent='';
  try{ const d=await api('/api/session',{method:'POST', body:sessionBody(ts)}); out.replaceChildren(...sessionNodes(d)); showCounters(d.today, d.today); }
  catch(err){ message(out, err.message, true); }
});

$('pr-run').onclick = e => busy(e.target, async ()=>{
  const out=$('pr-out'); message(out,'Reading recent ticks and the live payout…');
  try{
    const stake=tradeSettings().stake; let sym=$('ss-symbol').value;
    if(sym==='auto'){ const p=await api('/api/payouts?stake='+stake); sym=(p.markets.find(m=>m.payout)||{symbol:'R_100'}).symbol; }
    const d=await api('/api/probability?symbol='+encodeURIComponent(sym)+'&stake='+stake);
    const nodes=[el('p',{className:'msg'}, 'Next bet on '+mname(d.symbol)+': digit '+d.digit+' (strategy "'+d.strategy+'").')];
    const f=[[pct(d.probability),'chance it matches'],[pct(d.recent_frequency),'how often '+d.digit+' came up in the last '+d.ticks+' ticks']];
    if(d.payout){ f.push(['$'+d.payout.toFixed(2),'payout ($'+d.profit_if_win.toFixed(2)+' profit) on $'+d.stake.toFixed(2)],[pct(d.breakeven_rate),'needed to break even'],[money(d.expected_per_trade),'expected per trade ($)',cls(d.expected_per_trade)],[money(d.expected_per_100),'expected per 100 trades ($)',cls(d.expected_per_100)]); }
    nodes.push(figures(f));
    const max=Math.max(0.14,...d.frequencies);
    const strip=el('div',{className:'strip',role:'img',ariaLabel:'Recent digit shares, digit '+d.digit+' highlighted'});
    d.frequencies.forEach((x,i)=>strip.append(el('div',{className:'b'+(i===d.digit?' pick':''),style:'height:'+(x/max*100)+'%',title:i+': '+pct(x)})));
    strip.append(el('div',{className:'fair',style:'bottom:'+(0.1/max*100)+'%'}));
    const digits=el('div',{className:'digits'}); for(let i=0;i<10;i++) digits.append(el('span',{},i));
    const wrap=el('div',{style:'max-width:360px;margin-top:12px'}); wrap.append(strip,digits); nodes.push(wrap);
    nodes.push(el('p',{className:'verdict'}, 'Every tick, each digit has the same 1-in-10 chance, whatever came before. The recent share above is history, not a forecast.'+(d.payout?' At this payout each trade loses about $'+Math.abs(d.expected_per_trade).toFixed(2)+' on average.':' Payout unavailable right now.')));
    out.replaceChildren(...nodes);
  }catch(err){ message(out, err.message, true); }
});

$('rs-run').onclick = e => busy(e.target, async ()=>{
  const out=$('ss-out'); message(out,'Loading your '+(account()==='real'?'live':'demo')+' Matches history from Deriv…');
  try{ const r=await api('/api/results?account='+account()+(resetTime()?'&since='+resetTime():'')); showResults(out, r); showCounters(r.today); }catch(err){ message(out, err.message, true); }
});
</script>
</body>
</html>
"""
