#!/usr/bin/env python3
"""Build a private, offline transcript comparison; score only human-reviewed clips."""

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path


def tokens(text):
    """Case/punctuation insensitive; preserve accents, numbers and negations."""
    return re.findall(
        r"\w+(?:'\w+)*",
        unicodedata.normalize("NFKC", text).casefold().replace("’", "'"),
    )


def errors(reference, hypothesis):
    """Levenshtein word edits, O(len(hypothesis)) memory; no model reference."""
    ref, hyp = tokens(reference), tokens(hypothesis)
    if not ref:
        raise ValueError("A WER reference must contain at least one word")
    previous = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, 1):
        current = [i]
        for j, other in enumerate(hyp, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (word != other))
            )
        previous = current
    return {
        "edits": previous[-1],
        "reference_words": len(ref),
        "wer": previous[-1] / len(ref),
    }


def score_clips(manifest, references):
    clips = {c["id"]: c for c in manifest.get("clips", [])}
    if len(clips) != len(manifest.get("clips", [])):
        raise ValueError("Duplicate clip id")
    rows, seen = [], set()
    for reference in references:
        cid = reference["clip_id"]
        if cid not in clips or cid in seen:
            raise ValueError("Unknown or duplicate reference clip: " + cid)
        seen.add(cid)
        if reference.get("human_reviewed") is not True:
            continue
        clip = clips[cid]
        for candidate in clip["candidates"]:
            if candidate.get("scope") != "exact_clip":
                continue
            rows.append(
                {
                    "clip_id": cid,
                    "recording": clip["recording"],
                    "variant": candidate["variant"],
                    **errors(reference["text"], candidate["text"]),
                }
            )
    groups = defaultdict(lambda: {"edits": 0, "reference_words": 0, "clips": 0})
    for row in rows:
        group = groups[(row["recording"], row["variant"])]
        for key in ("edits", "reference_words"):
            group[key] += row[key]
        group["clips"] += 1
    totals = [
        {
            "recording": rec,
            "variant": variant,
            **values,
            "wer": values["edits"] / values["reference_words"],
        }
        for (rec, variant), values in groups.items()
    ]
    return {
        "clips": rows,
        "totals": totals,
        "note": "WER applies only to reviewed exact-clip hypotheses; no speaker scoring or full-recording accuracy is inferred.",
    }


def summarize(manifest, references):
    recordings = []
    for rec in manifest["recordings"]:
        variants = rec["variants"]
        if not variants:
            raise ValueError("Each recording needs at least one variant")
        baseline = tokens(variants[0]["text"])
        rows = []
        for variant in variants:
            words = tokens(variant["text"])
            difference = (
                1 - SequenceMatcher(None, baseline, words, autojunk=False).ratio()
            )
            rows.append(
                {
                    "id": variant["id"],
                    "label": variant["label"],
                    "words": len(words),
                    "wall_seconds": variant.get("wall_seconds"),
                    "difference_from_archive": difference,
                    "notes": variant.get("notes", ""),
                }
            )
        recordings.append(
            {
                "id": rec["id"],
                "duration": rec["duration"],
                "variants": rows,
                "diarizers": rec.get("diarizers", []),
            }
        )
    return {
        "recordings": recordings,
        "quality": score_clips(manifest, references),
        "difference_definition": "1 - difflib.SequenceMatcher ratio on normalized words (autojunk=False). Textual disagreement, NOT WER or accuracy. First variant is the archived baseline.",
    }


