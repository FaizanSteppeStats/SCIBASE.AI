import json, subprocess, textwrap, tempfile, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).resolve().parents[1]
packet=json.loads((root/'demo/live-search.json').read_text())
selected=packet['items'][0]['id']
for fmt,name in [('csl','references.json'),('ris','references.ris')]:
    run=subprocess.run(['python','citations.py','export','demo/live-search.json','--id',selected,'--format',fmt],cwd=root,text=True,capture_output=True,check=True)
    (root/'demo'/name).write_text(run.stdout)
run=subprocess.run(['python','-m','unittest','discover','-s','tests','-v'],cwd=root,text=True,capture_output=True,check=True)
(root/'demo/test-output.txt').write_text(run.stdout+run.stderr)
frames=Path(tempfile.mkdtemp(prefix='citation-demo-'))
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',23)
heading=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',36)
item=packet['items'][0]
scenes=[('01 / Live literature search',[
 '$ python citations.py search \'TITLE:"malaria"\'', '    --limit 5 --open-access', '    --context "malaria vaccine prevention"', '',
 'Provider: Europe PMC',f'Retrieved: {packet["retrieved_at"]}',f'Returned candidates: {len(packet["items"])}','',
 'Source identifiers:', *[f'  {p["id"]} | {p["title"][:45]}…' for p in packet['items']]]),
 ('02 / Inspect the candidate',[
 f'ID: {item["id"]}',f'Title: {item["title"]}',f'DOI: {item["doi"] or "not supplied"}', f'Source: {item["url"]}',
 f'Matched terms: {", ".join(item["matched_terms"])}',f'Local overlap: {item["context_overlap"]}', '',
 'Warnings:', *[f'  {w}' for w in item['warnings']], '', 'Keyword overlap is not proof that a paper supports a claim.', 'Review the publication before citing it.']),
 ('03 / Export the selected reference',[
 f'$ python citations.py export demo/live-search.json', f'    --id {selected} --format ris', '',
 *[s for s in (root/'demo/references.ris').read_text().splitlines() if not s.startswith('AB  -')][:15]]),
 ('04 / Verified behavior',[
 '$ python -m unittest discover -s tests -v', '', *run.stderr.strip().splitlines()[-4:], '',
 'Covered: request encoding, local context, missing metadata,', 'DOI deduplication, Unicode authors, HTTP retries, size limits,', 'explicit selection and safe RIS record boundaries.', '',
 'CSL JSON and RIS exports generated successfully.', 'Partial contribution to SCIBASE issue #13.', 'Bounty acceptance and payment are not confirmed.'])]
for i,(title,lines) in enumerate(scenes):
    im=Image.new('RGB',(1280,720),'#101826'); d=ImageDraw.Draw(im)
    d.rounded_rectangle((30,30,1250,690),radius=18,fill='#172438')
    d.text((62,56),'SCIBASE / CITATION DISCOVERY',font=font,fill='#67e8c5')
    d.text((62,105),title,font=heading,fill='white')
    y=174
    for line in lines:
        for part in textwrap.wrap(line, width=80, replace_whitespace=False) or ['']:
            d.text((62,y),part,font=font,fill='#d8e4f2');y+=28
    d.text((62,653),'Actual CLI output replay | Search is live; unit fixtures are synthetic',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18),fill='#8da1ba')
    im.save(frames/f'{i:02}.png')
subprocess.run(['ffmpeg','-y','-framerate','1/7','-i',str(frames/'%02d.png'),'-c:v','libx264','-r','24','-pix_fmt','yuv420p','-movflags','+faststart',str(root/'demo/demo.mp4')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print('Created 28-second replay, exports and test transcript.')

shutil.rmtree(frames)
