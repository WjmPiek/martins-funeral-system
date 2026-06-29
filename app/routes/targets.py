
from datetime import date, datetime, time
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, ClientApplication, RecoveryCallLog, SalesTarget, CommissionRule, AuditLog
from app.security import require_manager_or_admin, is_admin_user
from app.services.branch_access import user_branch, selected_branch_arg, branch_choices_from_model

targets_bp = Blueprint("targets", __name__, url_prefix="/targets")

def _month(): return request.args.get("month") or date.today().strftime("%Y-%m")
def _bounds(month):
    y,m=[int(x) for x in month.split('-')]
    start=datetime(y,m,1)
    end=datetime(y+1,1,1) if m==12 else datetime(y,m+1,1)
    return start,end

@targets_bp.route("/", methods=["GET","POST"])
@login_required
def index():
    blocked=require_manager_or_admin()
    if blocked: return blocked
    month=_month(); branch=selected_branch_arg() if is_admin_user() else user_branch()
    if request.method=='POST':
        uid=request.form.get('user_id', type=int) or None
        branch=request.form.get('branch') or branch
        target=SalesTarget(user_id=uid, branch=branch, month=request.form.get('month') or month, calls_target=request.form.get('calls_target',type=int) or 0, sales_target=request.form.get('sales_target',type=int) or 0, premium_target=request.form.get('premium_target') or 0)
        db.session.add(target); db.session.add(AuditLog(user_id=current_user.id, action='TARGET_CREATED', entity_type='sales_target', entity_id=str(uid or branch), details='Sales target created'))
        db.session.commit(); flash('Target saved.','success'); return redirect(url_for('targets.index', branch=branch or '', month=month))
    start,end=_bounds(month)
    users=User.query
    if branch: users=users.filter(User.branch==branch)
    rows=[]
    for u in users.order_by(User.name).all():
        sales=ClientApplication.query.filter(ClientApplication.agent_id==u.id, ClientApplication.created_at>=start, ClientApplication.created_at<end).count()
        premium=db.session.query(db.func.coalesce(db.func.sum(ClientApplication.monthly_premium),0)).filter(ClientApplication.agent_id==u.id, ClientApplication.created_at>=start, ClientApplication.created_at<end).scalar() or 0
        calls=RecoveryCallLog.query.filter(RecoveryCallLog.agent_id==u.id, RecoveryCallLog.created_at>=start, RecoveryCallLog.created_at<end).count()
        t=SalesTarget.query.filter_by(user_id=u.id, month=month).order_by(SalesTarget.id.desc()).first()
        rows.append({'user':u,'calls':calls,'sales':sales,'premium':premium,'target':t,'sales_progress':round(sales/(t.sales_target or 1)*100,1) if t else 0})
    branches=branch_choices_from_model(db, ClientApplication)
    rules=CommissionRule.query.filter_by(active=True).all()
    return render_template('targets/index.html', rows=rows, branch=branch, month=month, branches=branches, rules=rules)

@targets_bp.route('/commission-rules', methods=['POST'])
@login_required
def commission_rules():
    blocked=require_manager_or_admin()
    if blocked: return blocked
    rule=CommissionRule(name=request.form.get('name') or 'Default rule', role_name=request.form.get('role_name') or 'agent', flat_amount_per_sale=request.form.get('flat_amount_per_sale') or 0, percentage_of_premium=request.form.get('percentage_of_premium') or 0)
    db.session.add(rule); db.session.commit(); flash('Commission rule saved.','success')
    return redirect(url_for('targets.index'))
