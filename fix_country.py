import json

PREFIX_MAP = {
    '+507': 'Panama', '507': 'Panama',
    '+503': 'El Salvador', '503': 'El Salvador',
    '+506': 'Costa Rica', '506': 'Costa Rica',
    '+502': 'Guatemala', '502': 'Guatemala',
    '+504': 'Honduras', '504': 'Honduras',
    '+505': 'Nicaragua', '505': 'Nicaragua',
    '+57': 'Colombia', '57': 'Colombia',
    '+593': 'Ecuador', '593': 'Ecuador',
    '+51': 'Peru', '51': 'Peru',
    '+56': 'Chile', '56': 'Chile',
    '+54': 'Argentina', '54': 'Argentina',
    '+52': 'Mexico', '52': 'Mexico',
    '+598': 'Uruguay', '598': 'Uruguay',
    '+595': 'Paraguay', '595': 'Paraguay',
    '+591': 'Bolivia', '591': 'Bolivia',
    '+58': 'Venezuela', '58': 'Venezuela',
    '+1809': 'Republica Dominicana',
    '+1829': 'Republica Dominicana',
    '+1849': 'Republica Dominicana',
}

def detect_pais(telefono):
    if not telefono:
        return ''
    clean = ''.join(c for c in telefono if c.isdigit() or c == '+')
    for prefix in ['+1809','+1829','+1849','+507','+503','+506','+502','+504','+505','+598','+595','+591','+593','+54','+56','+52','+58','+51','+57','+53']:
        if clean.startswith(prefix):
            return PREFIX_MAP.get(prefix, '')
    for prefix in ['507','503','506','502','504','505','593','54','56','52','58','51','57','53']:
        if clean.startswith(prefix):
            return PREFIX_MAP.get(prefix, '')
    return ''

with open('/app/data/leads_para_enviar.json') as f:
    leads = json.load(f)

fixed = 0
for l in leads:
    if not l.get('pais'):
        p = detect_pais(l.get('telefono',''))
        if p:
            l['pais'] = p
            fixed += 1

with open('/app/data/leads_para_enviar.json','w') as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)

print('Reparados %d leads con pais' % fixed)
from collections import Counter
c = Counter(l.get('pais','') for l in leads)
for k,v in c.most_common():
    label = k if k else '(sin pais)'
    print('  %s: %d' % (label, v))
