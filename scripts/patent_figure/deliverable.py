"""附图导出包的页面合成：规范版本 DXF → A4 页面栅格 → PDF / Word。

只服务 ``patent_figure.export``（单一导出服务）；读的是被钉住的版本目录里的 DXF，写的只在导出
包目录里。OCP 无关；栅格化用 ezdxf 的 matplotlib 后端（Agg，面向对象 API，不碰 pyplot 全局状态，
导出作业线程里安全），PDF 用 matplotlib 的 ``PdfPages``，Word 用可选依赖 python-docx。**出图链路
（DXF、N10 金样）一个字节都不受影响**：版式参数只在这里生效。

版式（任务书 F1，契约 §14.1）：

* A4（210×297 mm）竖放，页边 上 25 / 左 25 / 下 15 / 右 15 mm → 可用区 170×257 mm；
* 图区预设 ``standard`` = 170×257、``conservative`` = 165×245，居中放在可用区内；
* 每页一张图：取 DXF 全部图元的外廓（含图号、件号表，外扩 ``WINDOW_PAD_MM``）为取景窗，
  **不放大**——缩放比 = min(1, 图区宽/窗宽, 图区高/窗高)，所以字高只会不变或变小，由
  ``deliverable_check`` 逐页核验缩放后字高；
* 栅格 dpi 可配（默认 300，范围 72–600），灰度 8 位、白底黑线；
* 页序 = 图号序（图 1 … 图 n，即 plan.figures 的顺序；「图 N」已由标注步骤写进规范版本 DXF）。

精确图片参数以当期《电子申请文件格式要求说明》为准（``CNIPA_NOTE``，能力接口原样返回）。

Office profiles（首发收口）：纸张、页边、图区预设、图号格式、页码、最小字高、靶标都从
``profiles/<office>.json`` 读（``patent_figure.office``），``spec(..., office=)`` 带回来；本模块的
常数是 CNIPA 的值，也是 ``office=None`` 时的默认——``cnipa.json`` 与这些常数逐项一致，默认路径的
输出不变。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from patent_figure import layout as _layout
from patent_figure import office as _office
from patent_figure.mpl_lock import MPL_LOCK as _MPL_LOCK

PAGE_MM = (210.0, 297.0)
MARGINS_MM = {"top": 25.0, "left": 25.0, "bottom": 15.0, "right": 15.0}
SHEET_PRESETS = {
    "standard": {"area_mm": (170.0, 257.0), "label": "标准版心 170×257 mm"},
    "conservative": {"area_mm": (165.0, 245.0), "label": "保守版心 165×245 mm"},
}
DEFAULT_PRESET = "standard"
DEFAULT_DPI = 300
DPI_MIN, DPI_MAX = 72, 600
#: Clearance added around the drawing's ink extents to form the page's capture window (mm).
WINDOW_PAD_MM = 2.0
#: 缩放后最小字高（mm）：A16 / 审查指南五部一章 5.2 的 3.5 mm，与出图闸门同一常数。
MIN_TEXT_MM = float(_layout.TEXT_FLOOR_MM)
#: 栅格上最小字高（像素）。汉字笔画可辨约需 16 px 字身；A11 要求缩印到 2/3 仍清晰 →
#: 16 / (2/3) = 24 px。300 dpi 下 3.5 mm ≈ 41 px（通过），72 dpi 下 ≈ 9.9 px（不通过）。
MIN_TEXT_PX = 24.0
CNIPA_NOTE = "精确图片参数以当期《电子申请文件格式要求说明》为准"
#: Gray level (0–255) below which a pixel counts as ink.
INK_LEVEL = 128
#: Scan-target cross-hairs (37 CFR 1.84(g)): stroke width in PDF points. Drawn in the margins, BEFORE
#: the picture (the checker forbids painting after the image), only when the profile enables them.
TARGET_LW_PT = 0.5


class DeliverableError(RuntimeError):
    pass


def spec(preset: str = DEFAULT_PRESET, dpi: int = DEFAULT_DPI,
         office: Optional[str] = None) -> Dict[str, Any]:
    """Everything a page is built against and checked against (also the capabilities shape).
    ``office`` picks the profile (``profiles/<office>.json``; None = cnipa)."""
    try:
        prof = _office.load(office)
    except _office.OfficeError as exc:
        raise DeliverableError(str(exc))
    presets = prof["area_presets"]
    if preset not in presets:
        raise DeliverableError("未知图区预设 %r（%s 可选：%s）" % (preset, prof["office"],
                                                              "、".join(presets)))
    dpi = int(dpi)
    if not (DPI_MIN <= dpi <= DPI_MAX):
        raise DeliverableError("dpi 必须在 %d–%d 之间，收到 %d" % (DPI_MIN, DPI_MAX, dpi))
    aw, ah = (float(x) for x in presets[preset]["area_mm"])
    page = [float(x) for x in prof["paper"]["size_mm"]]
    margins = {k: float(prof["margins_mm"][k]) for k in ("top", "left", "bottom", "right")}
    note = CNIPA_NOTE if prof["office"] == _office.DEFAULT_OFFICE else (
        "Layout per %s; acceptance by the office is final, not legal advice." % prof.get("name", prof["office"]))
    return {"office": prof["office"], "paper": str(prof["paper"].get("name", "A4")),
            "page_mm": page, "margins_mm": margins, "preset": preset,
            "area_mm": [aw, ah], "dpi": dpi, "min_text_mm": float(prof["min_text_mm"]),
            "min_text_px": MIN_TEXT_PX, "window_pad_mm": WINDOW_PAD_MM, "note": note,
            "caption_format": str(prof["caption"]["format"]),
            "sheet_number": dict(prof["sheet_number"]), "targets": dict(prof["targets"]),
            "text_language": str(prof["text_language"])}


def printable_mm(sp: Optional[Dict[str, Any]] = None) -> Tuple[float, float]:
    page = sp["page_mm"] if sp else PAGE_MM
    m = sp["margins_mm"] if sp else MARGINS_MM
    return (page[0] - m["left"] - m["right"], page[1] - m["top"] - m["bottom"])


def target_segments_mm(sp: Dict[str, Any]) -> List[Tuple[float, float, float, float]]:
    """Cross-hair segments ``(x0, y0, x1, y1)`` in page mm (origin top-left) for the profile's
    target corners, centred in the margin corner; empty when the profile has no targets. Shared by
    the PDF writer and the checker's content-stream pattern."""
    t = sp.get("targets") or {}
    if not t.get("enabled"):
        return []
    pw, ph = sp["page_mm"]
    m = sp["margins_mm"]
    size = float(t.get("size_mm", 6.0))
    centres = {"top-left": (m["left"] / 2.0, m["top"] / 2.0),
               "top-right": (pw - m["right"] / 2.0, m["top"] / 2.0),
               "bottom-left": (m["left"] / 2.0, ph - m["bottom"] / 2.0),
               "bottom-right": (pw - m["right"] / 2.0, ph - m["bottom"] / 2.0)}
    segs = []
    for corner in t.get("corners", ("top-left", "bottom-right")):
        cx, cy = centres[corner]
        segs.append((cx - size / 2.0, cy, cx + size / 2.0, cy))
        segs.append((cx, cy - size / 2.0, cx, cy + size / 2.0))
    return segs


