import json
import os
import re
import boto3
import anthropic
import requests
import xml.etree.ElementTree as ET
from datetime import datetime


RSS_FEEDS = [
    ("BBC World",   "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Reuters",     "https://feeds.reuters.com/reuters/topNews"),
    ("NYT World",   "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("AP News",     "https://feeds.apnews.com/rss/apf-topnews"),
    ("Guardian",    "https://www.theguardian.com/world/rss"),
]

POLISH_FEEDS = [
    ("TVN24",       "https://tvn24.pl/najnowsze.xml"),
    ("Onet",        "https://wiadomosci.onet.pl/.feed/rss"),
    ("PAP",         "https://www.pap.pl/aktualnosci.xml"),
    ("PolskieRadio","https://www.polskieradio.pl/rss/news.xml"),
]

HEADERS = {"User-Agent": "WorldExplainer/1.0 (+https://github.com/worldexplainer)"}


def _parse_feed(source, url, max_items=6):
    items = []
    try:
        resp = requests.get(url, timeout=8, headers=HEADERS)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            desc  = re.sub(r"<[^>]+>", " ", desc).strip()[:180]
            if title:
                items.append(f"[{source}] {title}" + (f": {desc}" if desc else ""))
    except Exception as exc:
        print(f"RSS error ({source}): {exc}")
    return items


def fetch_headlines():
    headlines = []
    for source, url in RSS_FEEDS:
        headlines.extend(_parse_feed(source, url, max_items=6))
    return headlines


def fetch_polish_headlines():
    headlines = []
    for source, url in POLISH_FEEDS:
        headlines.extend(_parse_feed(source, url, max_items=5))
    return headlines


def generate_analysis(headlines: list[str], polish_headlines: list[str]) -> tuple[str, str]:
    today = datetime.utcnow().strftime("%B %d, %Y")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    headlines_block = "\n".join(headlines[:22])
    polish_block    = "\n".join(polish_headlines[:15]) if polish_headlines else "(no Polish feeds available today)"

    prompt = f"""Today is {today}. Here are this morning's top headlines.

=== GLOBAL NEWS ===
{headlines_block}

=== POLAND NEWS (from TVN24, Onet, PAP, Polskie Radio) ===
{polish_block}

You are WorldExplainer — a daily briefing that exposes what the PUBLIC GETS WRONG about the most significant stories. Your job is not to summarise the news; it is to challenge assumptions, expose hidden mechanisms, and draw precise historical parallels.

Structure your response in two sections:

---

## WORLD

Pick the 3–4 most significant global stories. For each write:

**[STORY TITLE IN CAPS]**
**Public belief:** [1 sentence — the naive dominant narrative]
**What's really happening:** [3–4 paragraphs. Deeper mechanics, hidden actors, structural causes, what coverage omits. Name institutions, dates, incentives.]
**Historical analogy:** [1–2 paragraphs. A precise parallel — name the year, the people, the event. Show why it is mechanically apt, not just superficially similar.]
**Controversial thesis:** [1 paragraph. A well-reasoned claim that challenges conventional wisdom. Make the argument; do not hedge it.]

---

## POLAND

Pick the 2–3 most significant Polish stories. Apply the same format. Write in English but treat the Polish reader as the primary audience — explain what Polish public discourse gets wrong, not what a foreign reader needs to understand. Draw analogies to Polish history (Solidarity, martial law, the Partition era, the Sanacja period, PRL etc.) where they illuminate the story. Be willing to challenge both PiS and Tusk-coalition narratives equally.

---

## SYNTHESIS

2–3 paragraphs connecting the global and Polish stories into one overarching pattern the public is missing this week.

---

Style rules:
- Confident, direct prose. No "some argue." No "it remains to be seen."
- Make claims. Defend them with evidence embedded in the prose.
- The reader is an intelligent adult who wants to understand the world, not just consume headlines.
- Flowing paragraphs inside each story section — no bullet points."""

    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text, today


def md_to_html(text: str) -> str:
    """Minimal Markdown → HTML converter for email body."""
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic (single *)
    text = re.sub(r"\*([^*\n]+?)\*", r"<em>\1</em>", text)
    # H2 / H3 / H1
    text = re.sub(r"^### (.+)$", r'<h3 style="color:#555;font-style:italic;margin:4px 0 14px;">\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$",  r'<h2 style="color:#1a1a1a;font-size:20px;margin:40px 0 6px;border-bottom:2px solid #1a1a1a;padding-bottom:6px;">\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$",   r'<h1 style="font-size:24px;margin:0 0 20px;">\1</h1>', text, flags=re.MULTILINE)
    # HR
    text = re.sub(r"^---$", '<hr style="border:none;border-top:1px solid #ddd;margin:28px 0;">', text, flags=re.MULTILINE)
    # Paragraphs
    chunks = re.split(r"\n{2,}", text)
    parts = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("<h") or chunk.startswith("<hr"):
            parts.append(chunk)
        else:
            chunk = chunk.replace("\n", "<br>")
            parts.append(f'<p style="margin:0 0 16px;line-height:1.8;">{chunk}</p>')
    return "\n".join(parts)


def build_html_email(content_md: str, date_str: str) -> str:
    body_html = md_to_html(content_md)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>WorldExplainer — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f0ede8;font-family:Georgia,serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0ede8;padding:32px 0;">
  <tr><td align="center">
    <table width="660" cellpadding="0" cellspacing="0" style="max-width:660px;width:100%;background:#ffffff;">

      <!-- ── HEADER ─────────────────────────────────────────── -->
      <tr><td style="background:#111111;padding:32px 40px 28px;">
        <div style="font-family:Georgia,serif;font-size:30px;font-weight:bold;color:#ffffff;letter-spacing:3px;">
          WORLDEXPLAINER
        </div>
        <div style="font-family:'Helvetica Neue',Arial,sans-serif;font-size:11px;color:#888888;letter-spacing:2px;margin-top:6px;">
          {date_str.upper()} &nbsp;·&nbsp; WHAT THE NEWS GOT WRONG
        </div>
      </td></tr>

      <!-- ── INTRO STRIP ────────────────────────────────────── -->
      <tr><td style="background:#f7f4ef;padding:14px 40px;border-left:4px solid #111;">
        <p style="margin:0;font-family:'Helvetica Neue',Arial,sans-serif;font-size:13px;color:#555;line-height:1.6;">
          Every morning: the story beneath the story. Public misconceptions exposed,
          historical parallels drawn, uncomfortable theses defended.
        </p>
      </td></tr>

      <!-- ── BODY ───────────────────────────────────────────── -->
      <tr><td style="padding:36px 40px 24px;color:#1a1a1a;font-size:16px;">
        {body_html}
      </td></tr>

      <!-- ── FOOTER ─────────────────────────────────────────── -->
      <tr><td style="background:#111111;padding:20px 40px;">
        <p style="margin:0;font-family:'Helvetica Neue',Arial,sans-serif;font-size:11px;color:#666666;">
          WorldExplainer · Delivered daily at 06:00 UTC · Powered by Claude AI &amp; curated RSS
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def send_email(content_md: str, date_str: str) -> dict:
    ses = boto3.client("ses", region_name=os.environ.get("SES_REGION", "us-east-1"))
    html_body = build_html_email(content_md, date_str)

    return ses.send_email(
        Source=os.environ["SENDER_EMAIL"],
        Destination={"ToAddresses": [os.environ["RECIPIENT_EMAIL"]]},
        Message={
            "Subject": {"Data": f"WorldExplainer — {date_str}", "Charset": "UTF-8"},
            "Body": {
                "Html": {"Data": html_body,     "Charset": "UTF-8"},
                "Text": {"Data": content_md,    "Charset": "UTF-8"},
            },
        },
    )


def lambda_handler(event, context):
    print("WorldExplainer Lambda starting")
    headlines        = fetch_headlines()
    polish_headlines = fetch_polish_headlines()
    print(f"  global headlines: {len(headlines)}, polish: {len(polish_headlines)}")

    content_md, date_str = generate_analysis(headlines, polish_headlines)
    print(f"  analysis generated: {len(content_md)} chars")

    resp = send_email(content_md, date_str)
    msg_id = resp["MessageId"]
    print(f"  email sent: {msg_id}")

    return {"statusCode": 200, "body": json.dumps({"sent": True, "messageId": msg_id})}
