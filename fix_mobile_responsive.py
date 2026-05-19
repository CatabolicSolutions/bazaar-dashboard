from pathlib import Path
# Add mobile-responsive CSS to the bloc page
path=Path('/var/www/bazaar/dashboard/public/bloc/index.html')
text=path.read_text()

mobile_css='''@media (max-width:600px){body{font:13px/1.4 Inter,system-ui,sans-serif}.wrap{padding:10px}.hero h1{font-size:20px}.stat .value{font-size:17px}.stats,.chips{gap:6px}.chip{font-size:10px;padding:5px 8px}.panel{border-radius:10px;padding:10px}.controls input{padding:6px;font-size:13px}.kv{padding:5px 0;font-size:12px}.large canvas{height:240px!important}.small canvas{height:160px!important}.btns .btn{font-size:11px;padding:5px 7px}.hero{flex-direction:column;gap:8px}.hero .chips{flex-wrap:wrap;width:100%}.panel h2{font-size:10px}#visualKey.grid{grid-template-columns:repeat(2,1fr)!important}}@media(min-width:601px)and(max-width:900px){body{font-size:13px}.wrap{padding:12px}.hero h1{font-size:24px}.stat .value{font-size:20px}.large canvas{height:320px!important}.small canvas{height:200px!important}}'''

old_mq='@media (max-width:1200px){.top,.bottom,.stats,.controls{grid-template-columns:1fr}.hero{flex-direction:column}}'
new_mq='@media (max-width:1200px){.top,.bottom,.stats{grid-template-columns:1fr}.hero{flex-direction:column}}'+mobile_css
text=text.replace(old_mq,new_mq)

# Fix strategy lab inline column styles for mobile
text=text.replace('style="grid-template-columns:repeat(4,1fr)"><div class="stat"><div class="label">Samples</div>','style="grid-template-columns:repeat(2,1fr)"><div class="stat"><div class="label">Samples</div>')
text=text.replace('style="margin-top:12px;grid-template-columns:repeat(4,1fr)"><div><label>DISTANCE_MIN</label>','style="margin-top:12px;grid-template-columns:repeat(2,1fr)"><div><label>DISTANCE_MIN</label>')
text=text.replace('style="grid-template-columns:repeat(3,1fr);margin-top:12px">','style="grid-template-columns:repeat(2,1fr);margin-top:12px">')

# Fix visual key and bottom grid inline styles
text=text.replace('style="grid-template-columns:repeat(4,minmax(0,1fr));gap:10px">','style="grid-template-columns:repeat(2,minmax(0,1fr));gap:10px">')

path.write_text(text)
print('ok')
