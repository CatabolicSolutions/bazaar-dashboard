from pathlib import Path
p = Path('/var/www/bazaar/dashboard/public/bloc/index.html')
text = p.read_text()

old = "const $=id=>document.getElementById(id),money=n=>n==null?'â':`$${Number(n).toFixed(2)}`,pct=n=>n==null?'â':`${Number(n).toFixed(3)}%`;function kv(o){return Object.entries(o).map(([k,v])=>`<div class=\"kv\"><span>${k}</span><strong>${v}</strong></div>`).join('')}function gauge(label,val,max,color){const p=max>0?Math.max(0,Math.min(100,val/max*100)):0;return `<div style=\"margin-bottom:12px\"><div class=\"kv\"><span>${label}</span><strong>${p.toFixed(1)}%</strong></div><div class=\"gauge\"><div class=\"fill\" style=\"width:${p}%;background:${color}\"></div></div></div>`}"
new = "const $=id=>document.getElementById(id),num=n=>{const v=Number(n);return Number.isFinite(v)?v:null},money=n=>{const v=num(n);return v==null?'--':`$${v.toFixed(2)}`},pct=n=>{const v=num(n);return v==null?'--':`${v.toFixed(3)}%`},pctDiff=(target,current)=>{const t=num(target),c=num(current);return (t==null||c==null||c===0)?null:((t-c)/c*100)};function kv(o){return Object.entries(o).map(([k,v])=>`<div class=\"kv\"><span>${k}</span><strong>${v ?? '--'}</strong></div>`).join('')}function gauge(label,val,max,color){const vv=num(val),mm=num(max);const p=(mm&&mm>0&&vv!=null)?Math.max(0,Math.min(100,vv/mm*100)):0;return `<div style=\"margin-bottom:12px\"><div class=\"kv\"><span>${label}</span><strong>${p.toFixed(1)}%</strong></div><div class=\"gauge\"><div class=\"fill\" style=\"width:${p}%;background:${color}\"></div></div></div>`}"
text = text.replace(old, new)

text = text.replace("$('levels').innerHTML=kv({'Prime buy':money(primeBuy),'Prime sell':money(primeSell),'Preferred reentry':money(pref),'Dist to prime buy':pct(live.distance_to_prime_buy_pct ?? (((primeBuy-live.current_price)/(live.current_price||1))*100)),'Dist to preferred reentry':pct(live.distance_to_preferred_reentry_pct ?? (((pref-live.current_price)/(live.current_price||1))*100)),'Last sell anchor':money(live.last_sell_price),'Extended rollover exit':String(!!live.extended_profit_rollover_exit)});",
                    "$('levels').innerHTML=kv({'Prime buy':money(primeBuy),'Prime sell':money(primeSell),'Preferred reentry':money(pref),'Dist to prime buy':pct(live.distance_to_prime_buy_pct ?? pctDiff(primeBuy, live.current_price)),'Dist to preferred reentry':pct(live.distance_to_preferred_reentry_pct ?? pctDiff(pref, live.current_price)),'Last sell anchor':money(live.last_sell_price),'Extended rollover exit':String(!!live.extended_profit_rollover_exit)});")

text = text.replace("'Entry class':live.entry_class||'—'", "'Entry class':live.entry_class||'--'")
text = text.replace("const holdState=live.hold_state||'hold';const fresh=(live.freshness_age_sec ?? '—');", "const holdState=live.hold_state||'hold';const fresh=(live.freshness_age_sec ?? '--');")

p.write_text(text)
print('ok')
