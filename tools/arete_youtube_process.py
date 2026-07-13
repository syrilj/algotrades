#!/usr/bin/env python3
"""Process Arete Trading YouTube videos into agent-ready markdown + playbook.

Pipeline:
  1. List channel videos (yt-dlp)
  2. Pull captions / transcripts (youtube-transcript-api)
  3. Write one markdown file per video under docs/arete/videos/
  4. Extract trading insights and merge into docs/arete/ARETE_PLAYBOOK.md

Usage:
  python tools/arete_youtube_process.py --limit 5          # smoke test
  python tools/arete_youtube_process.py --new-only         # incremental
  python tools/arete_youtube_process.py --all              # full channel
  python tools/arete_youtube_process.py --video-id abc123  # one video
  python tools/arete_youtube_process.py --rebuild-playbook # merge only

Env (optional):
  OPENAI_API_KEY  — richer insight extraction; heuristics used if unset
  OPENAI_MODEL    — default gpt-4o-mini
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "arete"
VIDEOS_DIR = OUT_DIR / "videos"
STATE_DIR = OUT_DIR / "_state"
PLAYBOOK_PATH = OUT_DIR / "ARETE_PLAYBOOK.md"
PROCESSED_PATH = STATE_DIR / "processed.json"
INDEX_PATH = STATE_DIR / "channel_index.json"
INSIGHTS_PATH = STATE_DIR / "insights.jsonl"

CHANNEL_URL = "https://www.youtube.com/@AreteTrading/videos"
CHANNEL_HANDLE = "@AreteTrading"

TICKER_RE = re.compile(r"\b(?:\$)?([A-Z]{1,5})\b")
LEVEL_RE = re.compile(
    r"(?i)(?:support|resistance|level|pivot|target|stop|vwap|open|"
    r"high|low|gap|break(?:out|down)?|reject(?:ion)?|hold(?:ing)?)"
    r"[^.\n]{0,80}?(\d{2,5}(?:\.\d{1,2})?)"
)
INDEX_WORDS = {
    "spy", "spx", "qqq", "iwm", "dia", "vix", "ndx", "rut", "es", "nq",
    "ym", "rty", "tlt", "hyg", "uvxy", "sqqq", "tqqq", "soxl", "smh",
}
STOP_TICKERS = {
    "I", "A", "AM", "PM", "THE", "AND", "FOR", "TO", "OF", "IN", "ON", "AT",
    "OR", "IS", "IT", "BE", "AS", "BY", "IF", "SO", "WE", "US", "OK", "ALL",
    "NOW", "NOT", "BUT", "CAN", "HAS", "HAD", "WAS", "ARE", "YOU", "THIS",
    "THAT", "WITH", "FROM", "HAVE", "WILL", "JUST", "LIKE", "WHAT", "WHEN",
    "THEN", "THAN", "ALSO", "INTO", "OVER", "OUT", "UP", "DOWN", "HERE",
    "THERE", "THEY", "THEM", "YOUR", "OUR", "HIS", "HER", "SHE", "HIM",
    "WHO", "HOW", "WHY", "GET", "GOT", "SEE", "SAY", "SAYS", "SAID", "ONE",
    "TWO", "NEW", "OLD", "BIG", "LOW", "HIGH", "DAY", "WEEK", "YEAR", "LONG",
    "SHORT", "BUY", "SELL", "PUT", "CALL", "OPS", "ETF", "CEO", "CFO", "IPO",
    "ATH", "ATL", "AH", "PRE", "RTH", "EPS", "PE", "ROI", "USD", "USA",
    "NYSE", "NASDAQ",
    # CTA / filler from auto captions + descriptions
    "WATCH", "FULL", "VIDEO", "MAKE", "SURE", "STOCK", "STOCKS", "MARKET",
    "TODAY", "LIVE", "TRADE", "TRADES", "TRADING", "IDEA", "IDEAS", "NEWS",
    "NEXT", "BACK", "LOOK", "LOOKS", "WANT", "NEED", "STILL", "REALLY",
    "GOING", "THING", "THINGS", "POINT", "POINTS", "AREA", "AREAS", "SHOW",
    "TAKE", "TAKES", "COME", "COMES", "KEEP", "KIND", "SORT", "MUCH",
    "VERY", "WELL", "GOOD", "BEST", "FREE", "JOIN", "LINK", "BELOW",
    "SUBSCRIBE", "COMMENT", "SHARE", "CLICK", "CHECK", "DISCORD", "TWITTER",
    # Indicators / jargon mistaken for tickers
    "ATR", "RSI", "ADX", "VWAP", "EMA", "SMA", "MACD", "OBV", "CCI", "MFI",
    "FYI", "IMO", "AKA", "ETC", "LLM", "API", "PDF",
}
CTA_NOISE_RE = re.compile(
    r"(?is)(?:make sure to watch|watch the full video|subscribe|discord|"
    r"twitter|instagram|business inquiries|for more|follow us).*"
)
CONCEPT_PATTERNS = [
    (r"(?i)\bvwap\b", "VWAP"),
    (r"(?i)\bpre[- ]?market\b", "premarket"),
    (r"(?i)\bopening range\b|\bORB\b", "opening range / ORB"),
    (r"(?i)\bgap\s*(fill|and go|up|down)\b", "gap setups"),
    (r"(?i)\bvolume\b", "volume"),
    (r"(?i)\brelative strength\b|\bRS\b", "relative strength"),
    (r"(?i)\bmarket\s+internals?\b|\bTICK\b|\bADD\b", "market internals"),
    (r"(?i)\brisk\b|\bposition size\b|\bstop\b", "risk / stops"),
    (r"(?i)\bearnings\b", "earnings"),
    (r"(?i)\bfed\b|\bFOMC\b|\bCPI\b|\bNFP\b", "macro / catalysts"),
    (r"(?i)\bbreakout\b|\bbreakdown\b", "breakout / breakdown"),
    (r"(?i)\btrend\b|\bhigher high\b|\blower low\b", "trend structure"),
    (r"(?i)\boptions?\b|\bcall\b|\bput\b|\bIV\b", "options"),
    (r"(?i)\bscalp\b|\bday trade\b|\bswing\b", "timeframe / style"),
    (r"(?i)\blevels?\b|\bkey level\b", "key levels"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text: str, max_len: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return (s[:max_len] or "video").rstrip("-")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ensure_dirs() -> None:
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def list_channel_videos(limit: int | None = None) -> list[dict[str, Any]]:
    """Flat list of channel uploads via yt-dlp (no download)."""
    try:
        import yt_dlp
    except ImportError as e:
        raise SystemExit(
            "Missing yt-dlp. Install with: pip install yt-dlp youtube-transcript-api"
        ) from e

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": limit,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(CHANNEL_URL, download=False)

    entries = info.get("entries") or []
    videos: list[dict[str, Any]] = []
    for e in entries:
        if not e:
            continue
        vid = e.get("id") or e.get("url")
        if not vid:
            continue
        videos.append(
            {
                "id": vid,
                "title": e.get("title") or vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "duration": e.get("duration"),
                "upload_date": e.get("upload_date"),
                "description": e.get("description") or "",
                "view_count": e.get("view_count"),
            }
        )
    _save_json(
        INDEX_PATH,
        {"fetched_at": _utc_now(), "channel": CHANNEL_HANDLE, "videos": videos},
    )
    return videos


def enrich_video_meta(video_id: str) -> dict[str, Any]:
    """Full metadata for one video (upload date, description)."""
    try:
        import yt_dlp
    except ImportError:
        return {}
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}", download=False
        )
    return {
        "id": video_id,
        "title": info.get("title") or video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "duration": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "description": info.get("description") or "",
        "view_count": info.get("view_count"),
        "channel": info.get("channel") or info.get("uploader") or "Arete Trading",
    }


def fetch_transcript(video_id: str) -> tuple[str, str]:
    """Return (plain_text, source_label). Empty text if unavailable."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            NoTranscriptFound,
            TranscriptsDisabled,
            VideoUnavailable,
        )
    except ImportError as e:
        raise SystemExit(
            "Missing youtube-transcript-api. Install with: "
            "pip install youtube-transcript-api"
        ) from e

    api = YouTubeTranscriptApi()
    try:
        listing = api.list(video_id)
        transcript = None
        source = "unknown"
        try:
            transcript = listing.find_manually_created_transcript(
                ["en", "en-US", "en-GB"]
            )
            source = "manual_en"
        except Exception:
            try:
                transcript = listing.find_generated_transcript(
                    ["en", "en-US", "en-GB"]
                )
                source = "auto_en"
            except Exception:
                for t in listing:
                    transcript = t
                    source = f"other:{t.language_code}"
                    break
        if transcript is None:
            return "", "none"
        fetched = transcript.fetch()
        chunks: list[str] = []
        for snip in fetched:
            text = snip.text if hasattr(snip, "text") else snip.get("text", "")
            text = (text or "").replace("\n", " ").strip()
            if text:
                chunks.append(text)
        return " ".join(chunks), source
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable):
        return "", "unavailable"
    except Exception as exc:  # noqa: BLE001 — keep pipeline moving
        print(f"  transcript error for {video_id}: {exc}", file=sys.stderr)
        return "", f"error:{type(exc).__name__}"


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "unknown"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    return f"{m}m {sec:02d}s"


