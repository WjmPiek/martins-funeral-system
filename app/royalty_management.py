"""Enterprise Royalty Management subsystem (Phase 9).

This layer does not change the existing royalty calculation formula.  It wraps
that formula with agreement profiles, GDP/growth policy, calculation snapshots,
diagnostics and rebuild services so every result is traceable and repeatable.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from app.extensions import db
from app.models import (
    Franchise,
    MonthlyFigure,
    RoyaltyAgreementProfile,
    RoyaltyCalculationSnapshot,
    RoyaltyGrowthProfile,
)
from app.royalty_engine import calculate_monthly_figure, decimal_value, select_royalty_method

DEFAULT_GDP_GROWTH_PERCENT = Decimal("1.6000")
DEFAULT_PROFILE_NAME = "South Africa GDP Standard"


def _json(value) -> str:
    return json.dumps(value or {}, default=str)


def utcnow():
    return datetime.now(timezone.utc)


def ensure_default_growth_profile(commit: bool = False) -> RoyaltyGrowthProfile:
    profile = RoyaltyGrowthProfile.query.filter_by(name=DEFAULT_PROFILE_NAME).first()
    if not profile:
        profile = RoyaltyGrowthProfile(
            name=DEFAULT_PROFILE_NAME,
            source="SA GDP standard",
            default_growth_percent=DEFAULT_GDP_GROWTH_PERCENT,
            scope_type="global",
            is_active=True,
            notes="Default royalty target growth policy. Admin may change this in future; franchise users do not see this setting.",
        )
        db.session.add(profile)
        db.session.flush()
    if commit:
        db.session.commit()
    return profile


def agreement_version_for(franchise: Franchise, method: str) -> str:
    start = getattr(franchise, "agreement_start_date", None)
    if start:
        return f"agreement-{start.year}-{method}"
    return f"missing-agreement-{method}"


def agreement_profile_for(franchise: Franchise, *, month: Optional[int] = None, year: Optional[int] = None, commit: bool = False) -> RoyaltyAgreementProfile | None:
    if not franchise:
        return None
    growth_profile = ensure_default_growth_profile(commit=False)
    method, source, warnings, errors = select_royalty_method(franchise, period_month=month, period_year=year)
    start = getattr(franchise, "agreement_start_date", None)
    end = getattr(franchise, "agreement_end_date", None)
    version = agreement_version_for(franchise, method)

    query = RoyaltyAgreementProfile.query.filter_by(
        franchise_id=franchise.id,
        agreement_version=version,
        formula_version="current_scale",
    )
    profile = query.first()
    if not profile:
        profile = RoyaltyAgreementProfile(
            franchise_id=franchise.id,
            agreement_version=version,
            formula_version="current_scale",
            royalty_method=method,
            target_method="previous_year_average_plus_growth",
            growth_profile_id=growth_profile.id,
            effective_start_date=start,
            effective_end_date=end,
            is_active=True,
            notes=f"Auto-created from franchise agreement fields. Method source: {source}.",
        )
        db.session.add(profile)
        db.session.flush()
    else:
        profile.royalty_method = method
        profile.effective_start_date = start
        profile.effective_end_date = end
        if not profile.growth_profile_id:
            profile.growth_profile_id = growth_profile.id
    if commit:
        db.session.commit()
    return profile


def previous_year_average(franchise_id: int, year: int) -> Decimal:
    rows = MonthlyFigure.query.filter_by(franchise_id=franchise_id, year=int(year) - 1).all()
    if not rows:
        return Decimal("0")
    total = sum(decimal_value(getattr(row, "gross_turnover", 0)) for row in rows)
    return total / Decimal(len(rows)) if rows else Decimal("0")


def target_for_month(franchise_id: int, year: int, growth_percent: Decimal) -> tuple[Decimal, Decimal]:
    avg = previous_year_average(franchise_id, year)
    target = avg * (Decimal("1") + (decimal_value(growth_percent) / Decimal("100")))
    return avg.quantize(Decimal("0.01")), target.quantize(Decimal("0.01"))


def snapshot_monthly_figure(monthly_figure: MonthlyFigure, *, commit: bool = False) -> RoyaltyCalculationSnapshot:
    result = calculate_monthly_figure(monthly_figure)
    franchise = monthly_figure.franchise or Franchise.query.get(monthly_figure.franchise_id)
    profile = agreement_profile_for(franchise, month=monthly_figure.month, year=monthly_figure.year, commit=False) if franchise else None
    growth_profile = profile.growth_profile if profile and profile.growth_profile else ensure_default_growth_profile(commit=False)
    custom_growth = getattr(profile, "custom_growth_percent", None) if profile else None
    growth_percent = decimal_value(custom_growth, "0")
    if growth_percent == Decimal("0"):
        growth_percent = decimal_value(getattr(growth_profile, "default_growth_percent", DEFAULT_GDP_GROWTH_PERCENT), DEFAULT_GDP_GROWTH_PERCENT)
    avg, target = target_for_month(monthly_figure.franchise_id, monthly_figure.year, growth_percent)

    diagnostics = {
        "agreement_found": bool(getattr(franchise, "agreement_start_date", None)),
        "agreement_start_date": str(getattr(franchise, "agreement_start_date", "") or ""),
        "agreement_end_date": str(getattr(franchise, "agreement_end_date", "") or ""),
        "agreement_profile_id": getattr(profile, "id", None),
        "agreement_version": getattr(profile, "agreement_version", ""),
        "formula_version": getattr(profile, "formula_version", "current_scale"),
        "method": result.method,
        "method_source": result.method_source,
        "scale_source_franchise_id": result.scale_source_franchise_id,
        "scale_source_franchise_name": result.scale_source_franchise_name,
        "growth_profile": getattr(growth_profile, "name", ""),
        "growth_percent": str(growth_percent),
        "warnings": result.warnings,
        "blocking_errors": result.blocking_errors,
    }
    status = "needs_review" if result.blocking_errors else "calculated"

    snapshot = RoyaltyCalculationSnapshot.query.filter_by(monthly_figure_id=monthly_figure.id).first()
    if not snapshot:
        snapshot = RoyaltyCalculationSnapshot(monthly_figure_id=monthly_figure.id, franchise_id=monthly_figure.franchise_id)
        db.session.add(snapshot)

    snapshot.franchise_id = monthly_figure.franchise_id
    snapshot.year = monthly_figure.year
    snapshot.month = monthly_figure.month
    snapshot.agreement_profile_id = getattr(profile, "id", None)
    snapshot.agreement_version = getattr(profile, "agreement_version", "")
    snapshot.formula_version = getattr(profile, "formula_version", "current_scale")
    snapshot.royalty_method = result.method
    snapshot.method_source = result.method_source
    snapshot.royalty_base = result.royalty_base
    snapshot.royalty_percentage = result.royalty_percentage
    snapshot.royalty_amount = result.royalty_amount
    snapshot.minimum_royalty_amount = result.minimum_royalty_amount
    snapshot.minimum_royalty_applied = result.minimum_royalty_applied
    snapshot.scale_source_franchise_id = result.scale_source_franchise_id
    snapshot.scale_source_franchise_name = result.scale_source_franchise_name or ""
    snapshot.growth_profile_id = getattr(growth_profile, "id", None)
    snapshot.growth_percent = growth_percent
    snapshot.previous_year_average = avg
    snapshot.target_amount = target
    snapshot.status = status
    snapshot.diagnostics_json = _json(diagnostics)
    snapshot.calculated_at = utcnow()

    monthly_figure.status = "Needs Review" if status == "needs_review" else "Calculated"
    monthly_figure.notes = (monthly_figure.notes or "")
    if result.blocking_errors:
        marker = "Royalty needs review: " + "; ".join(result.blocking_errors)
        if marker not in monthly_figure.notes:
            monthly_figure.notes = (monthly_figure.notes + "\n" + marker).strip()
    if commit:
        db.session.commit()
    return snapshot


def recalculate_royalties_for_period(month: int, year: int, franchise_ids: Optional[Iterable[int]] = None, *, commit: bool = True) -> dict:
    query = MonthlyFigure.query.filter_by(month=int(month), year=int(year))
    if franchise_ids:
        query = query.filter(MonthlyFigure.franchise_id.in_(list(franchise_ids)))
    rows = query.order_by(MonthlyFigure.franchise_id).all()
    total = 0
    needs_review = 0
    calculated = 0
    errors = 0
    error_details = []
    for row in rows:
        total += 1
        try:
            snapshot = snapshot_monthly_figure(row, commit=False)
            if snapshot.status == "needs_review":
                needs_review += 1
            else:
                calculated += 1
        except Exception as exc:
            errors += 1
            needs_review += 1
            franchise_name = getattr(getattr(row, "franchise", None), "business_name", "") or f"Franchise #{getattr(row, 'franchise_id', '')}"
            error_details.append({
                "monthly_figure_id": getattr(row, "id", None),
                "franchise_id": getattr(row, "franchise_id", None),
                "franchise_name": franchise_name,
                "error": str(exc),
            })
            row.status = "Needs Review"
            marker = f"Royalty rebuild error: {exc}"
            notes = row.notes or ""
            if marker not in notes:
                row.notes = (notes + "\n" + marker).strip()
            continue
    if commit:
        try:
            from app.events import emit_event
            emit_event(
                "royalty.recalculated",
                source="royalty_management",
                title=f"Royalties recalculated for {year}-{int(month):02d}",
                message=f"{calculated} calculated, {needs_review} need review, {errors} errors.",
                payload={"month": int(month), "year": int(year), "total": total, "calculated": calculated, "needs_review": needs_review, "errors": errors, "error_details": error_details[:50]},
                year=int(year),
                month=int(month),
                aggregate_type="royalties",
            )
        except Exception:
            pass
        db.session.commit()
    return {"month": int(month), "year": int(year), "total": total, "calculated": calculated, "needs_review": needs_review, "errors": errors, "error_details": error_details}


def royalty_management_summary() -> dict:
    ensure_default_growth_profile(commit=False)
    snapshot_rows = db.session.execute(db.text("""
        SELECT status, COUNT(*) AS count
        FROM royalty_calculation_snapshots
        GROUP BY status
    """)).mappings().all()
    snapshot_status = {row["status"]: int(row["count"] or 0) for row in snapshot_rows}
    latest = RoyaltyCalculationSnapshot.query.order_by(RoyaltyCalculationSnapshot.calculated_at.desc()).limit(15).all()
    missing_snapshot_count = db.session.execute(db.text("""
        SELECT COUNT(*)
        FROM monthly_figures mf
        LEFT JOIN royalty_calculation_snapshots rcs ON rcs.monthly_figure_id = mf.id
        WHERE rcs.id IS NULL
    """)).scalar() or 0
    return {
        "growth_profiles": RoyaltyGrowthProfile.query.order_by(RoyaltyGrowthProfile.name).all(),
        "agreement_profiles": RoyaltyAgreementProfile.query.count(),
        "snapshots": snapshot_status,
        "snapshot_total": sum(snapshot_status.values()),
        "missing_snapshot_count": int(missing_snapshot_count),
        "latest_snapshots": latest,
    }