# --------------------------------------------------------------------------- DXF facts


def read_doc(dxf: Path):
    import ezdxf
    return ezdxf.readfile(str(dxf))


def sheet_window(msp, area_mm: Optional[Sequence[float]] = None
                 ) -> Tuple[float, float, float, float]:
    """The capture window (DXF mm): ink extents of every entity plus a clearance of up to
    ``WINDOW_PAD_MM`` per side — reduced (never below 0) on an axis where the full clearance
    would push a drawing that FITS the drawing area over it, so a fitting drawing is always
    placed 1:1 and its text heights are untouched. Shared by the writer and the checker; derived
    from the SOURCE drawing and the chosen preset only, never from what the writer reports."""
    from ezdxf import bbox
    ext = bbox.extents(msp)
    if not ext.has_data:
        raise DeliverableError("DXF 里没有任何图元")
    x0, y0 = float(ext.extmin.x), float(ext.extmin.y)
    x1, y1 = float(ext.extmax.x), float(ext.extmax.y)
    px = py = WINDOW_PAD_MM
    if area_mm is not None:
        aw, ah = float(area_mm[0]), float(area_mm[1])
        if x1 - x0 <= aw:
            px = max(0.0, min(px, (aw - (x1 - x0)) / 2.0))
        if y1 - y0 <= ah:
            py = max(0.0, min(py, (ah - (y1 - y0)) / 2.0))
    return (x0 - px, y0 - py, x1 + px, y1 + py)