PAGE = r"""<!doctype html>
<html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Confronto locale delle trascrizioni</title>
<style>
:root{color-scheme:light}body{font:16px/1.55 system-ui;margin:0;background:#f4f6f8;color:#202b36}main{max-width:1400px;margin:auto;padding:28px}h1{font-size:30px;line-height:1.2}h2{margin-top:30px}.note{background:#e4eef6;padding:16px;border-radius:10px}.muted{color:#526171;font-size:14px}button,select,input,textarea{font:inherit;padding:8px;border:1px solid #b4c0cb;border-radius:6px}button{cursor:pointer;background:#eef4f8}audio{width:100%;max-width:600px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:9px;text-align:left;border-bottom:1px solid #d7dfe7}th{background:#e7edf3}.scroll{overflow:auto}.cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{background:white;padding:18px;border-radius:10px;margin:12px 0;min-width:0}.transcript{max-height:600px;overflow:auto;white-space:pre-wrap}.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}textarea{box-sizing:border-box;width:100%;min-height:130px}summary{cursor:pointer;font-weight:600}.segment{margin:5px 0}.time{color:#547087;font-size:12px}pre{white-space:pre-wrap}@media(max-width:850px){.cols{grid-template-columns:1fr}main{padding:15px}}
</style><main>
<h1>Prima versione, modelli e nuova pipeline</h1>
<p class="note">Rapporto privato e offline. Le differenze tra testi non misurano la correttezza. Le note archiviate includono interventi umani; i risultati automatici rimangono candidati. Per valutare la fedeltà, ascoltare prima i campioni e scrivere un riferimento senza guardare le proposte.</p>
<div id="overview"></div>
<h2>Confronto sullo stesso intervallo</h2>
<div class="controls"><label>Audio <select id="recording"></select></label><label>Da (s) <input id="start" type="number" value="0" min="0" step="1"></label><label>A (s) <input id="end" type="number" value="90" min="0" step="1"></label><button id="show">Confronta</button><button id="listen">Ascolta intervallo</button></div>
<audio id="fullaudio" controls preload="none"></audio>
<p class="muted">I timestamp hanno granularità diversa. I segmenti che attraversano un confine vengono mostrati interi, senza inventare tempi parola per parola. Questo estratto visivo non entra nel calcolo WER.</p>
<div class="cols"><div class="card"><select id="left"></select><p id="leftnote" class="muted"></p><div id="lefttext" class="transcript"></div></div><div class="card"><select id="right"></select><p id="rightnote" class="muted"></p><div id="righttext" class="transcript"></div></div></div>
<h2>Testo completo e approfondimenti</h2><div id="fulltexts"></div>
<h2>Campioni per il riferimento umano</h2>
<p>Tre finestre di 90 secondi per registrazione, scelte per posizione prima di leggere gli output. Le proposte sono chiuse inizialmente per ridurre l'influenza sull'ascolto. I campioni difficili aggiuntivi non vanno mescolati con questi per stimare una qualità media. Le modifiche restano in memoria: esportare il JSON prima di chiudere.</p>
<div class="controls"><button id="download">Esporta riferimenti JSON</button><label>Ricarica riferimenti <input id="upload" type="file" accept=".json,application/json"></label></div>
<div id="samples"></div>
<h2>Misure di accuratezza</h2><pre id="scores"></pre>
</main><script id="dataset" type="application/json">__DATA__</script><script>
'use strict';
const D=JSON.parse(document.getElementById('dataset').textContent), M=D.manifest;
const $=id=>document.getElementById(id);
function el(tag,text,cls){const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x;}
function option(s,v,t){const o=el('option',t);o.value=v;s.append(o);}
function table(headers,rows){const w=el('div',undefined,'scroll'),t=el('table'),head=el('tr');headers.forEach(h=>head.append(el('th',h)));t.append(head);rows.forEach(r=>{const tr=el('tr');r.forEach(c=>tr.append(el('td',String(c))));t.append(tr);});w.append(t);return w;}
for(const r of D.summary.recordings){$('overview').append(el('h2',r.id+' · '+(r.duration/60).toFixed(2)+' minuti'));$('overview').append(table(['Variante','Parole normalizzate','Tempo (s)','Differenza testuale vs archivio*'],r.variants.map(v=>[v.label,v.words,v.wall_seconds===null?'—':v.wall_seconds.toFixed(2),(100*v.difference_from_archive).toFixed(1)+'%'])));if(r.diarizers.length)$('overview').append(table(['Diarizzazione','Voci','Nota'],r.diarizers.map(d=>[d.label,d.speakers,d.notes||''])));}
$('overview').append(el('p','* 1 − similarità SequenceMatcher; non è WER, percentuale di errori o graduatoria di qualità. I tempi delle singole inferenze e quelli del workflow hanno confini di misura diversi.','muted'));
for(const r of M.recordings)option($('recording'),r.id,r.label||r.id);
function rec(){return M.recordings.find(r=>r.id===$('recording').value);}
function show(){const r=rec(),a=Number($('start').value),b=Number($('end').value);for(const side of ['left','right']){const v=r.variants.find(v=>v.id===$(side).value),out=$(side+'text');out.replaceChildren();$(side+'note').textContent=v.notes||'';for(const s of v.segments||[]){if(s.end>a&&s.start<b){const p=el('div',undefined,'segment');p.append(el('span',s.start.toFixed(2)+'–'+s.end.toFixed(2)+' '+(s.speaker||'')+'  ','time'),document.createTextNode(s.text));out.append(p);}}if(!out.childNodes.length)out.append(el('p','Nessun segmento temporizzato in questo intervallo. Il testo completo è disponibile sotto.'));}}
function choose(){const r=rec();$('fullaudio').src=r.audio;for(const side of ['left','right']){$(side).replaceChildren();for(const v of r.variants)option($(side),v.id,v.label);} $('right').selectedIndex=Math.min(4,r.variants.length-1);$('fulltexts').replaceChildren();for(const v of r.variants){const det=el('details',undefined,'card');det.append(el('summary',v.label),el('p',v.notes||'','muted'),el('div',v.text,'transcript'));$('fulltexts').append(det);}for(const d of r.diagnostics||[]){const det=el('details',undefined,'card');det.append(el('summary',d.label+' · '+d.start.toFixed(2)+'–'+d.end.toFixed(2)+' s'),el('p',d.notes||'','muted'),el('div',d.text,'transcript'));$('fulltexts').append(det);}show();}
$('recording').onchange=choose;$('show').onclick=show;$('left').onchange=show;$('right').onchange=show;
$('listen').onclick=()=>{const a=Number($('start').value),b=Number($('end').value);if(a<0||b<=a)return;$('fullaudio').currentTime=a;$('fullaudio').play();};
$('fullaudio').ontimeupdate=()=>{if($('fullaudio').currentTime>=Number($('end').value))$('fullaudio').pause();};
const editors=new Map();
for(const c of M.clips||[]){const card=el('section',undefined,'card'),audio=el('audio');audio.controls=true;audio.preload='none';audio.src=c.audio;const ta=el('textarea'),check=el('input');check.type='checkbox';ta.setAttribute('aria-label','Riferimento '+c.id);const label=el('label');label.append(check,document.createTextNode(' Ho ascoltato e verificato tutto il testo del campione'));card.append(el('h3',c.id+' · '+c.start.toFixed(2)+'–'+(c.start+c.duration).toFixed(2)+' s'),audio,ta,label);const det=el('details');det.append(el('summary','Mostra le trascrizioni candidate'));for(const v of c.candidates){det.append(el('h4',v.variant+' · '+v.scope),el('p',v.text));}card.append(det);$('samples').append(card);editors.set(c.id,{ta,check});}
function loadRefs(refs){for(const r of refs){const e=editors.get(r.clip_id);if(e){e.ta.value=r.text||'';e.check.checked=r.human_reviewed===true;}}}
loadRefs(D.references);
$('download').onclick=()=>{const refs=[...editors].map(([id,e])=>({clip_id:id,text:e.ta.value,human_reviewed:e.check.checked}));const u=URL.createObjectURL(new Blob([JSON.stringify(refs,null,2)],{type:'application/json'}));const a=el('a');a.href=u;a.download='references.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};
$('upload').onchange=async()=>{try{const refs=JSON.parse(await $('upload').files[0].text());if(!Array.isArray(refs))throw Error('Attesa una lista JSON');loadRefs(refs);}catch(e){alert(e.message);}};
$('scores').textContent=D.summary.quality.totals.length?JSON.stringify(D.summary.quality,null,2):'WER non calcolato: mancano riferimenti umani verificati. DER e riconoscimento delle identità non sono misurati da questo rapporto.';
choose();
</script></html>"""


