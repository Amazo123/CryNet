"""Build SYSTEM_WIRING_DIAGRAMS.html and its PDF from the page modules.

    python tools/wiring/build.py            # html + pdf
    python tools/wiring/build.py --check    # layout check only

The layout is generated rather than hand-written because the previous
hand-written SVG had wires running through labels.  Every page now runs
through diagram_lib.Page.check(), which fails the build if a label
overlaps another label, sits on a component, or has a wire crossing it.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_HTML = os.path.join(ROOT, "SYSTEM_WIRING_DIAGRAMS.html")
OUT_PDF = os.path.join(ROOT, "SYSTEM_WIRING_DIAGRAMS.pdf")

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CSS = """
@page{size:A4 landscape;margin:10mm}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,Helvetica,sans-serif;color:#182638}
.page{min-height:188mm;break-after:page;page-break-after:always;position:relative}
.page:last-child{break-after:auto;page-break-after:auto}
h1{font-size:19px;margin:0 0 3px}
h2{font-size:13px;margin:0 0 4px;color:#35506a}
.sub{font-size:11px;margin:0 0 4px;color:#5b6b7c}
.foot{position:absolute;bottom:0;font-size:10px;border-top:1px solid #aaa;
      padding-top:4px;width:100%;color:#33465c}
.warning{background:#fff2d3;border-left:5px solid #cc8b18;padding:6px;
         font-size:10.5px;line-height:1.3;margin-top:4px}
.ok{background:#e7f5ee;border-left:5px solid #25865f;padding:5px;
    font-size:10.5px;line-height:1.3;margin-top:4px}
.legend{font-size:10px;color:#33465c;margin-top:3px}
svg.diagram{width:100%;height:auto;display:block}
svg text{font-family:Arial,Helvetica,sans-serif;font-size:13px;fill:#142638}
svg text.title{font-size:15px;font-weight:bold}
svg text.pin{font-family:Consolas,'Courier New',monospace;font-size:12.5px;
             font-weight:bold}
svg text.mono{font-family:Consolas,'Courier New',monospace}
svg text.small{font-size:11px}
svg text.note{font-size:12px}
.board{fill:#edf5fb;stroke:#345775;stroke-width:2}
.mod{fill:#eef8f2;stroke:#31765d;stroke-width:2}
.proposed{fill:#fff8e8;stroke:#b47b17;stroke-width:2;stroke-dasharray:8 5}
.part{fill:#ffffff;stroke:#5b6b7c;stroke-width:1.5}
.panel{fill:#f6f8fa;stroke:#8fa3b5;stroke-width:1.5;stroke-dasharray:5 4}
.wire{fill:none;stroke-linecap:round;stroke-linejoin:round}
.red{stroke:#c43e39}.black{stroke:#28323d}.blue{stroke:#3166bb}
.green{stroke:#298560}.orange{stroke:#dd861d}.purple{stroke:#8759a9}
.teal{stroke:#15979c}.brown{stroke:#8a6348}.grey{stroke:#7b8794}
.dot{fill:#28323d}
"""

WIRE_HEX = {
    "red": "#c43e39", "black": "#28323d", "blue": "#3166bb",
    "green": "#298560", "orange": "#dd861d", "purple": "#8759a9",
    "teal": "#15979c", "brown": "#8a6348", "grey": "#7b8794",
}


def page_section(page, notes_html, foot_html):
    """Wrap a diagram_lib.Page into a printable section."""
    return ("<section class=\"page\">"
            "<h1>%s</h1>"
            "<h2>%s</h2>"
            "%s"
            "%s"
            "<div class=\"foot\">%s</div>"
            "</section>" % (page.title, page.subtitle or "",
                            page.svg(), notes_html, foot_html))


def build_html(pages):
    body = []
    for page, notes, foot in pages:
        body.append(page_section(page, notes, foot))
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>CryNet battery wiring diagrams</title><style>%s</style>"
            "</head><body>\n%s\n</body></html>\n" % (CSS, "\n".join(body)))


def main():
    import page_overview
    import page_node
    import page_hub
    import page_wearable
    import page_haptic
    import page_padmap

    pages = []
    for mod in (page_overview, page_node, page_hub, page_wearable,
                page_haptic, page_padmap):
        pages.append(mod.build())

    for page, _notes, _foot in pages:
        page.check()

    html = build_html(pages)
    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote %s (%d bytes)" % (OUT_HTML, len(html)))

    if "--check" in sys.argv:
        return 0

    if not os.path.exists(CHROME):
        print("chrome not found at %s - HTML written, PDF skipped" % CHROME)
        return 1
    subprocess.check_call([
        CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        "--print-to-pdf=" + OUT_PDF, "file:///" + OUT_HTML.replace("\\", "/"),
    ])
    print("wrote %s (%d bytes)" % (OUT_PDF, os.path.getsize(OUT_PDF)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
