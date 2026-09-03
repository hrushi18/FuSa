"""ReqIF adapter — round-trip requirements between a PLM/ALM tool and the work-product grammar.

Import: SPEC-OBJECTs become `### <PREFIX>-nnn` items; every ATTRIBUTE-VALUE becomes a `- key: value`
bullet (long names normalised to snake_case); SPEC-RELATIONs of type derive/satisfy become `- parent:`.
The ReqIF IDENTIFIER is kept as `- reqif_id:` so export writes back to the same objects.

Export: items → SPEC-OBJECTs, `parent:` → SPEC-RELATIONs, PENDING markers → a `pending` attribute.
Only the subset of ReqIF 1.2 that tools actually exchange is implemented; unknown constructs are ignored.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..tools import ids

NS = {"r": "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd", "x": "http://www.w3.org/1999/xhtml"}
R = "{%s}" % NS["r"]
PARENT_RELATION_TYPES = {"derive", "derives", "satisfies", "satisfy", "refines", "parent", "traces"}


@dataclass
class ReqIfObject:
    identifier: str
    attributes: dict[str, str] = field(default_factory=dict)
    parents: list[str] = field(default_factory=list)   # identifiers of source objects


def _snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "value"


def _xhtml_text(el: ET.Element) -> str:
    return " ".join(t.strip() for t in el.itertext() if t.strip())


def parse(path: str | Path) -> list[ReqIfObject]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as e:
        raise ValueError(f"{Path(path).name} is not readable ReqIF XML: {e}") from None
    # attribute definitions: id -> long name
    defs: dict[str, str] = {}
    for d in root.iter():
        if d.tag.startswith(R + "ATTRIBUTE-DEFINITION-"):
            defs[d.get("IDENTIFIER", "")] = d.get("LONG-NAME", d.get("IDENTIFIER", ""))
    rel_types: dict[str, str] = {t.get("IDENTIFIER", ""): t.get("LONG-NAME", "").lower()
                                 for t in root.iter(R + "SPEC-RELATION-TYPE")}

    objs: dict[str, ReqIfObject] = {}
    for so in root.iter(R + "SPEC-OBJECT"):
        o = ReqIfObject(identifier=so.get("IDENTIFIER", ""))
        for av in so.iter():
            tag = av.tag.replace(R, "")
            if not tag.startswith("ATTRIBUTE-VALUE-"):
                continue
            def_ref = next((c for c in av.iter() if c.tag.endswith("-REF") and "DEFINITION" in c.tag), None)
            key = _snake(defs.get(def_ref.text.strip(), def_ref.text.strip())) if def_ref is not None and def_ref.text else _snake(tag)
            if tag == "ATTRIBUTE-VALUE-XHTML":
                the_value = av.find(R + "THE-VALUE")
                val = _xhtml_text(the_value) if the_value is not None else ""
            elif tag == "ATTRIBUTE-VALUE-ENUMERATION":
                val = ", ".join(v.text.strip() for v in av.iter(R + "ENUM-VALUE-REF") if v.text)
            else:
                val = av.get("THE-VALUE", "")
            o.attributes[key] = val
        objs[o.identifier] = o

    for rel in root.iter(R + "SPEC-RELATION"):
        src = rel.find(f"{R}SOURCE/{R}SPEC-OBJECT-REF")
        tgt = rel.find(f"{R}TARGET/{R}SPEC-OBJECT-REF")
        typ = rel.find(f"{R}TYPE/{R}SPEC-RELATION-TYPE-REF")
        tname = rel_types.get(typ.text.strip(), "") if typ is not None and typ.text else ""
        if src is not None and tgt is not None and (not tname or any(k in tname for k in PARENT_RELATION_TYPES)):
            # convention: SOURCE derives from TARGET  →  target is the parent
            if src.text.strip() in objs:
                objs[src.text.strip()].parents.append(tgt.text.strip())
    return list(objs.values())


def to_work_product(objs: list[ReqIfObject], work_product: str, prefix: str, agent: str = "reqif-import",
                    id_attribute: str | None = None, parent_ids: dict[str, str] | None = None) -> str:
    """Render objects in the house grammar. `id_attribute` names a ReqIF attribute already holding
    house ids (e.g. 'req_id'); otherwise ids are assigned PREFIX-001.. in document order."""
    parent_ids = dict(parent_ids or {})
    assigned: dict[str, str] = {}
    for n, o in enumerate(objs, 1):
        hid = o.attributes.get(id_attribute or "", "").strip() if id_attribute else ""
        assigned[o.identifier] = hid if ids.ID_RE.fullmatch(hid) else f"{prefix}-{n:03d}"
    parent_ids.update(assigned)

    out = [f"---\nid: {work_product}\ntitle: Imported requirements\nagent: {agent}\n"
           f"date: {datetime.now(timezone.utc).date().isoformat()}\nsource: reqif\nstatus: imported\n---\n",
           f"# {work_product}\n\nImported from ReqIF; `reqif_id` keeps the round-trip key.\n\n## Items\n"]
    for o in objs:
        out.append(f"### {assigned[o.identifier]}")
        out.append(f"- reqif_id: {o.identifier}")
        for pid in o.parents:
            out.append(f"- parent: {parent_ids.get(pid, f'[PENDING: parent {pid} not in import <- reqif-import]')}")
        for k, v in o.attributes.items():
            if k == (id_attribute or ""):
                continue
            out.append(f"- {k}: {v}")
        out.append("")
    return "\n".join(out)


def from_work_product(content: str, spec_type_name: str = "Requirement") -> str:
    """Export a work product to a minimal ReqIF 1.2 document (string)."""
    items = ids.parse_items(content)
    fm = ids.parse_front_matter(content)
    keys = sorted({k for i in items for k in i.fields} - {"reqif_id", "parent"} | {"house_id", "pending"})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def defn(k: str) -> str:
        return f'<ATTRIBUTE-DEFINITION-STRING IDENTIFIER="ad-{k}" LONG-NAME="{k}" LAST-CHANGE="{now}"><TYPE><DATATYPE-DEFINITION-STRING-REF>dt-string</DATATYPE-DEFINITION-STRING-REF></TYPE></ATTRIBUTE-DEFINITION-STRING>'

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")

    objects, relations = [], []
    for i in items:
        oid = i.fields.get("reqif_id") or f"obj-{i.id}"
        vals = [f'<ATTRIBUTE-VALUE-STRING THE-VALUE="{esc(i.id)}"><DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>ad-house_id</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION></ATTRIBUTE-VALUE-STRING>']
        for k, v in i.fields.items():
            if k in {"reqif_id", "parent"}:
                continue
            vals.append(f'<ATTRIBUTE-VALUE-STRING THE-VALUE="{esc(v)}"><DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>ad-{k}</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION></ATTRIBUTE-VALUE-STRING>')
        pend = ids.find_pending(i.body)
        if pend:
            vals.append(f'<ATTRIBUTE-VALUE-STRING THE-VALUE="{esc("; ".join(pend))}"><DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>ad-pending</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION></ATTRIBUTE-VALUE-STRING>')
        objects.append(f'<SPEC-OBJECT IDENTIFIER="{esc(oid)}" LAST-CHANGE="{now}"><TYPE><SPEC-OBJECT-TYPE-REF>st-req</SPEC-OBJECT-TYPE-REF></TYPE><VALUES>{"".join(vals)}</VALUES></SPEC-OBJECT>')
        for p in i.refs("parent"):
            relations.append(f'<SPEC-RELATION IDENTIFIER="rel-{esc(i.id)}-{esc(p)}" LAST-CHANGE="{now}"><TYPE><SPEC-RELATION-TYPE-REF>rt-derive</SPEC-RELATION-TYPE-REF></TYPE>'
                             f'<SOURCE><SPEC-OBJECT-REF>{esc(oid)}</SPEC-OBJECT-REF></SOURCE><TARGET><SPEC-OBJECT-REF>obj-{esc(p)}</SPEC-OBJECT-REF></TARGET></SPEC-RELATION>')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<REQ-IF xmlns="{NS["r"]}" xmlns:xhtml="{NS["x"]}">
<THE-HEADER><REQ-IF-HEADER IDENTIFIER="hdr-{esc(fm.get("id", "wp"))}"><CREATION-TIME>{now}</CREATION-TIME><REQ-IF-TOOL-ID>fusa-agents</REQ-IF-TOOL-ID><REQ-IF-VERSION>1.2</REQ-IF-VERSION><SOURCE-TOOL-ID>fusa-agents</SOURCE-TOOL-ID><TITLE>{esc(fm.get("title", fm.get("id", "")))}</TITLE></REQ-IF-HEADER></THE-HEADER>
<CORE-CONTENT><REQ-IF-CONTENT>
<DATATYPES><DATATYPE-DEFINITION-STRING IDENTIFIER="dt-string" LONG-NAME="String" MAX-LENGTH="32000" LAST-CHANGE="{now}"/></DATATYPES>
<SPEC-TYPES>
<SPEC-OBJECT-TYPE IDENTIFIER="st-req" LONG-NAME="{esc(spec_type_name)}" LAST-CHANGE="{now}"><SPEC-ATTRIBUTES>{"".join(defn(k) for k in keys)}</SPEC-ATTRIBUTES></SPEC-OBJECT-TYPE>
<SPEC-RELATION-TYPE IDENTIFIER="rt-derive" LONG-NAME="derives" LAST-CHANGE="{now}"/>
</SPEC-TYPES>
<SPEC-OBJECTS>{"".join(objects)}</SPEC-OBJECTS>
<SPEC-RELATIONS>{"".join(relations)}</SPEC-RELATIONS>
</REQ-IF-CONTENT></CORE-CONTENT>
</REQ-IF>
'''