def format_upload_date(raw: str | None) -> str:
    if not raw or len(raw) != 8:
        return raw or "unknown"
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def heuristic_insights(title: str, description: str, transcript: str) -> dict[str, Any]:
    clean_desc = CTA_NOISE_RE.sub(" ", description or "")
    # Prefer transcript + title for tickers; description is full of CTA caps.
    ticker_blob = f"{title}\n{transcript}"
    blob = f"{title}\n{clean_desc}\n{transcript}"
    lower = blob.lower()

    raw_counts: Counter[str] = Counter()
    context_hits: Counter[str] = Counter()
    for m in TICKER_RE.finditer(ticker_blob):
        t = m.group(1)
        if t in STOP_TICKERS or len(t) < 2:
            continue
        raw_counts[t] += 1
        start = m.start(1)
        has_dollar = start > 0 and ticker_blob[start - 1] == "$"
        if has_dollar or t.lower() in INDEX_WORDS:
            context_hits[t] += 2
            continue
        window = ticker_blob[max(0, m.start() - 40) : m.end() + 40].lower()
        if re.search(
            r"(ticker|shares?|long|short|calls?|puts?|levels?|break|"
            r"support|resistance|earnings|gap|vwap|chart|name|etf)",
            window,
        ):
            context_hits[t] += 1

    tickers: Counter[str] = Counter()
    for t, n in raw_counts.items():
        if t.lower() in INDEX_WORDS or context_hits[t] > 0 or n >= 4:
            tickers[t] = n

    indexes = sorted(
        {t for t in tickers if t.lower() in INDEX_WORDS},
        key=lambda x: -tickers[x],
    )
    symbols = [
        t for t, _ in tickers.most_common(40) if t.lower() not in INDEX_WORDS
    ][:25]

    levels: list[str] = []
    for m in LEVEL_RE.finditer(blob):
        phrase = re.sub(r"\s+", " ", m.group(0).strip())
        if phrase not in levels and len(phrase) < 120:
            levels.append(phrase)
    levels = levels[:40]

    concepts: list[str] = []
    for pat, label in CONCEPT_PATTERNS:
        if re.search(pat, lower) and label not in concepts:
            concepts.append(label)

    looks_for: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", transcript[:12000]):
        s = sent.strip()
        if len(s) < 40 or len(s) > 220:
            continue
        if re.search(
            r"(?i)\b(looking for|watch(?:ing)?|want to see|key is|important|"
            r"if we hold|if we break|levels? to watch|setup|thesis)\b",
            s,
        ):
            looks_for.append(s)
        if len(looks_for) >= 12:
            break

    summary_bits = []
    if concepts:
        summary_bits.append("Themes: " + ", ".join(concepts[:8]))
    if indexes:
        summary_bits.append("Indexes: " + ", ".join(indexes[:8]))
    if symbols:
        summary_bits.append("Tickers: " + ", ".join(symbols[:10]))

    return {
        "method": "heuristic",
        "agent_summary": (
            " | ".join(summary_bits)
            or "Transcript captured; skim for setups and levels."
        ),
        "what_he_looks_for": looks_for,
        "levels_and_indexes": levels,
        "indexes": indexes,
        "symbols": symbols,
        "concepts": concepts,
        "risk_notes": [
            s for s in looks_for if re.search(r"(?i)risk|stop|size|cut", s)
        ][:6],
        "process_notes": [
            s
            for s in looks_for
            if re.search(r"(?i)premarket|open|plan|checklist|watchlist", s)
        ][:6],
        "quotes": [],
    }


