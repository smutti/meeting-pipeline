from __future__ import annotations
from html import escape
from .common import read, save, locked
from .quality import speaker_for
from .state import State


def stamp(value):
    value = int(value)
    return f"{value // 60:02d}:{value % 60:02d}"


def render(home, job_id):
    directory = home / "jobs" / job_id
    state = State(home)
    status = state.job(job_id)["status"]
    manifest = read(directory / "manifest.json")
    issues = read(directory / "issues.json")
    selected = read(directory / "selected.json")
    diar = read(directory / "diarization.json")
    names = read(directory / "speaker-names.json")
    lines = [
        "---",
        f"meeting_job: {job_id}",
        f"status: {status}",
        "---",
        "",
        f"# {manifest['source_name']}",
        "",
        "Automatic transcript. Open issues are listed in the review report.",
        "",
    ]
    group = []
    label = None
    start = 0
    last = 0
    for w in selected["words"]:
        speakers = speaker_for(w, diar["segments"])
        current = (
            " / ".join(names.get(s, "Speaker " + s) for s in speakers)
            or "Uncertain speaker"
        )
        if len(speakers) > 1:
            current += " (sovrapposizione/cambio)"
        if group and (
            label != current or w["end"] - start > 25 or w["start"] - last > 1.5
        ):
            lines += [f"**[{stamp(start)}] {label}:** {' '.join(group)}", ""]
            group = []
        if not group:
            start = w["start"]
            label = current
        group.append(w["text"].strip())
        last = w["end"]
    if group:
        lines += [f"**[{stamp(start)}] {label}:** {' '.join(group)}", ""]
    open_issues = [i for i in issues if i["status"] == "open"]
    lines += [f"Open issues: {len(open_issues)}. Review file: review.html."]
    (directory / "transcript.md").write_text("\n".join(lines))
    parts = [
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Meeting review</title><style>body{max-width:1100px;margin:35px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f4f6f2;color:#203932}article{background:white;padding:20px;margin:15px 0;border:1px solid #ccd7cf;border-radius:10px}audio{width:100%}button{padding:8px 14px;cursor:pointer}pre{white-space:pre-wrap}small{color:#55685e}.alternatives{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}code{overflow-wrap:anywhere}</style>""",
        f'<h1>{escape(manifest["source_name"])}</h1><p>{escape(status)} · {len(open_issues)} open issues. Model scores are not accuracy percentages.</p><audio id="player" controls preload="none" src="audio.wav"></audio><p><a href="transcript.md">Transcript</a> · <a href="issues.json">Issues JSON</a></p>',
    ]
    for item in open_issues:
        parts.append(
            f'<article><small>{escape(item["id"])} · {escape(item["kind"])}</small><h2>{stamp(item["start"])}–{stamp(item["end"])}</h2><p>{escape(item["reason"])}</p><button data-start="{max(0, item["start"] - 2)}" data-end="{item["end"] + 2}">Listen</button><div class="alternatives">'
        )
        for key, label in [("primary", "Parakeet"), ("secondary", "Qwen")]:
            if item.get(key):
                parts.append(f"<div><h3>{label}</h3><p>{escape(item[key])}</p></div>")
        if item.get("third_reading"):
            parts.append(
                f"<div><h3>Whisper, with context</h3><p>{escape(item['third_reading']['text'])}</p></div>"
            )
        if item.get("candidates"):
            parts.append(
                "<div><h3>Voice candidates to confirm</h3><p>"
                + escape(", ".join(x["name"] for x in item["candidates"]))
                + "</p></div>"
            )
        parts.append(
            "</div><p>Use <code>$meeting-review</code> with this issue ID, or run:</p><pre>"
            + escape(f"meet review resolve {job_id} {item['id']} --action keep")
            + "</pre></article>"
        )
    parts.append(
        """<script>const a=document.getElementById('player');document.querySelectorAll('[data-start]').forEach(b=>b.onclick=()=>{a.currentTime=Number(b.dataset.start);a.dataset.stop=b.dataset.end;a.play().catch(()=>{});});a.ontimeupdate=()=>{if(a.dataset.stop&&a.currentTime>=Number(a.dataset.stop)){a.pause();delete a.dataset.stop;}};</script></html>"""
    )
    (directory / "review.html").write_text("\n".join(parts))
    return {
        "job": job_id,
        "status": status,
        "open_issues": len(open_issues),
        "report": str(directory / "review.html"),
        "transcript": str(directory / "transcript.md"),
    }


def resolve(home, job_id, issue_id, action, text=None, name=None, language=None):
    from .adapters import Engines, crop
    from .common import load_config

    directory = home / "jobs" / job_id
    state = State(home)
    state.job(job_id)
    with locked(home / "worker.lock"):
        issues = read(directory / "issues.json")
        item = next((i for i in issues if i["id"] == issue_id), None)
        if item is None:
            raise ValueError("Unknown review item")
        if item["status"] != "open":
            raise ValueError("Review item already resolved")
        if action == "name":
            if not name or not item.get("speaker"):
                raise ValueError("A name and a speaker-related item are required")
            names = read(directory / "speaker-names.json")
            names[item["speaker"]] = name
            save(directory / "speaker-names.json", names)
            for other in issues:
                if (
                    other["kind"] == "identity"
                    and other.get("speaker") == item["speaker"]
                ):
                    other.update(status="reviewed", resolution="name", name=name)
        elif action == "replace":
            if (
                item["kind"] not in {"text", "disagreement"}
                or not text
                or not text.strip()
            ):
                raise ValueError(
                    "Text replacement requires a text-related item and nonempty text"
                )
            selected = read(directory / "selected.json")
            if any(
                e["start"] < item["end"] and e["end"] > item["start"]
                for e in selected["reviewed_edits"]
            ):
                raise ValueError(
                    "This replacement overlaps an existing edit; resolve by retaining the already reviewed text"
                )
            manifest = read(directory / "manifest.json")
            lang = language or manifest["parameters"]["language"]
            if lang == "auto":
                raise ValueError(
                    "Specify --language it/en for alignment of a reviewed replacement"
                )
            clip = crop(
                directory / "audio.wav",
                directory / "review-edit.wav",
                item["start"],
                item["end"],
            )
            result = Engines(load_config(home)["runtime"]).align(
                clip, text, lang, directory / "review-edits" / issue_id
            )
            words = [
                {
                    **w,
                    "start": w["start"] + item["start"],
                    "end": w["end"] + item["start"],
                }
                for w in result["words"]
            ]
            if not words:
                raise ValueError("Alignment returned no words")
            if any(
                w["start"] < item["start"]
                or w["end"] > item["end"] + 0.1
                or w["end"] < w["start"]
                for w in words
            ):
                raise ValueError("Alignment falls outside the reviewed audio span")
            selected["words"] = [
                w
                for w in selected["words"]
                if not item["start"] <= (w["start"] + w["end"]) / 2 < item["end"]
            ] + words
            selected["words"].sort(key=lambda w: w["start"])
            selected["reviewed_edits"].append(
                {
                    "issue": issue_id,
                    "start": item["start"],
                    "end": item["end"],
                    "text": text,
                }
            )
            save(directory / "selected.json", selected)
        elif action != "keep":
            raise ValueError("Action must be keep, name or replace")
        item.update(status="reviewed", resolution=action)
        save(directory / "issues.json", issues)
        status = (
            "needs_review" if any(i["status"] == "open" for i in issues) else "reviewed"
        )
        state.status(job_id, status)
        state.event(
            job_id,
            "review",
            {"issue": issue_id, "action": action, "text": text, "name": name},
        )
        result = render(home, job_id)
        destination = load_config(home).get("auto_export_directory")
        if status == "reviewed" and destination:
            from .service import export

            result["export"] = export(home, job_id, destination)
        return result
