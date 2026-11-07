"""Merge OSM API tiles and extract downhill pistes, aerialways, peaks, restaurants."""
import glob, json, sys, xml.etree.ElementTree as ET
src = sys.argv[1]; out = sys.argv[2]
nodes, ways, nodetags = {}, {}, {}
relations = {}
for f in sorted(glob.glob(src + '/osm_*.xml')):
    for el in ET.parse(f).getroot():
        if el.tag == 'node':
            nid = el.get('id'); nodes[nid] = (float(el.get('lon')), float(el.get('lat')))
            t = {c.get('k'): c.get('v') for c in el if c.tag == 'tag'}
            if t: nodetags[nid] = t
        elif el.tag == 'way':
            ways[el.get('id')] = ([n.get('ref') for n in el if n.tag == 'nd'], {c.get('k'): c.get('v') for c in el if c.tag == 'tag'})
        elif el.tag == 'relation':
            relations[el.get('id')] = ([(m.get('type'), m.get('ref'), m.get('role')) for m in el if m.tag == 'member'], {c.get('k'): c.get('v') for c in el if c.tag == 'tag'})
# relation names/difficulty propagate to member ways
relinfo = {}
for rid, (mem, t) in relations.items():
    if t.get('piste:type') == 'downhill' or t.get('route') == 'piste':
        for typ, ref, role in mem:
            if typ == 'way': relinfo.setdefault(ref, t)
feats = []
def coords(nds): return [nodes[n] for n in nds if n in nodes]
for wid, (nds, t) in ways.items():
    rt = relinfo.get(wid, {})
    pt = t.get('piste:type') or rt.get('piste:type')
    if pt == 'downhill' and t.get('area') != 'yes' and nds[0] != nds[-1] or (pt == 'downhill' and 'area' not in t and nds[0] != nds[-1]):
        c = coords(nds)
        if len(c) < 2: continue
        feats.append({'k': 'piste', 'id': wid,
            'name': t.get('piste:name') or t.get('name') or rt.get('piste:name') or rt.get('name') or '',
            'diff': t.get('piste:difficulty') or rt.get('piste:difficulty') or '',
            'grooming': t.get('piste:grooming', ''), 'c': c})
    elif pt == 'skitour' or pt == 'downhill' and False: pass
    a = t.get('aerialway')
    if a and a not in ('station', 'pylon', 'goods', 'zip_line'):
        c = coords(nds)
        if len(c) < 2: continue
        feats.append({'k': 'lift', 'id': wid, 'name': t.get('name', ''), 'type': a,
            'occupancy': t.get('aerialway:occupancy', ''), 'cap': t.get('aerialway:capacity', ''), 'c': c})
for nid, t in nodetags.items():
    if t.get('natural') == 'peak' and t.get('name'):
        feats.append({'k': 'peak', 'name': t['name'], 'ele': t.get('ele', ''), 'c': [nodes[nid]]})
    if t.get('amenity') in ('restaurant', 'cafe', 'bar', 'fast_food') and t.get('name'):
        feats.append({'k': 'food', 'name': t['name'], 'amenity': t['amenity'], 'c': [nodes[nid]]})
    if t.get('place') in ('village', 'town', 'hamlet') and t.get('name'):
        feats.append({'k': 'place', 'name': t['name'], 'c': [nodes[nid]]})
for wid, (nds, t) in ways.items():
    if t.get('amenity') in ('restaurant', 'cafe', 'bar', 'fast_food') and t.get('name'):
        c = coords(nds); 
        if c: feats.append({'k': 'food', 'name': t['name'], 'amenity': t['amenity'], 'c': [(sum(p[0] for p in c)/len(c), sum(p[1] for p in c)/len(c))]})
from collections import Counter
print(Counter(f['k'] for f in feats)); print(Counter(f.get('diff') for f in feats if f['k']=='piste')); print(Counter(f.get('type') for f in feats if f['k']=='lift'))
print(sorted(set(f['name'] for f in feats if f['k']=='lift')))
print(len(set(f['name'] for f in feats if f['k']=='piste')), 'piste names')
json.dump(feats, open(out, 'w'))