def llm_insights(title: str, description: str, transcript: str) -> dict[str, Any] | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    body = transcript[:28000]
    prompt = f"""You extract durable trading lessons from an Arete Trading YouTube video.
Return ONLY valid JSON with keys:
- agent_summary: 3-6 sentences an agent can follow (what this video teaches)
- what_he_looks_for: string array of concrete tells/setups/criteria
- levels_and_indexes: string array (SPX/SPY/VIX levels, pivots, VWAP rules, key prices)
- symbols: string array of tickers discussed with intent
- concepts: string array of named concepts (ORB, gap fill, RS, internals, etc.)
- risk_notes: string array (stops, size, stand-aside rules)
- process_notes: string array (premarket routine, how he builds the plan)
- quotes: up to 5 short memorable teaching lines

Focus on transferable rules, not one-day noise. Ignore ads/CTAs.

Title: {title}
Description: {description[:1500]}
Transcript:
{body}
"""
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a trading desk analyst extracting operator "
                        "playbooks from education videos."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        data["method"] = f"openai:{model}"
        return data
    except Exception as exc:  # noqa: BLE001
        print(f"  LLM extract failed: {exc}", file=sys.stderr)
        return None


def extract_insights(title: str, description: str, transcript: str) -> dict[str, Any]:
    llm = llm_insights(title, description, transcript) if transcript else None
    if llm:
        for key in (
            "what_he_looks_for",
            "levels_and_indexes",
            "symbols",
            "concepts",
            "risk_notes",
            "process_notes",
            "quotes",
            "indexes",
        ):
            if key not in llm or llm[key] is None:
                llm[key] = []
            elif isinstance(llm[key], str):
                llm[key] = [llm[key]]
        return llm
    return heuristic_insights(title, description, transcript)


