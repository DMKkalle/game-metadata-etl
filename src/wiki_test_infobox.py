import requests
import re
import sys

WIKI_API = "https://en.wikipedia.org/w/api.php"
START_TITLE = "Super Battletank 2"

ROLE_FIELDS = {
    "developer": "Developer(s)",
    "publisher": "Publisher(s)",
    "designer": "Designer(s)",
    "programmer": "Programmer(s)",
    "artist": "Artist(s)",
    "composer": "Composer(s)",
    "producer": "Producer(s)",
    "director": "Director(s)",
}

def fetch_wikitext(title, follow_redirect=True):
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "titles": title,
        "format": "json",
        "formatversion": "2",
        "redirects": 1,
    }
    resp = requests.get(
        WIKI_API,
        params=params,
        timeout=30,
        headers={
            "User-Agent": "Exjobb-Embracer-Research/0.1 (contact: dmkk@karlstad-university.example)"
        },
    )
    resp.raise_for_status()
    js = resp.json()
    pages = js.get("query", {}).get("pages", [])
    if not pages:
        return None, None

    page = pages[0]
    actual_title = page.get("title")
    revs = page.get("revisions", [])
    if not revs:
        return actual_title, None

    content = revs[0].get("slots", {}).get("main", {}).get("content", "")
    if not content:
        return actual_title, None

    # manual redirect fallback
    m = re.match(r"#REDIRECT\s*\[\[([^\]]+)\]\]", content, flags=re.IGNORECASE)
    if m and follow_redirect:
        new_title = m.group(1)
        return fetch_wikitext(new_title, follow_redirect=False)

    return actual_title, content


def extract_infobox(wikitext):
    """
    Försök hitta en infobox som börjar med:
      {{Infobox VG
      {{Infobox Video game
      {{Infobox video game
      {{Infobox ...
    Vi tar första {{Infobox ... }}-blocket där "VG" eller "video game"
    dyker upp direkt efter 'Infobox'.
    """
    # hitta alla möjliga startpositioner för "{{Infobox"
    candidates = [m.start() for m in re.finditer(r"\{\{[Ii]nfobox", wikitext)]
    if not candidates:
        return None

    for start_idx in candidates:
        # kolla om den texten ser ut som ett spel-info-box
        snippet = wikitext[start_idx:start_idx+40].lower()
        if "infobox vg" in snippet or "infobox video game" in snippet or "infobox vg" in snippet or "infobox vg" in snippet:
            # vi försöker parsa den här
            box = extract_template_block(wikitext, start_idx)
            if box:
                return box

    # fallback: om vi inte matchade heuristiken, men ändå hittade nån infobox,
    # ta första och hoppas
    return extract_template_block(wikitext, candidates[0])


def extract_template_block(text, start_idx):
    """
    Generisk template-parser: börja på '{{' och räkna klamrar tills nivå 0 igen.
    """
    i = start_idx
    brace_level = 0
    buf = []

    while i < len(text):
        if text.startswith("{{", i):
            brace_level += 1
            buf.append("{{")
            i += 2
            continue
        if text.startswith("}}", i):
            brace_level -= 1
            buf.append("}}")
            i += 2
            if brace_level == 0:
                break
            continue
        buf.append(text[i])
        i += 1

    result = "".join(buf)
    # sanity: ska börja med {{Infobox
    if not result.lower().startswith("{{infobox"):
        return None
    return result


def clean_value(val):
    # ta bort refs
    val = re.sub(r"<ref[^>]*>.*?</ref>", "", val, flags=re.DOTALL)
    val = re.sub(r"<ref[^/]*/>", "", val)
    # <br> -> komma
    val = re.sub(r"<br\s*/?>", ", ", val, flags=re.IGNORECASE)

    # [[Foo|Bar]] -> Bar, [[Foo]] -> Foo
    def repl_link(m):
        inner = m.group(1)
        parts = inner.split("|")
        return parts[-1]
    val = re.sub(r"\[\[([^\]]+)\]\]", repl_link, val)

    # [http://... Title] -> Title
    def repl_http(m):
        inner = m.group(1).strip()
        parts = inner.split(" ", 1)
        if len(parts) == 2:
            return parts[1]
        else:
            return parts[0]
    val = re.sub(r"\[([^\]]+)\]", repl_http, val)

    # ta bort andra templates {{...}} helt (t.ex. {{nowrap|...}})
    val = re.sub(r"\{\{[^\}]+\}\}", "", val)

    # whitespace cleanup
    val = re.sub(r"\s+", " ", val).strip()
    return val


def parse_infobox_roles(infobox_text):
    roles_out = {k: [] for k in ROLE_FIELDS.keys()}

    for raw_line in infobox_text.split("\n"):
        line = raw_line.strip()
        if not line.startswith("|"):
            continue

        # | programmer   = John Doe<br>Jane Doe
        m = re.match(r"^\|\s*([A-Za-z0-9_ ]+?)\s*=\s*(.+)$", line)
        if not m:
            continue

        raw_field = m.group(1).strip().lower()
        raw_val = m.group(2).strip()

        # mappa "programmer" / "programmers" -> programmer
        for role_key in ROLE_FIELDS.keys():
            if raw_field == role_key or raw_field == role_key + "s":
                cleaned = clean_value(raw_val)
                # dela upp på kommatecken
                parts = [p.strip(" ,") for p in cleaned.split(",") if p.strip(" ,")]
                roles_out[role_key].extend(parts)

    # dedupe
    for k, arr in roles_out.items():
        seen = set()
        uniq = []
        for person in arr:
            low = person.lower()
            if low not in seen and person != "":
                seen.add(low)
                uniq.append(person)
        roles_out[k] = uniq

    return roles_out


def main():
    print(f"[1] Hämtar wikiwikitext för '{START_TITLE}' ...")
    actual_title, wikitext = fetch_wikitext(START_TITLE)

    print(f"[1.1] Wikipedia gav titel: {actual_title!r}")
    if not wikitext:
        print("Ingen wikitext hittades 😭")
        sys.exit(0)

    print("\n[DEBUG] Första ~200 tecken av artikeln:\n--------------------------------")
    print(wikitext[:200])
    print("--------------------------------\n")

    print("[2] Letar infobox...")
    infobox = extract_infobox(wikitext)
    if not infobox:
        print("Fortfarande ingen infobox hittad 😬")
        sys.exit(0)

    print("[3] Extraherar roller ur infobox...")
    roles = parse_infobox_roles(infobox)

    print("\n=== RESULTAT ===")
    for role_key, human_label in ROLE_FIELDS.items():
        vals = roles[role_key]
        if vals:
            print(f"{role_key}: {', '.join(vals)}")

    print("\n---[Infobox Preview: top 30 rader]---")
    preview_lines = infobox.splitlines()[:30]
    for ln in preview_lines:
        print(ln)
    print("---[END preview]---")


if __name__ == "__main__":
    main()
