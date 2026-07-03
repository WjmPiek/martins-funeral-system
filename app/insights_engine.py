"""Enterprise Insights and Explanation Engine.

Phase 12 converts trusted Martins Funeral System data into plain-language
explanations.  It is read/explain only and does not alter royalty, import,
target or leaderboard calculations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Dict, List

from sqlalchemy import text

from app.extensions import db
from app.models import (
    BusinessInsight,
    FranchiseHealthSnapshot,
    InsightNarrative,
    MonthlyFigure,
    RoyaltyCalculationSnapshot,
)


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _money(value: Any) -> str:
    return f"R {_to_float(value):,.2f}"


def _pct(value: Any) -> str:
    return f"{_to_float(value):.1f}%"


def latest_period() -> Dict[str, int]:
    row = db.session.execute(text("""
        SELECT year, month
        FROM monthly_figures
        GROUP BY year, month
        ORDER BY year DESC, month DESC
        LIMIT 1
    """)).mappings().first()
    if row:
        return {"year": int(row["year"]), "month": int(row["month"])}
    now = datetime.now(timezone.utc)
    return {"year": now.year, "month": now.month}


def _previous_period(year: int, month: int) -> Dict[str, int]:
    month -= 1
    if month < 1:
        month = 12
        year -= 1
    return {"year": year, "month": month}


def _totals(year: int, month: int) -> Dict[str, Any]:
    row = db.session.execute(text("""
        SELECT COUNT(*) AS rows,
               COALESCE(SUM(gross_turnover), 0) AS gross_turnover,
               COALESCE(SUM(royalty_amount), 0) AS royalty_amount,
               COALESCE(SUM(payover), 0) AS payover,
               COALESCE(SUM(number_of_funerals), 0) AS funerals,
               COALESCE(SUM(insurance_joinings), 0) AS joinings
        FROM monthly_figures
        WHERE year = :year AND month = :month
    """), {"year": year, "month": month}).mappings().first()
    return dict(row or {})


def _status_counts(year: int, month: int) -> Dict[str, int]:
    rows = db.session.execute(text("""
        SELECT health_status, COUNT(*) AS count
        FROM franchise_health_snapshots
        WHERE year = :year AND month = :month
        GROUP BY health_status
    """), {"year": year, "month": month}).mappings().all()
    return {str(r["health_status"]): int(r["count"] or 0) for r in rows}


def _province_rows(year: int, month: int) -> List[Dict[str, Any]]:
    rows = db.session.execute(text("""
        WITH province_map AS (
            SELECT franchise_id, MAX(NULLIF(province, '')) AS province
            FROM heatmap_records
            GROUP BY franchise_id
        )
        SELECT COALESCE(NULLIF(f.province, ''), pm.province, 'Unassigned') AS province,
               COUNT(*) AS franchises,
               COALESCE(AVG(fhs.health_score), 0) AS avg_health_score,
               COALESCE(SUM(fhs.gross_turnover), 0) AS gross_turnover,
               COALESCE(SUM(fhs.royalty_amount), 0) AS royalty_amount,
               COALESCE(AVG(fhs.growth_percent), 0) AS avg_growth_percent,
               SUM(CASE WHEN fhs.health_status = 'critical' THEN 1 ELSE 0 END) AS critical_count
        FROM franchise_health_snapshots fhs
        JOIN franchises f ON f.id = fhs.franchise_id
        LEFT JOIN province_map pm ON pm.franchise_id = fhs.franchise_id
        WHERE fhs.year = :year AND fhs.month = :month
        GROUP BY COALESCE(NULLIF(f.province, ''), pm.province, 'Unassigned')
        ORDER BY avg_health_score DESC, gross_turnover DESC
        LIMIT 12
    """), {"year": year, "month": month}).mappings().all()
    return [dict(r) for r in rows]


def _add_narrative(kind: str, title: str, summary: str, detail: str = "", severity: str = "info", *, year: int, month: int, franchise_id: int | None = None, province: str | None = None, source: Dict[str, Any] | None = None) -> None:
    db.session.add(InsightNarrative(
        narrative_type=kind,
        title=title,
        summary=summary,
        detail=detail,
        severity=severity,
        year=year,
        month=month,
        franchise_id=franchise_id,
        province=province,
        source_json=json.dumps(source or {}, default=str),
    ))


def rebuild_insight_narratives(year: int | None = None, month: int | None = None, commit: bool = True) -> Dict[str, Any]:
    period = latest_period() if not year or not month else {"year": int(year), "month": int(month)}
    year = int(period["year"])
    month = int(period["month"])
    prev = _previous_period(year, month)

    # Ensure BI data exists before generating explanations.
    if FranchiseHealthSnapshot.query.filter_by(year=year, month=month).count() == 0:
        from app.business_intelligence import rebuild_business_intelligence
        rebuild_business_intelligence(year, month, commit=False)
        db.session.flush()

    InsightNarrative.query.filter_by(year=year, month=month).delete()
    db.session.flush()

    totals = _totals(year, month)
    prev_totals = _totals(prev["year"], prev["month"])
    gross = _to_float(totals.get("gross_turnover"))
    prev_gross = _to_float(prev_totals.get("gross_turnover"))
    royalty = _to_float(totals.get("royalty_amount"))
    growth = ((gross - prev_gross) / prev_gross * 100.0) if prev_gross else (100.0 if gross else 0.0)
    status = _status_counts(year, month)
    critical = status.get("critical", 0)
    watch = status.get("watch", 0)
    healthy = status.get("healthy", 0)

    severity = "info"
    if critical:
        severity = "warning"
    if growth < -10:
        severity = "danger"
    _add_narrative(
        "executive_summary",
        f"Executive Summary - {year}-{month:02d}",
        f"Company turnover is {_money(gross)} for {year}-{month:02d}, with royalties of {_money(royalty)}.",
        f"Compared with {prev['year']}-{prev['month']:02d}, turnover changed by {_pct(growth)}. The BI health mix is {healthy} healthy, {watch} watch and {critical} critical franchise records. This explanation is generated from monthly figures, royalty snapshots and BI health scoring; it does not change calculations.",
        severity,
        year=year,
        month=month,
        source={"totals": totals, "previous_totals": prev_totals, "health_status": status},
    )

    top_growth = FranchiseHealthSnapshot.query.filter_by(year=year, month=month).order_by(FranchiseHealthSnapshot.growth_percent.desc()).limit(5).all()
    largest_decline = FranchiseHealthSnapshot.query.filter_by(year=year, month=month).order_by(FranchiseHealthSnapshot.growth_percent.asc()).limit(5).all()
    for snap in top_growth:
        if _to_float(snap.gross_turnover) <= 0:
            continue
        _add_narrative(
            "franchise_performance",
            f"{snap.franchise.business_name} growth explanation",
            f"{snap.franchise.business_name} shows {_pct(snap.growth_percent)} growth versus the previous month.",
            f"Current gross turnover is {_money(snap.gross_turnover)} compared with {_money(snap.previous_gross_turnover)} previously. Target achievement is {_pct(snap.target_achievement_percent)} and royalty amount is {_money(snap.royalty_amount)}.",
            "success" if _to_float(snap.growth_percent) > 0 else "info",
            year=year,
            month=month,
            franchise_id=snap.franchise_id,
            source={"health_snapshot_id": snap.id, "reasons": snap.reasons},
        )
    for snap in largest_decline:
        if _to_float(snap.growth_percent) >= 0:
            continue
        sev = "danger" if _to_float(snap.growth_percent) <= -15 else "warning"
        _add_narrative(
            "franchise_performance",
            f"{snap.franchise.business_name} decline explanation",
            f"{snap.franchise.business_name} declined by {_pct(abs(_to_float(snap.growth_percent)))} versus the previous month.",
            f"Current gross turnover is {_money(snap.gross_turnover)} compared with {_money(snap.previous_gross_turnover)} previously. Recorded reasons: {'; '.join(snap.reasons) if snap.reasons else 'No detailed BI reason recorded.'}",
            sev,
            year=year,
            month=month,
            franchise_id=snap.franchise_id,
            source={"health_snapshot_id": snap.id, "reasons": snap.reasons},
        )

    for row in _province_rows(year, month):
        sev = "danger" if int(row.get("critical_count") or 0) else ("warning" if _to_float(row.get("avg_growth_percent")) < 0 else "info")
        _add_narrative(
            "province_summary",
            f"{row.get('province')} province summary",
            f"{row.get('province')} has an average health score of {_pct(row.get('avg_health_score'))} across {int(row.get('franchises') or 0)} franchises.",
            f"Gross turnover is {_money(row.get('gross_turnover'))}, royalties are {_money(row.get('royalty_amount'))}, and average growth is {_pct(row.get('avg_growth_percent'))}. Critical records: {int(row.get('critical_count') or 0)}.",
            sev,
            year=year,
            month=month,
            province=row.get("province"),
            source=row,
        )

    # Royalty explanations focus on traceability and warnings, not changing values.
    royalty_rows = RoyaltyCalculationSnapshot.query.filter_by(year=year, month=month).order_by(RoyaltyCalculationSnapshot.status.desc(), RoyaltyCalculationSnapshot.royalty_amount.desc()).limit(30).all()
    for snap in royalty_rows:
        if snap.status == "calculated" and _to_float(snap.royalty_amount) <= 0:
            continue
        sev = "danger" if snap.status == "needs_review" else ("warning" if snap.minimum_royalty_applied else "info")
        title = f"Royalty explanation - {snap.franchise.business_name}"
        summary = f"Royalty for {snap.franchise.business_name} is {_money(snap.royalty_amount)} at {_pct(snap.royalty_percentage)}."
        detail = (
            f"The system used agreement version '{snap.agreement_version or 'not recorded'}', formula '{snap.formula_version}', "
            f"royalty method '{snap.royalty_method}', royalty base {_money(snap.royalty_base)}, target {_money(snap.target_amount)}, "
            f"growth {_pct(snap.growth_percent)} and previous-year average {_money(snap.previous_year_average)}. "
            f"Status: {snap.status}."
        )
        if snap.minimum_royalty_applied:
            detail += f" Minimum royalty was applied at {_money(snap.minimum_royalty_amount)}."
        _add_narrative(
            "royalty_explanation" if snap.status == "calculated" else "royalty_warning",
            title,
            summary,
            detail,
            sev,
            year=year,
            month=month,
            franchise_id=snap.franchise_id,
            source={"snapshot_id": snap.id, "diagnostics": snap.diagnostics},
        )

    # Carry forward key BI insights into the explanation centre.
    for insight in BusinessInsight.query.filter_by(year=year, month=month, is_active=True).order_by(BusinessInsight.created_at.desc()).limit(20).all():
        _add_narrative(
            "business_insight_explanation",
            insight.title,
            insight.message,
            "This insight was generated from the Business Intelligence health scoring layer and is included here for executive explanation.",
            insight.severity,
            year=year,
            month=month,
            franchise_id=insight.franchise_id,
            source={"business_insight_id": insight.id, "data": insight.data},
        )

    if commit:
        db.session.commit()
    count = InsightNarrative.query.filter_by(year=year, month=month).count()
    return {"year": year, "month": month, "narratives": count}


def get_insight_summary(year: int | None = None, month: int | None = None) -> Dict[str, Any]:
    period = latest_period() if not year or not month else {"year": int(year), "month": int(month)}
    year = int(period["year"])
    month = int(period["month"])
    if InsightNarrative.query.filter_by(year=year, month=month).count() == 0:
        rebuild_insight_narratives(year, month, commit=True)
    rows = db.session.execute(text("""
        SELECT narrative_type, severity, COUNT(*) AS count
        FROM insight_narratives
        WHERE year = :year AND month = :month
        GROUP BY narrative_type, severity
        ORDER BY narrative_type, severity
    """), {"year": year, "month": month}).mappings().all()
    totals: Dict[str, Any] = {"by_type": {}, "by_severity": {}, "total": 0}
    for row in rows:
        ntype = row["narrative_type"]
        sev = row["severity"]
        count = int(row["count"] or 0)
        totals["by_type"][ntype] = totals["by_type"].get(ntype, 0) + count
        totals["by_severity"][sev] = totals["by_severity"].get(sev, 0) + count
        totals["total"] += count
    executive = InsightNarrative.query.filter_by(year=year, month=month, narrative_type="executive_summary").order_by(InsightNarrative.created_at.desc()).first()
    return {"year": year, "month": month, "counts": totals, "executive": executive}
