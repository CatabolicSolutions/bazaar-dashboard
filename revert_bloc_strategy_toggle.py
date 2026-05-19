from pathlib import Path
p = Path('/var/www/bazaar/dashboard/public/bloc/index.html')
text = p.read_text()
old = "$(`strategyToggle`).onclick=async()=>{strategyOpen=!strategyOpen;$('strategyLabWrap').style.display=strategyOpen?'block':'none';if(strategyOpen&&!labMarket){await loadLab();}else if(strategyOpen){drawLab();}};"
if old not in text:
    old = "$('strategyToggle').onclick=async()=>{strategyOpen=!strategyOpen;$('strategyLabWrap').style.display=strategyOpen?'block':'none';if(strategyOpen&&!labMarket){await loadLab();}else if(strategyOpen){drawLab();}};"
new = "$('strategyToggle').onclick=async()=>{strategyOpen=!strategyOpen;$('strategyLabWrap').style.display=strategyOpen?'block':'none';};"
text = text.replace(old, new)
p.write_text(text)
print('ok')
