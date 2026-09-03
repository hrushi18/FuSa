"""CLI:  fusa plan | run <agent-id> [--force] [--no-review] | run-all | status | gate <WP> | metrics <csv> [--asil D]"""
from __future__ import annotations

import argparse
import sys

from . import config


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fusa", description="FuSa Agent Framework (ISO 26262 / SEooC)")
    p.add_argument("--dry-run", action="store_true", help="no model calls; deterministic stub content")
    p.add_argument("--strict", action="store_true", help="block downstream while upstream has PENDING markers")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="show creation order")
    r = sub.add_parser("run", help="run one agent"); r.add_argument("agent"); r.add_argument("--force", action="store_true"); r.add_argument("--no-review", action="store_true")
    sub.add_parser("run-all", help="walk the dependency sequence")
    sub.add_parser("status", help="live status board")
    g = sub.add_parser("gate", help="re-run structural gate on a work product"); g.add_argument("work_product")
    sub.add_parser("aspice", help="ASPICE base-practice coverage from the status board")
    rp = sub.add_parser("report", help="release validation -> _generated/VALIDATION-REPORT.md (exit 1 if not releasable)"); rp.add_argument("--asil", default="B")
    u = sub.add_parser("ui", help="serve the demo dashboard"); u.add_argument("--host", default="127.0.0.1"); u.add_argument("--port", type=int, default=8000)
    ri = sub.add_parser("import-reqif", help="ReqIF -> work product"); ri.add_argument("file"); ri.add_argument("--work-product", required=True); ri.add_argument("--prefix", required=True); ri.add_argument("--id-attribute")
    re_ = sub.add_parser("export-reqif", help="work product -> ReqIF"); re_.add_argument("work_product"); re_.add_argument("--out")
    m = sub.add_parser("metrics", help="compute SPFM/LFM/PMHF from a failure-mode CSV"); m.add_argument("csv"); m.add_argument("--asil", default="B")
    t = sub.add_parser("template", help="write an input template (requirements .xlsx | fmeda .csv)")
    t.add_argument("--kind", choices=["requirements", "fmeda"], default="requirements")
    t.add_argument("--out", help="default: safety-requirements-template.xlsx / fmeda-failure-modes-template.csv")
    a = p.parse_args(argv)

    if a.cmd == "ui":
        from .ui import server
        print(f"FuSa dashboard on http://{a.host}:{a.port}  (dry_run={a.dry_run or None})")
        server.serve(host=a.host, port=a.port, dry_run=a.dry_run or None)
        return 0

    if a.cmd == "template":
        from pathlib import Path
        from .tools import reqtable
        if a.kind == "fmeda":
            out = Path(a.out or "fmeda-failure-modes-template.csv")
            out.write_text(reqtable.fmeda_template_text(), encoding="utf-8")
            print(out)
        else:
            print(reqtable.write_template(a.out or "safety-requirements-template.xlsx"))
        return 0

    if a.cmd == "metrics":
        from .tools import metrics
        try:
            rows = metrics.load_csv(a.csv)
        except (OSError, ValueError) as e:
            print(f"fusa: {e}", file=sys.stderr)
            return 2
        print(metrics.render(metrics.compute(rows), a.asil.upper()))
        return 0

    from .agents.llm import LLMConfigError, LLMResponseError
    from .orchestrator import Orchestrator, UnknownAgent
    orch = Orchestrator(dry_run=a.dry_run or None, strict_pending=a.strict or None)
    if orch.reg.process.load_warning:
        print(f"fusa: {orch.reg.process.load_warning}", file=sys.stderr)
    try:
        return _dispatch(a, orch)
    except UnknownAgent as e:
        print(f"fusa: {e}", file=sys.stderr)
        runnable = ", ".join(sorted(orch.agents))
        print(f"fusa: runnable now: {runnable}", file=sys.stderr)
        return 2
    except LLMResponseError as e:
        print(f"fusa: {e}", file=sys.stderr)
        return 3
    except LLMConfigError as e:                      # setup problem: one line, not a stack trace
        print(f"fusa: {e}", file=sys.stderr)
        print(f"fusa: provider '{orch.llm.provider}', model '{orch.llm.model}' "
              "(FUSA_PROVIDER / FUSA_MODEL; --dry-run needs no key)", file=sys.stderr)
        print(f"fusa: or put the key in {config.ROOT / '.env'} — see .env.example", file=sys.stderr)
        return 2


def _dispatch(a, orch) -> int:
    if a.cmd == "plan":
        for i, s in enumerate(orch.plan(), 1):
            print(f"{i:2}. phase {s.phase}  {s.id:22} -> {s.work_product:12} requires {', '.join(s.requires) or '—'}")
    elif a.cmd == "run":
        orch.run(a.agent, force=a.force, review=not a.no_review)
    elif a.cmd == "run-all":
        orch.run_all()
        print(); print(orch.status())
    elif a.cmd == "status":
        print(orch.status())
    elif a.cmd == "aspice":
        print(orch.aspice())
    elif a.cmd == "report":
        from .report import validate, write_report
        rep = validate(orch, asil=a.asil.upper())
        print(f"{rep.verdict}  (ASIL {rep.asil})")
        for reason in rep.reasons:
            print(f"  - {reason}")
        print(write_report(orch, rep))
        return 0 if rep.verdict == "RELEASABLE" else 1
    elif a.cmd == "import-reqif":
        from .adapters import reqif
        try:
            objs = reqif.parse(a.file)
        except (OSError, ValueError) as e:
            print(f"fusa: {e}", file=sys.stderr)
            return 2
        content = reqif.to_work_product(objs, a.work_product, a.prefix, id_attribute=a.id_attribute,
                                        parent_ids={v: k for k, v in _reqif_index(orch).items()})
        path = orch.reg.generated.write(a.work_product, content)
        orch.reg.process.update(a.work_product, "reqif-import", status=__import__("fusa.models", fromlist=["Status"]).Status.GATE_PASSED, path=str(path))
        print(f"imported {len(objs)} objects -> {path}")
    elif a.cmd == "export-reqif":
        from .adapters import reqif
        xml = reqif.from_work_product(orch.reg.generated.read(a.work_product))
        out = a.out or str(orch.reg.generated.file(a.work_product).with_suffix(".reqif"))
        open(out, "w", encoding="utf-8").write(xml); print(out)
    elif a.cmd == "gate":
        from .gate import run_gate
        try:
            spec = orch.spec_for(a.work_product)
        except KeyError:
            known = ", ".join(sorted(set(orch.by_wp) | set(orch.reg.generated.all_work_products())))
            print(f"fusa: no work product '{a.work_product}' — known: {known}", file=sys.stderr)
            return 2
        res = run_gate(spec, orch.reg.generated.read(a.work_product), orch.reg.generated)
        print(res.model_dump_json(indent=2))
        return 0 if res.passed else 1
    return 0


def _reqif_index(orch) -> dict[str, str]:
    """house id -> reqif_id for everything already in the store (lets imports link to existing parents)."""
    out = {}
    for wp in orch.reg.generated.all_work_products():
        for i in orch.reg.generated.items(wp):
            if "reqif_id" in i.fields:
                out[i.id] = i.fields["reqif_id"]
    return out


if __name__ == "__main__":
    sys.exit(main())