def video_markdown(
    meta: dict[str, Any],
    transcript: str,
    source: str,
    insights: dict[str, Any],
) -> str:
    date = format_upload_date(meta.get("upload_date"))
    lines = [
        f"# {meta.get('title', meta.get('id'))}",
        "",
        f"- **Channel:** {CHANNEL_HANDLE}",
        f"- **Video ID:** `{meta.get('id')}`",
        f"- **URL:** {meta.get('url')}",
        f"- **Published:** {date}",
        f"- **Duration:** {format_duration(meta.get('duration'))}",
        f"- **Transcript source:** {source}",
        f"- **Insight method:** {insights.get('method', 'n/a')}",
        f"- **Processed:** {_utc_now()}",
        "",
        "> Agent use: read **Agent brief**, then **What he looks for** / levels. "
        "Use transcript only when you need exact wording.",
        "",
        "## Agent brief",
        "",
        insights.get("agent_summary") or "_No summary._",
        "",
        "## What he looks for",
        "",
    ]
    looks = insights.get("what_he_looks_for") or []
    if looks:
        lines.extend(f"- {item}" for item in looks)
    else:
        lines.append("- _None extracted._")

    lines += ["", "## Levels & indexes", ""]
    levels = insights.get("levels_and_indexes") or []
    if levels:
        lines.extend(f"- {item}" for item in levels)
    else:
        lines.append("- _None extracted._")

    lines += ["", "## Symbols", ""]
    symbols = insights.get("symbols") or []
    indexes = insights.get("indexes") or []
    if indexes:
        lines.append("**Indexes / ETFs:** " + ", ".join(indexes))
    if symbols:
        lines.append("**Names:** " + ", ".join(symbols))
    if not symbols and not indexes:
        lines.append("- _None extracted._")

    lines += ["", "## Concepts", ""]
    concepts = insights.get("concepts") or []
    if concepts:
        lines.extend(f"- {c}" for c in concepts)
    else:
        lines.append("- _None extracted._")

    lines += ["", "## Risk notes", ""]
    risk = insights.get("risk_notes") or []
    if risk:
        lines.extend(f"- {r}" for r in risk)
    else:
        lines.append("- _None extracted._")

    lines += ["", "## Process / routine", ""]
    process = insights.get("process_notes") or []
    if process:
        lines.extend(f"- {p}" for p in process)
    else:
        lines.append("- _None extracted._")

    quotes = insights.get("quotes") or []
    if quotes:
        lines += ["", "## Teaching quotes", ""]
        lines.extend(f"> {q}" for q in quotes)

    desc = (meta.get("description") or "").strip()
    if desc:
        lines += ["", "## Video description", "", "```", desc[:4000], "```"]

    lines += ["", "## Transcript", ""]
    if transcript:
        paras = []
        words = transcript.split()
        chunk: list[str] = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= 120:
                paras.append(" ".join(chunk))
                chunk = []
        if chunk:
            paras.append(" ".join(chunk))
        lines.extend(paras)
    else:
        lines.append("_No captions available for this video._")

    lines.append("")
    return "\n".join(lines)


