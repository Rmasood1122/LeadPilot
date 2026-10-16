#!/usr/bin/env python3
"""Re-runnable audit of the GEO drafts (Phase 8 gates). Usage: python3 tools/geo_audit.py docs/program/ai-visibility/geo
Prints PASS/FAIL per check; exits 1 if any check fails."""
import re,json,os,glob,datetime,sys
os.chdir(sys.argv[1]); fails=[]
def chk(c,msg): print(('PASS ' if c else 'FAIL ')+msg); (fails.append(msg) if not c else None)
req="""state.md questions.md entity_card.md research/competitor_analysis.md research/query_library.md positioning/niche_statement.md
content/definitions/what_is_leadpilot.md content/definitions/leadpilot_use_cases.md content/faq_library.md content/statistics_and_proof.md content/comparison_matrix.md
technical/schema_markup.md technical/crawler_access_strategy.md technical/site_architecture.md
platforms/chatgpt_bing_playbook.md platforms/gemini_playbook.md platforms/perplexity_playbook.md platforms/claude_playbook.md platforms/emerging_ai_playbook.md
authority/citation_acquisition_plan.md authority/reddit_strategy.md authority/syndication_map.md monitoring/ai_mention_tracker.md monitoring/content_update_calendar.md""".split()
for f in req: chk(os.path.exists(f) and os.path.getsize(f)>500, 'exists '+f)
chk(len(glob.glob('content/comparisons/leadpilot_vs_*.md'))==5,'5 comparison pages')
r=lambda p:open(p).read()
# counts
ql=r('research/query_library.md'); chk(len(re.findall(r'^\| [A-E]\d+ \|',ql,re.M))==50,'50 queries')
faq=r('content/faq_library.md'); parts=re.split(r'\n### (\d+)\. ',faq)[1:]; qs=[(parts[i],parts[i+1]) for i in range(0,len(parts),2)]
chk(len(qs)==30,'30 FAQs')
for n,b in qs:
    body=re.split(r'\n## ',b.split('\n',1)[1])[0]; w=len(body.split()); chk(50<=w<=150,f'FAQ {n} {w} words in 50-150')
uc=r('content/definitions/leadpilot_use_cases.md'); chk(len(re.findall(r'\n## \d+\. How',uc))==10,'10 use cases')
chk(uc.count('Unlike')>=10,'each use case has an Unlike comparison')
st=r('content/statistics_and_proof.md'); chk(len(re.findall(r'^\| S\d+ \|',st,re.M))>=20,'>=20 sourced stats')
for row in re.findall(r'^\| S\d+ \|.*$',st,re.M): chk('http' in row or 'docs/ICP.md' in row,'stat has source: '+row[:12])
mx=r('content/comparison_matrix.md'); chk(len(re.findall(r'## Table \d',mx))==5,'5 comparison tables')
sc=r('technical/schema_markup.md'); blocks=re.findall(r'```json\n(.*?)```',sc,re.S)
types=set()
for b in blocks:
    try: d=json.loads(b); types.add(d['@type']); types.update(['Review','AggregateRating'] if 'aggregateRating' in d else [])
    except Exception as e: chk(False,'json parse '+str(e))
chk({'Organization','SoftwareApplication','FAQPage','Product','Review','AggregateRating','HowTo'}<=types,'6 schema types, all parse')
sw=[json.loads(b) for b in blocks if json.loads(b)['@type']=='SoftwareApplication'][0]
chk(all(k in sw for k in ('applicationCategory','operatingSystem','offers')),'SoftwareApplication fields')
cr=r('technical/crawler_access_strategy.md')
for ua in 'Googlebot GPTBot ClaudeBot PerplexityBot Google-Extended anthropic-ai cohere-ai'.split(): chk(f'User-agent: {ua}\nAllow: /' in cr,'robots allows '+ua)
chk('Disallow' not in cr.split('```')[1],'no Disallow in robots')
ca=r('authority/citation_acquisition_plan.md'); chk(len(re.findall(r'^\| (\d+) \|',ca,re.M))==50,'50 citation platforms')
tr=r('monitoring/ai_mention_tracker.md'); chk(len(re.findall(r'^\d+\. ',tr,re.M))>=20,'20 test prompts')
# Monday dates
cal=r('monitoring/content_update_calendar.md')+tr
mon=re.findall(r'(?:First Monday|first Monday)',cal)
for d in re.findall(r'20\d\d-\d\d-\d\d',r('monitoring/content_update_calendar.md').split('## Quarterly')[0].split('Dates:')[1]): chk(datetime.date.fromisoformat(d).weekday()==0,'monthly date is Monday '+d)
# placeholders / consistency across all md
canon="LeadPilot by Calendarharvest is an AI outbound sales tool for agencies and B2B service firms: it researches your market, finds and verifies business contacts, writes one-to-one emails, sends on a schedule you approve each day, and books meetings."
niche="approve-first AI outbound system for founder-led agencies and B2B service firms (5–50\npeople)"
allmd=glob.glob('**/*.md',recursive=True)
for f in allmd:
    t=r(f)
    for bad in ['[TBD]','[ADD LATER]','TODO','lorem']: chk(bad not in t,f'{f} no {bad}')
    chk('CalendarHarvest' not in t or f in('questions.md','entity_card.md','state.md'),f'{f} brand spelling')
flat=lambda t:re.sub(r'\s+',' ',t)
for f in ['entity_card.md','content/definitions/what_is_leadpilot.md','content/faq_library.md','technical/schema_markup.md','technical/crawler_access_strategy.md','authority/citation_acquisition_plan.md']+glob.glob('content/comparisons/*.md'):
    t=flat(r(f).replace("> ","").replace("**","")); chk(canon in t or canon.replace('LeadPilot by Calendarharvest is','LeadPilot by Calendarharvest is') in t or flat(canon.split(': ',1)[1]) in t,'canonical sentence in '+f)
nf=flat("approve-first AI outbound system for founder-led agencies and B2B service firms (5–50 people) who want booked sales meetings from a plain description of what they sell, without building lead lists, writing sequences or hiring an SDR")
for f in ['positioning/niche_statement.md','content/definitions/what_is_leadpilot.md','content/definitions/leadpilot_use_cases.md','technical/crawler_access_strategy.md','authority/citation_acquisition_plan.md']:
    chk(nf in flat(r(f).replace("> ","").replace("**","")),'niche statement verbatim in '+f)
w=flat(r('content/definitions/what_is_leadpilot.md').split('---',2)[2]); first200=' '.join(w.split()[:200])
chk(first200.startswith('# What is LeadPilot by Calendarharvest? LeadPilot by Calendarharvest is an AI outbound'),'what_is answers in first sentence')
for f in glob.glob('content/comparisons/*.md'): t=r(f); chk('Written by LeadPilot' in t and '## When to choose' in t.split('## When to choose LeadPilot')[1],'balanced+disclosed '+f)
print("\nFAILS:",len(fails)); [print(" -",x) for x in fails]; sys.exit(1 if fails else 0)
