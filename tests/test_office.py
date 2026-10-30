"""Office profiles（首发收口 · USPTO 最小版）：profiles/<office>.json 驱动图号、页码、页边、最小字高、靶标。

守住两件事：

1. ``cnipa.json`` 与 ``layout.py`` / ``deliverable.py`` 的冻结常数逐项一致——默认路径一个字节不变（N10 金样）；
2. ``uspto`` 真能走通：标注出「FIG. N」与「n/total」，PDF / Word 在 1.84(g) 的页边与 17.0×26.2 cm 图区内、
   带十字靶标、图号与页码落在页面上、逐页核验通过；而用 cnipa 的尺子去量 uspto 的文件必须判不通过。

OCP 无关：图纸用 ezdxf 现造（与 tests/test_deliverable.py 同一套最小图）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

ezdxf = pytest.importorskip("ezdxf")
pytest.importorskip("matplotlib")

from ezdxf.enums import TextEntityAlignment  # noqa: E402

from patent_figure import deliverable as D  # noqa: E402
from patent_figure import deliverable_check as C  # noqa: E402
from patent_figure import layout as L  # noqa: E402
from patent_figure import office as O  # noqa: E402

ANNOTATE = _ROOT / "scripts" / "annotate_figure_sheet.py"


# --------------------------------------------------------------------------- profiles


def test_profiles_exist_and_validate():
    assert O.list_offices() == ["cnipa", "uspto"]
    for name in O.list_offices():
        prof = O.load(name)
        assert prof["schema"] == O.SCHEMA_ID and prof["office"] == name
        assert prof["_sources"] and prof["_verified"], "每个 profile 必须写条款出处与核对日期"
        for src in prof["_sources"]:
            assert src.get("cite"), src
    with pytest.raises(O.OfficeError):
        O.load("epo")
    with pytest.raises(D.DeliverableError):
        D.spec("standard", 300, "epo")


def test_cnipa_profile_matches_the_frozen_constants():
    """改 profile 不改金样：默认 spec 与 cnipa.json 与模块常数三者一致。"""
    prof = O.load("cnipa")
    assert prof["paper"]["size_mm"] == list(D.PAGE_MM)
    assert prof["margins_mm"] == D.MARGINS_MM
    assert {k: v["area_mm"] for k, v in prof["area_presets"].items()} == \
        {k: list(v["area_mm"]) for k, v in D.SHEET_PRESETS.items()}
    assert prof["default_preset"] == D.DEFAULT_PRESET
    assert prof["min_text_mm"] == D.MIN_TEXT_MM == L.TEXT_FLOOR_MM == 3.5
    assert O.caption("cnipa", 3) == "图3"
    assert O.sheet_number("cnipa", 1, 3) is None
    assert O.description_line("cnipa", 2, "回转组件分解示意图") == "图2为回转组件分解示意图；"
    assert D.target_segments_mm(D.spec()) == []
    sp, sp_default = D.spec("standard", 300, "cnipa"), D.spec()
    assert sp == sp_default and sp["office"] == "cnipa" and sp["note"] == D.CNIPA_NOTE
    assert sp["page_mm"] == [210.0, 297.0] and sp["area_mm"] == [170.0, 257.0]
    # 页面放置与纸张常数同源：默认 spec 下 printable_mm 两种调用一致
    assert D.printable_mm() == D.printable_mm(sp)


def test_uspto_profile_values_follow_37_cfr_1_84():
    prof = O.load("uspto")
    assert prof["margins_mm"] == {"top": 25.0, "left": 25.0, "bottom": 10.0, "right": 15.0}  # 1.84(g)
    assert prof["area_presets"]["standard"]["area_mm"] == [170.0, 262.0]                  # sight on A4
    assert prof["min_text_mm"] == 3.2                                                      # 1.84(p)(3)
    assert O.caption("uspto", 1) == "FIG. 1"                                               # 1.84(u)
    assert O.sheet_number("uspto", 2, 5) == "2/5"                                           # 1.84(t)
    assert O.description_line("uspto", 1, "a perspective view") == "FIG. 1 is a perspective view;"
    assert O.text_allowed("uspto", "FIG. 1") and not O.text_allowed("uspto", "图1")
    assert O.text_allowed("cnipa", "图1")
    assert O.qa_thresholds("uspto") == {"text_height_mm_min": 3.2}
    assert "shading" in prof["not_in_this_profile"] and "color" in prof["not_in_this_profile"]
    sp = D.spec("standard", 300, "uspto")
    segs = D.target_segments_mm(sp)
    assert len(segs) == 4                                                                  # 两对角十字
    for x0, y0, x1, y1 in segs:                      # 全部落在页边之内（不在图区）
        assert max(x0, x1) <= 25.0 or min(x0, x1) >= 210.0 - 15.0
        assert max(y0, y1) <= 25.0 or min(y0, y1) >= 297.0 - 10.0
    summ = O.summary("uspto")
    assert summ["targets"] is True and summ["caption_format"] == "FIG. {n}"


# --------------------------------------------------------------------------- annotate


def _raw_sheet(path: Path, h: float = 3.5) -> None:
    doc = ezdxf.new("R2018")
    for name in ("GEOM", "LEADER", "NUM", "CAPTION"):
        doc.layers.add(name)
    doc.styles.add("HZ", font="simfang.ttf")
    doc.styles.add("NUM", font="txt.shx")
    msp = doc.modelspace()
    msp.add_lwpolyline([(30, 40), (140, 40), (140, 200), (30, 200)], close=True,
                       dxfattribs={"layer": "GEOM"})
    msp.add_line((140, 120), (150, 120), dxfattribs={"layer": "LEADER"})
    t = msp.add_text("1", dxfattribs={"layer": "NUM", "height": h, "style": "NUM"})
    t.set_placement((152, 120), align=TextEntityAlignment.MIDDLE_LEFT)
    cap = msp.add_text("整体结构示意图", height=1.6 * h, dxfattribs={"layer": "CAPTION", "style": "HZ"})
    cap.set_placement((85.0, 8.0), align=TextEntityAlignment.MIDDLE_CENTER)
    doc.saveas(str(path))


def _numerals(path: Path) -> None:
    path.write_text(json.dumps({"schema": "patent-numerals/1", "numerals": [
        {"numeral": 1, "term": "housing", "selector": "SYN-1", "figures": ["fig1"]}]}),
        encoding="utf-8")


def _texts(path: Path, layer: str):
    return [e.dxf.text for e in ezdxf.readfile(str(path)).modelspace().query("TEXT")
            if e.dxf.layer == layer]


@pytest.mark.parametrize("office,caption,sheet", [("cnipa", "图2", []), ("uspto", "FIG. 2", ["2/3"])])
def test_annotate_writes_the_offices_caption_and_sheet_number(tmp_path, office, caption, sheet):
    src, num = tmp_path / "fig2.dxf", tmp_path / "num.json"
    _raw_sheet(src)
    _numerals(num)
    out = tmp_path / "fig2_filing.dxf"
    rep = tmp_path / "rep.json"
    proc = subprocess.run([sys.executable, str(ANNOTATE), str(src), "--numerals", str(num),
                           "--figure-number", "2", "--sheet-total", "3", "--office", office,
                           "--no-table", "-o", str(out), "--json", str(rep)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert _texts(out, "CAPTION") == [caption]
    assert _texts(out, O.SHEET_LAYER) == sheet
    r = json.loads(rep.read_text(encoding="utf-8"))
    assert r["office"] == office and r["caption"] == caption
    assert r["sheet_number"] == (sheet[0] if sheet else None)
    assert r["figure_description"] == O.description_line(office, 2, "整体结构示意图")
    # 页码在图幅上沿之外、顶部居中，且不低于图号字高（1.84(t)：须大于附图标记）
    if sheet:
        sn = next(e for e in ezdxf.readfile(str(out)).modelspace().query("TEXT")
                  if e.dxf.layer == O.SHEET_LAYER)
        x, y = sn.get_placement()[1].x, sn.get_placement()[1].y
        assert abs(x - L.FRAME_W / 2) < 1e-6 and y > L.FRAME_H
        assert sn.dxf.height >= 5.0 > 3.5


def test_annotate_without_sheet_total_adds_no_sheet_number_even_for_uspto(tmp_path):
    src, num = tmp_path / "fig1.dxf", tmp_path / "num.json"
    _raw_sheet(src)
    _numerals(num)
    out = tmp_path / "fig1_filing.dxf"
    proc = subprocess.run([sys.executable, str(ANNOTATE), str(src), "--numerals", str(num),
                           "--figure-number", "1", "--office", "uspto", "--no-table",
                           "-o", str(out)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert _texts(out, "CAPTION") == ["FIG. 1"] and _texts(out, O.SHEET_LAYER) == []


# --------------------------------------------------------------------------- deliverable


def _filing_sheet(path: Path, number: int, office: str, total: int = 2, height: float = 180.0,
                  text_h: float = 3.5) -> Path:
    """A minimal FILING sheet in the office's wording (what annotate would have produced)."""
    doc = ezdxf.new("R2018")
    for name in ("GEOM", "LEADER", "NUM", "CAPTION", O.SHEET_LAYER):
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_lwpolyline([(30, 30), (140, 30), (140, 30 + height), (30, 30 + height)],
                       close=True, dxfattribs={"layer": "GEOM"})
    msp.add_line((140, 100), (152, 100), dxfattribs={"layer": "LEADER"})
    t = msp.add_text("1", dxfattribs={"layer": "NUM", "height": text_h})
    t.set_placement((155, 100), align=TextEntityAlignment.MIDDLE_LEFT)
    c = msp.add_text(O.caption(office, number), dxfattribs={"layer": "CAPTION", "height": 5.0})
    c.set_placement((85, 15), align=TextEntityAlignment.MIDDLE_CENTER)
    sn = O.sheet_number(office, number, total)
    if sn:
        s = msp.add_text(sn, dxfattribs={"layer": O.SHEET_LAYER, "height": 5.0})
        s.set_placement((85, 30 + height + 12), align=TextEntityAlignment.MIDDLE_CENTER)
    doc.saveas(str(path))
    return path