def render(manifest, summary, references):
    data = json.dumps(
        {"manifest": manifest, "summary": summary, "references": references},
        ensure_ascii=False,
    )
    # JSON remains inert even with transcript strings containing closing script tags.
    return PAGE.replace(
        "__DATA__", data.replace("<", "\\u003c").replace("&", "\\u0026")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--references", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    references = json.loads(args.references.read_text()) if args.references else []
    summary = summarize(manifest, references)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "comparison.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    (args.output / "comparison.html").write_text(render(manifest, summary, references))
    lines = ["# Confronto delle trascrizioni", "", summary["difference_definition"], ""]
    for rec in summary["recordings"]:
        lines += [
            "## " + rec["id"],
            "",
            "| Variante | Parole | Secondi | Differenza vs archivio (non WER) |",
            "|---|---:|---:|---:|",
        ]
        for v in rec["variants"]:
            lines.append(
                f"| {v['label'].replace('|', '/')} | {v['words']} | {v['wall_seconds']} | {v['difference_from_archive']:.3f} |"
            )
        lines.append("")
    lines += [
        "## WER su campioni verificati",
        "",
        json.dumps(summary["quality"], ensure_ascii=False, indent=2),
    ]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print(args.output / "comparison.html")


if __name__ == "__main__":
    main()