def video_path(meta: dict[str, Any]) -> Path:
    date = format_upload_date(meta.get("upload_date")).replace("unknown", "undated")
    name = f"{date}_{meta['id']}_{_slug(meta.get('title', ''))}.md"
    return VIDEOS_DIR / name


def append_insight_row(row: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with INSIGHTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_all_insight_rows() -> list[dict[str, Any]]:
    if not INSIGHTS_PATH.exists():
        return []
    rows = []
    for line in INSIGHTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        by_id[r["video_id"]] = r
    return list(by_id.values())


def rebuild_playbook(rows: list[dict[str, Any]] | None = None) -> None:
    rows = rows if rows is not None else load_all_insight_rows()
    rows = sorted(rows, key=lambda r: r.get("upload_date") or "", reverse=True)

    concept_c: Counter[str] = Counter()
    symbol_c: Counter[str] = Counter()
    index_c: Counter[str] = Counter()
    looks: list[tuple[str, str, str]] = []
    levels: list[tuple[str, str, str]] = []
    risk: list[tuple[str, str, str]] = []
    process: list[tuple[str, str, str]] = []
    quotes: list[tuple[str, str, str]] = []

    for r in rows:
        ins = r.get("insights") or {}
        for c in ins.get("concepts") or []:
            concept_c[str(c)] += 1
        for s in ins.get("symbols") or []:
            symbol_c[str(s).upper()] += 1
        for i in ins.get("indexes") or []:
            index_c[str(i).upper()] += 1
        date = format_upload_date(r.get("upload_date"))
        title = r.get("title") or r.get("video_id")
        for item in ins.get("what_he_looks_for") or []:
            looks.append((date, title, str(item)))
        for item in ins.get("levels_and_indexes") or []:
            levels.append((date, title, str(item)))
        for item in ins.get("risk_notes") or []:
            risk.append((date, title, str(item)))
        for item in ins.get("process_notes") or []:
            process.append((date, title, str(item)))
        for item in ins.get("quotes") or []:
            quotes.append((date, title, str(item)))

    def uniq(
        items: list[tuple[str, str, str]], limit: int
    ) -> list[tuple[str, str, str]]:
        seen: set[str] = set()
        out: list[tuple[str, str, str]] = []
        for date, title, text in items:
            key = re.sub(r"\s+", " ", text.casefold().strip())
            if key in seen or len(key) < 20:
                continue
            seen.add(key)
            out.append((date, title, text))
            if len(out) >= limit:
                break
        return out

    looks_u = uniq(looks, 80)
    levels_u = uniq(levels, 80)
    risk_u = uniq(risk, 40)
    process_u = uniq(process, 40)
    quotes_u = uniq(quotes, 30)

    channel_home = CHANNEL_URL.replace("/videos", "")
    lines = [
        "# Arete Trading Playbook",
        "",
        f"Living desk notes distilled from [{CHANNEL_HANDLE}]({channel_home}).",
        "Updated every time `tools/arete_youtube_process.py` processes videos.",
        "",
        f"- **Last rebuilt:** {_utc_now()}",
        f"- **Videos ingested:** {len(rows)}",
        f"- **Per-video files:** `docs/arete/videos/`",
        f"- **Raw insight log:** `docs/arete/_state/insights.jsonl`",
        "",
        "> Agent instruction: Prefer this playbook for durable rules (what he looks for, "
        "levels/indexes, risk, process). Open a video markdown only when you need episode "
        "context or the full transcript.",
        "",
        "## Core themes (frequency across videos)",
        "",
    ]
    if concept_c:
        for concept, n in concept_c.most_common(25):
            lines.append(f"- **{concept}** — seen in {n} video(s)")
    else:
        lines.append("- _Process videos to populate._")

    lines += ["", "## Indexes & market context he watches", ""]
    if index_c:
        lines.append(
            ", ".join(f"**{k}** ({v})" for k, v in index_c.most_common(20))
        )
    else:
        lines.append("_None yet._")

    lines += ["", "## Names that show up often", ""]
    if symbol_c:
        lines.append(
            ", ".join(f"`{k}` ({v})" for k, v in symbol_c.most_common(40))
        )
    else:
        lines.append("_None yet._")

    def section(title: str, items: list[tuple[str, str, str]]) -> None:
        lines.append("")
        lines.append(f"## {title}")
        lines.append("")
        if not items:
            lines.append("_None yet._")
            return
        for date, vid_title, text in items:
            lines.append(f"- {text}")
            lines.append(f"  - _{date} — {vid_title}_")

    section("What he looks for (accumulated)", looks_u)
    section("Levels, pivots, and price tells", levels_u)
    section("Risk & stand-aside rules", risk_u)
    section("Premarket / process", process_u)
    section("Teaching quotes", quotes_u)

    lines += [
        "",
        "## Processed video index",
        "",
        "| Date | Title | File |",
        "|------|-------|------|",
    ]
    for r in rows:
        date = format_upload_date(r.get("upload_date"))
        title = (r.get("title") or r["video_id"]).replace("|", "/")
        rel = r.get("markdown_rel") or ""
        lines.append(
            f"| {date} | [{title}]({r.get('url', '')}) | `{rel}` |"
        )

    lines += [
        "",
        "## How to refresh",
        "",
        "```bash",
        "# New uploads only",
        "python tools/arete_youtube_process.py --new-only",
        "",
        "# Next N videos from channel",
        "python tools/arete_youtube_process.py --limit 10",
        "",
        "# Full channel (slow)",
        "python tools/arete_youtube_process.py --all",
        "",
        "# Rebuild playbook from existing insights",
        "python tools/arete_youtube_process.py --rebuild-playbook",
        "```",
        "",
        "Set `OPENAI_API_KEY` for richer extraction; otherwise heuristics still fill "
        "the playbook.",
        "",
    ]
    PLAYBOOK_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Playbook → {PLAYBOOK_PATH}")


def process_one(
    meta: dict[str, Any], processed: dict[str, Any], force: bool = False
) -> bool:
    vid = meta["id"]
    if not force and vid in processed.get("videos", {}):
        print(f"skip {vid} (already processed)")
        return False

    print(f"process {vid}: {meta.get('title', '')[:70]}")
    if not meta.get("upload_date") or not meta.get("description"):
        rich = enrich_video_meta(vid)
        meta = {**meta, **{k: v for k, v in rich.items() if v}}

    transcript, source = fetch_transcript(vid)
    insights = extract_insights(
        meta.get("title", ""), meta.get("description", ""), transcript
    )
    path = video_path(meta)
    path.write_text(
        video_markdown(meta, transcript, source, insights), encoding="utf-8"
    )
    rel = str(path.relative_to(ROOT))

    row = {
        "video_id": vid,
        "title": meta.get("title"),
        "url": meta.get("url"),
        "upload_date": meta.get("upload_date"),
        "duration": meta.get("duration"),
        "transcript_source": source,
        "transcript_chars": len(transcript),
        "markdown_rel": rel,
        "processed_at": _utc_now(),
        "insights": insights,
    }
    append_insight_row(row)

    processed.setdefault("videos", {})[vid] = {
        "title": meta.get("title"),
        "markdown": rel,
        "processed_at": row["processed_at"],
        "transcript_source": source,
    }
    _save_json(PROCESSED_PATH, processed)
    print(
        f"  → {rel} ({source}, {len(transcript)} chars, "
        f"method={insights.get('method')})"
    )
    return True


def write_readme() -> None:
    readme = OUT_DIR / "README.md"
    if readme.exists():
        return
    readme.write_text(
        """# Arete Trading — video knowledge base

Source channel: https://www.youtube.com/@AreteTrading

| Path | Role |
|------|------|
| `ARETE_PLAYBOOK.md` | Overarching rules: what he looks for, levels/indexes, risk, process |
| `videos/*.md` | One agent-ready file per video (brief + transcript) |
| `_state/` | Processed IDs + insight log (do not edit by hand) |

```bash
python tools/arete_youtube_process.py --limit 5
python tools/arete_youtube_process.py --new-only
```
""",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Arete Trading YouTube → markdown + playbook"
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="Process entire channel uploads")
    g.add_argument("--limit", type=int, help="Process first N videos from channel list")
    g.add_argument("--video-id", help="Process a single video id")
    g.add_argument(
        "--rebuild-playbook", action="store_true", help="Only rebuild playbook"
    )
    p.add_argument(
        "--new-only", action="store_true", help="Skip already processed ids"
    )
    p.add_argument(
        "--force", action="store_true", help="Re-process even if already done"
    )
    p.add_argument(
        "--channel-url",
        default=CHANNEL_URL,
        help="Channel videos URL (default: @AreteTrading)",
    )
    return p.parse_args()


def main() -> int:
    global CHANNEL_URL
    args = parse_args()
    CHANNEL_URL = args.channel_url
    ensure_dirs()
    write_readme()

    if args.rebuild_playbook:
        rebuild_playbook()
        return 0

    processed = _load_json(PROCESSED_PATH, {"videos": {}})

    if args.video_id:
        meta = enrich_video_meta(args.video_id)
        if not meta:
            meta = {
                "id": args.video_id,
                "title": args.video_id,
                "url": f"https://www.youtube.com/watch?v={args.video_id}",
            }
        process_one(meta, processed, force=args.force or not args.new_only)
        rebuild_playbook()
        return 0

    limit = None if args.all else (args.limit or 5)
    print(f"Listing channel videos (limit={limit})…")
    videos = list_channel_videos(limit=limit)
    print(f"Found {len(videos)} videos")

    done = 0
    for meta in videos:
        vid = meta["id"]
        if args.new_only and vid in processed.get("videos", {}) and not args.force:
            continue
        if process_one(meta, processed, force=args.force):
            done += 1

    rebuild_playbook()
    print(f"Finished. Newly processed: {done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