def _build_and_check(tmp_path: Path, office: str, fmt: str, check_office: str = None):
    rows = [{"figure": "fig%d" % k, "number": k,
             "dxf": _filing_sheet(tmp_path / ("fig%d_filing.dxf" % k), k, office)} for k in (1, 2)]
    sp = D.spec("standard", 300, office)
    pages = [D.rasterize(r["dxf"], sp, r["figure"], r["number"]) for r in rows]
    out = tmp_path / ("%s.%s" % (office, fmt))
    (D.write_pdf if fmt == "pdf" else D.write_docx)(pages, out)
    sp_check = D.spec("standard", 300, check_office or office)
    sp_check["language_check"] = True
    return C.check_document(out, C.sources_from(rows, sp_check["area_mm"]), sp_check), pages


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_uspto_documents_pass_their_own_profile_check(tmp_path, monkeypatch, fmt):
    pytest.importorskip("pypdf")
    pytest.importorskip("pypdfium2")
    monkeypatch.setenv("PFK_PDF_RENDERER", "pypdfium2")
    rep, pages = _build_and_check(tmp_path, "uspto", fmt)
    assert rep["ok"] is True and rep["status"] == C.STATUS_OK, (rep["errors"], [p["errors"] for p in rep["page_checks"]])
    p1, p2 = rep["page_checks"]
    assert p1["caption"] == "FIG. 1" and p2["caption"] == "FIG. 2"
    assert p1["caption_ink"] > C.INK_FRACTION_MIN
    # 1.84(g)：上/左 ≥ 25、右 ≥ 15、下 ≥ 10 mm；图片在 17.0×26.2 cm 图区内
    img = p1["image_mm"]
    assert img["left"] >= 25 - 0.5 and img["top"] >= 25 - 0.5
    assert img["left"] + img["width"] <= 210 - 15 + 0.5
    assert img["top"] + img["height"] <= 297 - 10 + 0.5
    assert p1["min_text_mm"] >= 3.2
    if fmt == "pdf":
        from pypdf import PdfReader
        page = PdfReader(str(tmp_path / "uspto.pdf")).pages[0]
        ops = [op for _a, op in page.get_contents().operations]
        assert ops.count(b"S") == 4, "两对角十字靶标 = 4 条线段"
        assert ops.index(b"S") < ops.index(b"Do"), "靶标画在图片之前（图片之后不得再绘制）"
        assert ops == [op for op, _a in C._pdf_ops_pattern(1, D.spec("standard", 300, "uspto"))]


