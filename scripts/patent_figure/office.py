"""Office profiles（首发收口 · USPTO 最小版）：一套 figure-plan，切一个参数，出不同专利局的版式。

每个局是 ``profiles/<office>.json`` 一个文件：纸张与页边、图区预设、图号格式与位置、页码格式、最小字高、
图内文字语言、十字靶标开关；文件头 ``_sources`` 写条款出处与核对日期。**新增一个局不改代码。** 阴影与
彩色本轮不做（``not_in_this_profile``）。

谁读它：

* ``deliverable.spec(preset, dpi, office)`` —— 页面合成与逐页核验的全部版式参数；
* ``annotate_figure_sheet.py --office`` —— 图号文字（「图N」/「FIG. N」）、页码（「1/3」）、附图说明行；
* ``render_patent_figure.py`` / ``qa_patent_figure.py`` —— 闸门的最小字高阈值；
* ``capabilities.export_capabilities()`` —— 向前端 / Agent 公布可选的局。

默认 ``cnipa``；``cnipa.json`` 的数值与 ``layout.py`` / ``deliverable.py`` 的冻结常数逐项一致
（``tests/test_office.py`` 守着），所以默认路径的输出一个字节不变（N10 金样不变）。纯标准库，不 import OCP。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"
DEFAULT_OFFICE = "cnipa"
SCHEMA_ID = "patent-figure-office/1"
#: 页码 / 页眉文字所在的 DXF 图层（与 sheet.LAYERS 的七层并列；只在 profile 开启页码时出现）。
SHEET_LAYER = "SHEET"

_REQUIRED = ("office", "paper", "margins_mm", "area_presets", "default_preset", "caption",
             "sheet_number", "min_text_mm", "text_language", "targets")
_CACHE: Dict[str, Dict[str, Any]] = {}


class OfficeError(ValueError):
    pass


def list_offices() -> List[str]:
    """已安装的局（profiles/*.json 的文件名），按名排序；至少含 cnipa。"""
    names = sorted(p.stem for p in PROFILES_DIR.glob("*.json") if not p.name.startswith("_"))
    return names or [DEFAULT_OFFICE]


def normalize(office: Optional[str]) -> str:
    name = (office or DEFAULT_OFFICE).strip().lower()
    if name not in list_offices():
        raise OfficeError("未知专利局 %r（可选：%s）" % (office, " / ".join(list_offices())))
    return name


def load(office: Optional[str] = None) -> Dict[str, Any]:
    """读取并校验一个 profile（进程内缓存，返回副本）。"""
    name = normalize(office)
    if name not in _CACHE:
        path = PROFILES_DIR / (name + ".json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OfficeError("读不了 profile %s：%s" % (path, exc))
        if data.get("schema") != SCHEMA_ID:
            raise OfficeError("%s 的 schema 应为 %s" % (path.name, SCHEMA_ID))
        missing = [k for k in _REQUIRED if k not in data]
        if missing:
            raise OfficeError("%s 缺字段 %s" % (path.name, missing))
        if str(data["office"]).lower() != name:
            raise OfficeError("%s 里的 office=%r 与文件名不符" % (path.name, data["office"]))
        if data["default_preset"] not in data["area_presets"]:
            raise OfficeError("%s 的 default_preset 不在 area_presets 里" % path.name)
        for key, p in data["area_presets"].items():
            aw, ah = (float(x) for x in p["area_mm"])
            pw, ph = (float(x) for x in data["paper"]["size_mm"])
            m = data["margins_mm"]
            if aw > pw - m["left"] - m["right"] + 1e-6 or ah > ph - m["top"] - m["bottom"] + 1e-6:
                raise OfficeError("%s 的图区 %s（%g×%g）放不进页边之内" % (path.name, key, aw, ah))
        _CACHE[name] = data
    return json.loads(json.dumps(_CACHE[name]))


def caption(office: Optional[str], n: int) -> str:
    """图号文字：cnipa 「图3」，uspto 「FIG. 3」。"""
    return str(load(office)["caption"]["format"]).format(n=int(n))


def description_line(office: Optional[str], n: int, caption_text: str) -> str:
    """《附图说明》里的一行：cnipa 「图3为…；」，uspto 「FIG. 3 is …;」。"""
    fmt = load(office)["caption"].get("description_line") or "{n}: {caption}"
    return str(fmt).format(n=int(n), caption=caption_text)


def sheet_number(office: Optional[str], n: int, total: int) -> Optional[str]:
    """页码文字（profile 未开启时为 None）：uspto 「2/5」。"""
    sn = load(office)["sheet_number"]
    if not sn.get("enabled"):
        return None
    return str(sn["format"]).format(n=int(n), total=int(total))


def qa_thresholds(office: Optional[str]) -> Dict[str, float]:
    """闸门从 profile 读的阈值（目前只有最小字高；其余阈值是几何契约，不随局变）。"""
    return {"text_height_mm_min": float(load(office)["min_text_mm"])}


def text_allowed(office: Optional[str], text: str) -> bool:
    """图内文字语言：zh 不限；en 要求全部为 ASCII 可打印字符（1.84(p)(2) 英文字母表）。"""
    lang = load(office)["text_language"]
    if lang == "en":
        return all(32 <= ord(c) < 127 for c in text)
    return True


def summary(office: Optional[str] = None) -> Dict[str, Any]:
    """给能力接口 / 文档用的摘要（不含 _sources 正文）。"""
    p = load(office)
    return {"office": p["office"], "name": p.get("name", p["office"]),
            "paper": p["paper"], "margins_mm": p["margins_mm"],
            "area_presets": p["area_presets"], "default_preset": p["default_preset"],
            "caption_format": p["caption"]["format"], "sheet_number": p["sheet_number"],
            "min_text_mm": p["min_text_mm"], "text_language": p["text_language"],
            "targets": p["targets"].get("enabled", False),
            "not_in_this_profile": p.get("not_in_this_profile", []),
            "verified": p.get("_verified")}


def all_summaries() -> Dict[str, Dict[str, Any]]:
    return {name: summary(name) for name in list_offices()}