def text_heights(msp) -> List[Tuple[str, str, float]]:
    """(layer, text, height mm) of every TEXT / MTEXT in the drawing."""
    out = []
    for e in msp:
        kind = e.dxftype()
        if kind == "TEXT":
            out.append((str(e.dxf.layer), str(e.dxf.text), float(e.dxf.height)))
        elif kind == "MTEXT":
            out.append((str(e.dxf.layer), str(e.text), float(e.dxf.get("char_height", 0.0))))
    return out


def caption_of(msp) -> Optional[Dict[str, Any]]:
    """The figure-number caption (CAPTION layer TEXT): text, anchor and alignment."""
    from patent_figure import qa as _qa
    for e in msp:
        if e.dxftype() in ("TEXT", "MTEXT") and str(e.dxf.layer) == "CAPTION":
            payload = _qa._text_payload(e)
            if payload:
                text, h, anchor, hk, vk = payload
                return {"text": text.strip(), "height": h, "anchor": anchor, "h": hk, "v": vk}
    return None


def caption_box(cap: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """A box (DXF mm) that certainly overlaps the caption glyphs: CJK-aware width estimate,
    then the central 80 % (so a generous estimate cannot reach neighbouring ink)."""
    h = float(cap["height"])
    tw = sum((0.62 if ord(c) < 0x2E80 else 1.0) for c in cap["text"]) * h
    ax, ay = cap["anchor"]
    x0 = ax - tw if cap["h"] == "R" else (ax - tw / 2.0 if cap["h"] == "C" else ax)
    yc = ay if cap["v"] == "MID" else (ay - h / 2.0 if cap["v"] == "TOP" else ay + h / 2.0)
    box = (x0, yc - h / 2.0, x0 + tw, yc + h / 2.0)
    cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    return (cx - 0.4 * (box[2] - box[0]), cy - 0.4 * (box[3] - box[1]),
            cx + 0.4 * (box[2] - box[0]), cy + 0.4 * (box[3] - box[1]))


def place(window: Sequence[float], sp: Dict[str, Any]) -> Dict[str, float]:
    """Page placement (mm, origin top-left) of a capture window under preset ``sp``."""
    ww, wh = window[2] - window[0], window[3] - window[1]
    aw, ah = sp["area_mm"]
    pw, ph = printable_mm(sp if "page_mm" in sp else None)
    m = sp.get("margins_mm", MARGINS_MM)
    scale = min(1.0, aw / ww, ah / wh)
    iw, ih = ww * scale, wh * scale
    ax0 = m["left"] + (pw - aw) / 2.0
    at0 = m["top"] + (ph - ah) / 2.0
    return {"scale": scale, "w": iw, "h": ih,
            "x": ax0 + (aw - iw) / 2.0, "top": at0 + (ah - ih) / 2.0,
            "area_x": ax0, "area_top": at0}


# --------------------------------------------------------------------------- raster


class Page:
    """One rasterised page: the gray image + where it goes + the facts it was built from."""

    def __init__(self, figure: str, number: int, dxf: Path, gray, window, placement, dpi,
                 sp: Optional[Dict[str, Any]] = None):
        self.figure, self.number, self.dxf = figure, number, Path(dxf)
        self.gray, self.window, self.placement, self.dpi = gray, window, placement, dpi
        self.sp = sp                                  # the spec the page was placed under

    def png_bytes(self) -> bytes:
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(self.gray, "L").save(buf, "PNG", dpi=(self.dpi, self.dpi))
        return buf.getvalue()


#: R2l / R2m: matplotlib is not thread-safe and the service runs exports, lazy PNG previews and
#: MCP flowchart renders in concurrent threads (concurrent exports failed at random with
#: "生成失败：cmap"). ``rasterize`` and ``write_pdf`` hold the ONE process-wide lock that
#: ``sheet.render_preview`` holds too (``patent_figure.mpl_lock``).
MPL_LOCK = _MPL_LOCK


def rasterize(dxf: Path, sp: Dict[str, Any], figure: str = "", number: int = 0) -> Page:
    """Render the DXF's capture window to a gray raster of exactly the placed size at ``dpi``
    (under ``MPL_LOCK``)."""
    with MPL_LOCK:
        return _rasterize(dxf, sp, figure, number)


def _rasterize(dxf: Path, sp: Dict[str, Any], figure: str = "", number: int = 0) -> Page:
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from patent_figure import sheet as _sheet

    _sheet._preview_cjk_font()
    doc = read_doc(dxf)
    msp = doc.modelspace()
    win = sheet_window(msp, sp["area_mm"])
    pl = place(win, sp)
    dpi = int(sp["dpi"])
    wpx = max(1, int(round(pl["w"] / 25.4 * dpi)))
    hpx = max(1, int(round(pl["h"] / 25.4 * dpi)))
    # Agg truncates the figure size to whole pixels, and wpx/dpi*dpi can come back as wpx-1e-12.
    # Make the figure half a pixel larger and pin the axes to EXACTLY wpx × hpx pixels from the
    # bottom-left, so the window → pixel mapping is exact and the canvas is wpx × hpx.
    fig = Figure(figsize=((wpx + 0.5) / float(dpi), (hpx + 0.5) / float(dpi)), dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_axes([0.0, 0.0, wpx / (wpx + 0.5), hpx / (hpx + 0.5)])
    ax.set_axis_off()
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE,
                        color_policy=ColorPolicy.BLACK)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(
        msp, finalize=False)
    ax.set_xlim(win[0], win[2])
    ax.set_ylim(win[1], win[3])
    ax.set_aspect("auto")
    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba())
    if rgba.shape[0] >= hpx and rgba.shape[1] >= wpx:
        rgba = rgba[rgba.shape[0] - hpx:, :wpx]          # keep the bottom-left wpx × hpx
    if rgba.shape[0] != hpx or rgba.shape[1] != wpx:
        raise DeliverableError("栅格尺寸 %s 与版式 %dx%d 不符" % (rgba.shape[:2], hpx, wpx))
    gray = ((rgba[..., 0].astype(np.uint32) * 299 + rgba[..., 1].astype(np.uint32) * 587
             + rgba[..., 2].astype(np.uint32) * 114) // 1000).astype(np.uint8)
    return Page(figure, number, dxf, gray, win, pl, dpi, sp)


# --------------------------------------------------------------------------- writers


def write_pdf(pages: Sequence[Page], path: Path, title: str = "说明书附图") -> Path:
    """One A4 page per figure, the raster placed at its page rectangle (native resolution:
    ``interpolation='none'`` makes the PDF backend embed the image unsampled). Under
    ``MPL_LOCK``."""
    with MPL_LOCK:
        return _write_pdf(pages, path, title)


def _write_pdf(pages: Sequence[Page], path: Path, title: str = "说明书附图") -> Path:
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    sp0 = next((pg.sp for pg in pages if pg.sp), None)
    pw, ph = sp0["page_mm"] if sp0 else PAGE_MM
    targets = target_segments_mm(sp0) if sp0 else []
    try:
        with PdfPages(str(tmp), metadata={"Title": title, "Creator": "patent-figure-kit",
                                          "Producer": "patent-figure-kit", "CreationDate": None,
                                          "ModDate": None}) as pdf:
            for page in pages:
                pl = page.placement
                fig = Figure(figsize=(pw / 25.4, ph / 25.4), dpi=72)
                for (x0, y0, x1, y1) in targets:      # margins, painted BEFORE the picture
                    fig.add_artist(Line2D([x0 / pw, x1 / pw], [1.0 - y0 / ph, 1.0 - y1 / ph],
                                          transform=fig.transFigure, color="k",
                                          linewidth=TARGET_LW_PT, solid_capstyle="butt",
                                          zorder=0))
                ax = fig.add_axes([pl["x"] / pw, (ph - pl["top"] - pl["h"]) / ph,
                                   pl["w"] / pw, pl["h"] / ph])
                if targets:
                    ax.set_zorder(1)
                ax.set_axis_off()
                ax.imshow(page.gray, cmap="gray", vmin=0, vmax=255, interpolation="none",
                          aspect="auto")
                pdf.savefig(fig)
        tmp.replace(path)
    finally:                                  # a failed write never leaves a .tmp in the bundle
        if tmp.exists():
            tmp.unlink()
    return path


# --------------------------------------------------------------------------- Word (fixed package)
#
# WP2 R2d: the Word file is written from FIXED templates — every part of the package is ours,
# byte for byte (no python-docx default template with its mutable styles, theme, settings…).
# ``deliverable_check`` rebuilds the expected bytes of every non-media part from the values it
# reads back (picture extents, title) and requires an EXACT match: a closed set by construction,
# so an inherited/hidden/unknown property anywhere in the package cannot pass.

_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
EMU_PER_MM = 36000
DOCX_TITLES = ("说明书附图", "说明书附图（递交版）", "说明书附图（交底版）")


def _twips(mm: float) -> int:
    return int(round(mm * 1440.0 / 25.4))


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def docx_content_types() -> str:
    return (_XML_HEAD + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '</Types>')


def docx_package_rels() -> str:
    return (_XML_HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="%s/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>' % _REL)


def docx_document_rels(n: int) -> str:
    imgs = "".join('<Relationship Id="rIdImg%d" Type="%s/image" Target="media/image%d.png"/>'
                   % (k, _REL, k) for k in range(1, n + 1))
    return (_XML_HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdStyles" Type="%s/styles" Target="styles.xml"/>'
            '<Relationship Id="rIdSettings" Type="%s/settings" Target="settings.xml"/>%s'
            '</Relationships>' % (_REL, _REL, imgs))


def docx_styles() -> str:
    """Document defaults + Normal, nothing else. Character defaults are stated explicitly and
    visible (no vanish / webHidden / colour / size games); paragraph defaults are single-spaced
    with no space before/after."""
    return (_XML_HEAD + '<w:styles xmlns:w="%s"><w:docDefaults>'
            '<w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
            'w:eastAsia="SimSun" w:cs="Times New Roman"/><w:vanish w:val="0"/>'
            '<w:webHidden w:val="0"/><w:color w:val="000000"/><w:sz w:val="21"/>'
            '<w:szCs w:val="21"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN" w:bidi="ar-SA"/>'
            '</w:rPr></w:rPrDefault>'
            '<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" '
            'w:lineRule="auto"/><w:ind w:left="0" w:right="0" w:firstLine="0"/></w:pPr>'
            '</w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
            '<w:qFormat/></w:style></w:styles>' % _NS_W)


def docx_settings() -> str:
    return (_XML_HEAD + '<w:settings xmlns:w="%s"><w:defaultTabStop w:val="420"/>'
            '<w:characterSpacingControl w:val="doNotCompress"/><w:compat>'
            '<w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" '
            'w:val="15"/></w:compat></w:settings>' % _NS_W)


def docx_core(title: str) -> str:
    return (_XML_HEAD + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>%s</dc:title>'
            '<dc:creator>patent-figure-kit</dc:creator></cp:coreProperties>' % _esc(title))


def docx_document(extents: Sequence[Tuple[int, int]], page_mm: Sequence[float] = PAGE_MM,
                  margins: Optional[Dict[str, float]] = None) -> str:
    """One page paragraph per picture: page break before every page but the first, explicit
    single spacing, zero indents, centred, the paragraph mark and the picture run explicitly
    visible, one inline picture whose transform equals its extent. Section: the profile's page
    (A4 by default) portrait with the filing margins, no header/footer."""
    m = margins or MARGINS_MM
    paras = []
    for k, (cx, cy) in enumerate(extents, start=1):
        paras.append(
            '<w:p><w:pPr>%s<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
            '<w:ind w:left="0" w:right="0" w:firstLine="0"/><w:jc w:val="center"/>'
            '<w:rPr><w:vanish w:val="0"/><w:webHidden w:val="0"/></w:rPr></w:pPr>'
            '<w:r><w:rPr><w:vanish w:val="0"/><w:webHidden w:val="0"/></w:rPr><w:drawing>'
            '<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="%d" cy="%d"/>'
            '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
            '<wp:docPr id="%d" name="图%d" descr="图%d"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic><a:graphicData uri="%s"><pic:pic><pic:nvPicPr>'
            '<pic:cNvPr id="%d" name="image%d.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            '<pic:blipFill><a:blip r:embed="rIdImg%d"/><a:stretch><a:fillRect/></a:stretch>'
            '</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData>'
            '</a:graphic></wp:inline></w:drawing></w:r></w:p>'
            % ("<w:pageBreakBefore/>" if k > 1 else "", cx, cy, k, k, k, _NS_PIC, k, k, k,
               cx, cy))
    sect = ('<w:sectPr><w:pgSz w:w="%d" w:h="%d"/><w:pgMar w:top="%d" w:right="%d" '
            'w:bottom="%d" w:left="%d" w:header="0" w:footer="0" w:gutter="0"/>'
            '<w:cols w:space="425"/><w:docGrid w:linePitch="360"/></w:sectPr>'
            % (_twips(page_mm[0]), _twips(page_mm[1]), _twips(m["top"]), _twips(m["right"]),
               _twips(m["bottom"]), _twips(m["left"])))
    return (_XML_HEAD + '<w:document xmlns:w="%s" xmlns:r="%s" xmlns:wp="%s" xmlns:a="%s" '
            'xmlns:pic="%s"><w:body>%s%s</w:body></w:document>'
            % (_NS_W, _NS_R, _NS_WP, _NS_A, _NS_PIC, "".join(paras), sect))


def docx_parts(extents: Sequence[Tuple[int, int]], title: str,
               page_mm: Sequence[float] = PAGE_MM,
               margins: Optional[Dict[str, float]] = None) -> Dict[str, bytes]:
    """Every non-media part of the package, exactly as written (and as the checker expects)."""
    return {"[Content_Types].xml": docx_content_types().encode("utf-8"),
            "_rels/.rels": docx_package_rels().encode("utf-8"),
            "docProps/core.xml": docx_core(title).encode("utf-8"),
            "word/document.xml": docx_document(extents, page_mm, margins).encode("utf-8"),
            "word/_rels/document.xml.rels": docx_document_rels(len(extents)).encode("utf-8"),
            "word/styles.xml": docx_styles().encode("utf-8"),
            "word/settings.xml": docx_settings().encode("utf-8")}


def docx_available() -> bool:
    """The Word writer is stdlib-only since R2d (fixed package templates); Pillow (a matplotlib
    dependency) encodes the page PNGs."""
    return True


def write_docx(pages: Sequence[Page], path: Path, title: str = "说明书附图") -> Path:
    """Word：A4、规范页边、每页一张居中嵌入式图片（第 2 页起段前分页），图片按版面尺寸精确放置。
    整个包由固定模板写出（见上），不依赖 python-docx 的默认模板。"""
    import zipfile
    if title not in DOCX_TITLES:
        raise DeliverableError("未知的 Word 标题 %r" % title)
    extents = [(int(round(pg.placement["w"] * EMU_PER_MM)),
                int(round(pg.placement["h"] * EMU_PER_MM))) for pg in pages]
    sp0 = next((pg.sp for pg in pages if pg.sp), None)
    parts = docx_parts(extents, title, sp0["page_mm"] if sp0 else PAGE_MM,
                       sp0["margins_mm"] if sp0 else None)
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        # A .docx is a zip CONTAINER of one document (not an export archive): the export
        # archive itself is still written only by patent_figure.export.zip_dir.
        with zipfile.ZipFile(str(tmp), "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ("[Content_Types].xml", "_rels/.rels", "docProps/core.xml",
                         "word/document.xml", "word/_rels/document.xml.rels",
                         "word/styles.xml", "word/settings.xml"):
                zf.writestr(name, parts[name])
            for k, pg in enumerate(pages, start=1):
                zf.writestr("word/media/image%d.png" % k, pg.png_bytes())
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path