def test_cnipa_check_refuses_a_uspto_document_and_vice_versa(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    pytest.importorskip("pypdfium2")
    monkeypatch.setenv("PFK_PDF_RENDERER", "pypdfium2")
    rep, _ = _build_and_check(tmp_path, "uspto", "pdf", check_office="cnipa")
    assert rep["ok"] is False and rep["status"] == C.STATUS_FAIL
    errs = "；".join(rep["errors"] + sum((p["errors"] for p in rep["page_checks"]), []))
    assert "图号应为「图1」" in errs and ("内容流" in errs or "页边" in errs)
    rep, _ = _build_and_check(tmp_path, "cnipa", "docx", check_office="uspto")
    assert rep["ok"] is False
    errs = "；".join(rep["errors"] + sum((p["errors"] for p in rep["page_checks"]), []))
    assert "FIG. 1" in errs and ("页边" in errs or "固定模板" in errs)


def test_uspto_filing_copy_must_be_english_only(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    pytest.importorskip("pypdfium2")
    monkeypatch.setenv("PFK_PDF_RENDERER", "pypdfium2")
    path = _filing_sheet(tmp_path / "fig1_filing.dxf", 1, "uspto", total=1)
    doc = ezdxf.readfile(str(path))
    note = doc.modelspace().add_text("外壳", dxfattribs={"layer": "NOTE", "height": 3.5})
    note.set_placement((60, 100), align=TextEntityAlignment.MIDDLE_LEFT)
    doc.layers.add("NOTE")
    doc.saveas(str(path))
    rows = [{"figure": "fig1", "number": 1, "dxf": path}]
    sp = D.spec("standard", 300, "uspto")
    pages = [D.rasterize(path, sp, "fig1", 1)]
    out = tmp_path / "u.pdf"
    D.write_pdf(pages, out)
    strict = dict(sp, language_check=True)
    rep = C.check_document(out, C.sources_from(rows, sp["area_mm"]), strict)
    assert rep["ok"] is False and any("非英文字母表" in e for e in rep["page_checks"][0]["errors"])
    lenient = dict(sp, language_check=False)       # the disclosure copy keeps the drafter's language
    rep = C.check_document(out, C.sources_from(rows, sp["area_mm"]), lenient)
    assert rep["ok"] is True, rep["errors"]


# --------------------------------------------------------------------------- export service


def test_export_refuses_an_office_the_version_was_not_rendered_under(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    from patent_figure import export as EX
    from patent_figure import versions as V
    from test_deliverable import _publish
    store = V.VersionStore(tmp_path / "ws")
    vd = _publish(store, "r1", tmp_path)                 # cnipa sheets, no inputs/plan.json
    assert EX.version_office(vd) == "cnipa"
    (vd / "inputs").mkdir(exist_ok=True)
    (vd / "inputs" / "plan.json").write_text(json.dumps({"office": "cnipa"}), encoding="utf-8")
    with EX.acquire(store.root) as pin:
        bad = EX.build_bundle(pin, tmp_path / "bad", variants=("filing",), formats=("pdf", "dxf"),
                              dpi=300, checklist_txt=True, office="uspto")
    assert bad["ok"] is False
    assert bad["manifest"]["fig1/递交版/pdf"] == "fail" and bad["manifest"]["fig1/递交版/dxf"] == "ok"
    assert "不一致" in bad["reasons"]["fig1/递交版/pdf"]
    assert store.referenced() == set()
