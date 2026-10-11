"""Render the Team Scores card in headless Chrome at phone width, from recorded sensor states, and save a screenshot.

The page inlines the card script and the states (file:// pages cannot fetch), fakes the bit of `hass` the card
reads (states, locale, config), and prints script errors into the page so they show in the screenshot.

    python tests/render_card.py [states.json] -> tests/card_render.png
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CARD = os.path.join(ROOT, "custom_components", "sportsdb_tracker", "www", "team-scores-card.js")
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]


def main():
    states_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "fixtures_states.json")
    states = {s["entity_id"]: s for s in json.load(open(states_path, encoding="utf-8"))}
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>body{{margin:0;background:#111;color:#eee;font-family:Roboto,Segoe UI,sans-serif;
--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--divider-color:rgba(225,225,225,0.12);--error-color:#db4437;
--secondary-background-color:#2b2b2b}} ha-card{{display:block;background:#1c1c1c;border-radius:12px;margin:8px}}
#err{{color:#f66;white-space:pre-wrap;padding:8px}}</style></head><body><div id="err"></div>
<script>window.onerror=function(m,s,l){{document.getElementById('err').textContent+=m+' @'+l+'\\n'}}</script>
<script>{open(CARD, encoding="utf-8").read()}</script>
<script>
const states={json.dumps(states)};
const hass={{states, locale:{{language:"en-GB", time_format:"24", time_zone:"server"}}, config:{{time_zone:"Europe/Oslo"}}}};
const card=document.createElement("team-scores-card");
card.setConfig({{title:"Scores"}});
const wrap=document.createElement("div"); wrap.style.width="384px"; wrap.style.overflow="hidden"; wrap.style.outline="1px solid #444"; document.body.appendChild(wrap); wrap.appendChild(card);
card.hass=hass;
</script></body></html>"""
    html = os.path.join(HERE, "card_render.html")
    open(html, "w", encoding="utf-8").write(page)
    out = os.path.join(HERE, "card_render.png").replace("\\", "/")
    url = "file:///" + html.replace("\\", "/")
    for browser in BROWSERS:
        if not os.path.exists(browser):
            continue
        profile = tempfile.mkdtemp(prefix="card-")
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                        "--window-size=400,1700", f"--screenshot={out}", url], capture_output=True, timeout=90)
        shutil.rmtree(profile, ignore_errors=True)
        if os.path.exists(out):
            print("rendered with", os.path.basename(browser), "->", out)
            return
    raise SystemExit("no browser produced a screenshot")


if __name__ == "__main__":
    main()
