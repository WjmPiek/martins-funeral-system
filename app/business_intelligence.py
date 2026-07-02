"""Enterprise Business Intelligence layer for Martins Funeral System.

Phase 11 reads the existing monthly figures, royalty snapshots and operational
state to produce executive health scores and human-readable insights.  It does
not change the royalty calculation rules or write to monthly figures.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any, Dict, List, Tuple

from sqlalchemy import text

from app.extensions import db
from app.models import Franchise, FranchiseHealthSnapshot, BusinessInsight


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _period_back(year: int, month: int, months_back: int = 1) -> Tuple[int, int]:
    y = int(year)
    m = int(month)
    for _ in range(months_back):
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    return y, m


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


def _fetch_period_rows(year: int, month: int) -> Dict[int, Dict[str, Any]]:
    rows = db.session.execute(text("""
        SELECT mf.franchise_id,
               f.business_name,
               COALESCE(mf.gross_turnover, 0) AS gross_turnover,
               COALESCE(mf.royalty_amount, 0) AS royalty_amount,
               COALESCE(mf.payover, 0) AS payover,
               COALESCE(mf.number_of_funerals, 0) AS funerals,
               COALESCE(mf.insurance_joinings, 0) AS joinings,
               COALESCE(rs.target_amount, 0) AS target_amount,
               COALESCE(rs.status, '') AS royalty_status,
               COALESCE(rs.growth_percent, 0) AS growth_percent
        FROM monthly_figures mf
        JOIN franchises f ON f.id = mf.franchise_id
        LEFT JOIN royalty_calculation_snapshots rs ON rs.monthly_figure_id = mf.id
        WHERE mf.year = :year AND mf.month = :month
    """), {"year": year, "month": month}).mappings().all()
    return {int(row["franchise_id"]): dict(row) for row in rows}


def _trend_for_franchise(franchise_id: int, year: int, month: int) -> Dict[str, Any]:
    rows = db.session.execute(text("""
        SELECT year, month, COALESCE(gross_turnover, 0) AS gross_turnover
        FROM monthly_figures
        WHERE franchise_id = :franchise_id
          AND (year * 100 + month) <= (:year * 100 + :month)
        ORDER BY year DESC, month DESC
        LIMIT 4
    """), {"franchise_id": franchise_id, "year": year, "month": month}).mappings().all()
    ordered = list(reversed([dict(row) for row in rows]))
    values = [_to_float(row.get("gross_turnover")) for row in ordered]
    consecutive_growth = 0
    consecutive_decline = 0
    for prev, curr in zip(values, values[1:]):
        if curr > prev:
            consecutive_growth += 1
            consecutive_decline = 0
        elif curr < prev:
            consecutive_decline += 1
            consecutive_growth = 0
        else:
            consecutive_growth = 0
            consecutive_decline = 0
    return {
        "values": values,
        "consecutive_growth": consecutive_growth,
        "consecutive_decline": consecutive_decline,
        "periods": ordered,
    }


def _score_franchise(current: Dict[str, Any], previous: Dict[str, Any] | None, trend: Dict[str, Any]) -> Dict[str, Any]:
    gross = _to_float(current.get("gross_turnover"))
    prev_gross = _to_float((previous or {}).get("gross_turnover"))
    royalty = _to_float(current.get("royalty_amount"))
    target = _to_float(current.get("target_amount"))
    funerals = _to_float(current.get("funerals"))
    joinings = _to_float(current.get("joinings"))

    growth_percent = ((gross - prev_gross) / prev_gross * 100.0) if prev_gross else (100.0 if gross > 0 else 0.0)
    target_percent = (gross / target * 100.0) if target else 0.0
    royalty_ratio = (royalty / gross * 100.0) if gross else 0.0

    revenue_score = max(0, min(100, 55 + growth_percent * 2.0))
    if gross <= 0:
        revenue_score = 0
    target_score = max(0, min(100, target_percent)) if target else (80 if gross > 0 else 0)
    royalty_score = 90 if royalty > 0 else (20 if gross > 0 else 0)
    trend_score = 75
    if trend.get("consecutive_growth", 0) >= 3:
        trend_score = 95
    elif trend.get("consecutive_decline", 0) >= 3:
        trend_score = 25
    elif growth_percent < -10:
        trend_score = 40
    activity_score = 80 if (funerals > 0 or joinings > 0 or gross > 0) else 25

    overall = (
        revenue_score * 0.30
        + target_score * 0.25
        + royalty_score * 0.20
        + trend_score * 0.15
        + activity_score * 0.10
    )
    overall = round(max(0, min(100, overall)), 2)
    if overall >= 75:
        status = "healthy"
    elif overall >= 50:
        status = "watch"
    else:
        status = "critical"

    reasons = []
    if growth_percent < -10:
        reasons.append(f"Gross turnover declined by {abs(growth_percent):.1f}% versus previous month.")
    if target and target_percent < 80:
        reasons.append(f"Only {target_percent:.1f}% of target achieved.")
    if gross > 0 and royalty <= 0:
        reasons.append("Gross turnover exists but royalty calculated as zero.")
    if trend.get("consecutive_decline", 0) >= 3:
        reasons.append("Three consecutive months of decline detected.")
    if not reasons and status == "healthy":
        reasons.append("Performance is within healthy operating range.")

    return {
        "score": overall,
        "status": status,
        "growth_percent": round(growth_percent, 2),
        "target_percent": round(target_percent, 2),
        "royalty_ratio": round(royalty_ratio, 2),
        "reasons": reasons,
    }


def rebuild_business_intelligence(year: int | None = None, month: int | None = None, commit: bool = True) -> Dict[str, Any]:
    period = latest_period() if not year or not month else {"year": int(year), "month": int(month)}
    year = int(period["year"])
    month = int(period["month"])
    previous_year, previous_month = _period_back(year, month, 1)

    current_rows = _fetch_period_rows(year, month)
    previous_rows = _fetch_period_rows(previous_year, previous_month)

    # Replace snapshots for this period so the BI layer is reproducible.
    FranchiseHealthSnapshot.query.filter_by(year=year, month=month).delete()
    BusinessInsight.query.filter_by(year=year, month=month).delete()
    db.session.flush()

    snapshots: List[FranchiseHealthSnapshot] = []
    critical = []
    watch = []
    healthy = []
    biggest_decline = None
    biggest_growth = None

    for franchise_id, row in current_rows.items():
        trend = _trend_for_franchise(franchise_id, year, month)
        score_data = _score_franchise(row, previous_rows.get(franchise_id), trend)
        snapshot = FranchiseHealthSnapshot(
            franchise_id=franchise_id,
            year=year,
            month=month,
            health_score=Decimal(str(score_data["score"])),
            health_status=score_data["status"],
            gross_turnover=Decimal(str(_to_float(row.get("gross_turnover")))),
            previous_gross_turnover=Decimal(str(_to_float((previous_rows.get(franchise_id) or {}).get("gross_turnover")))),
            growth_percent=Decimal(str(score_data["growth_percent"])),
            target_amount=Decimal(str(_to_float(row.get("target_amount")))),
            target_achievement_percent=Decimal(str(score_data["target_percent"])),
            royalty_amount=Decimal(str(_to_float(row.get("royalty_amount")))),
            royalty_ratio_percent=Decimal(str(score_data["royalty_ratio"])),
            consecutive_growth_months=int(trend.get("consecutive_growth") or 0),
            consecutive_decline_months=int(trend.get("consecutive_decline") or 0),
            reasons_json=json.dumps(score_data["reasons"]),
        )
        db.session.add(snapshot)
        snapshots.append(snapshot)
        if score_data["status"] == "critical":
            critical.append((row, score_data))
        elif score_data["status"] == "watch":
            watch.append((row, score_data))
        else:
            healthy.append((row, score_data))
        if biggest_decline is None or score_data["growth_percent"] < biggest_decline[1]["growth_percent"]:
            biggest_decline = (row, score_data)
        if biggest_growth is None or score_data["growth_percent"] > biggest_growth[1]["growth_percent"]:
            biggest_growth = (row, score_data)

    def add_insight(kind: str, severity: str, title: str, message: str, franchise_id: int | None = None, data: Dict[str, Any] | None = None):
        db.session.add(BusinessInsight(
            insight_type=kind,
            severity=severity,
            title=title,
            message=message,
            year=year,
            month=month,
            franchise_id=franchise_id,
            data_json=json.dumps(data or {}),
        ))

    add_insight(
        "company_health",
        "info" if not critical else "warning",
        "Company health summary",
        f"{len(healthy)} healthy, {len(watch)} watch and {len(critical)} critical franchise records for {year}-{month:02d}.",
        data={"healthy": len(healthy), "watch": len(watch), "critical": len(critical)},
    )
    if biggest_growth:
        row, data = biggest_growth
        add_insight(
            "growth",
            "success",
            "Fastest growth detected",
            f"{row.get('business_name')} grew by {data['growth_percent']:.1f}% versus the previous month.",
            franchise_id=int(row.get("franchise_id")),
            data=data,
        )
    if biggest_decline and biggest_decline[1]["growth_percent"] < 0:
        row, data = biggest_decline
        add_insight(
            "decline",
            "danger" if data["growth_percent"] < -15 else "warning",
            "Largest decline detected",
            f"{row.get('business_name')} declined by {abs(data['growth_percent']):.1f}% versus the previous month.",
            franchise_id=int(row.get("franchise_id")),
            data=data,
        )
    for row, data in critical[:10]:
        add_insight(
            "franchise_health",
            "danger",
            f"{row.get('business_name')} is critical",
            "; ".join(data.get("reasons") or ["Health score is below threshold."]),
            franchise_id=int(row.get("franchise_id")),
            data=data,
        )

    if commit:
        db.session.commit()
    return {"year": year, "month": month, "snapshots": len(snapshots), "insights": BusinessInsight.query.filter_by(year=year, month=month).count()}


def get_intelligence_summary(year: int | None = None, month: int | None = None) -> Dict[str, Any]:
    period = latest_period() if not year or not month else {"year": int(year), "month": int(month)}
    year = int(period["year"])
    month = int(period["month"])
    total = FranchiseHealthSnapshot.query.filter_by(year=year, month=month).count()
    if total == 0:
        rebuild_business_intelligence(year, month, commit=True)
    status_rows = db.session.execute(text("""
        SELECT health_status, COUNT(*) AS count, COALESCE(AVG(health_score), 0) AS avg_score
        FROM franchise_health_snapshots
        WHERE year = :year AND month = :month
        GROUP BY health_status
    """), {"year": year, "month": month}).mappings().all()
    status = {row["health_status"]: {"count": int(row["count"]), "avg_score": round(_to_float(row["avg_score"]), 2)} for row in status_rows}
    avg_score = db.session.execute(text("""
        SELECT COALESCE(AVG(health_score), 0)
        FROM franchise_health_snapshots
        WHERE year = :year AND month = :month
    """), {"year": year, "month": month}).scalar()
    insights = BusinessInsight.query.filter_by(year=year, month=month, is_active=True).order_by(BusinessInsight.created_at.desc()).limit(12).all()
    return {"year": year, "month": month, "avg_score": round(_to_float(avg_score), 2), "status": status, "insights": insights}
