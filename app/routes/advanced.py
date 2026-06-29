from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models import RecoveryCallLog, LapsedPolicy, PolicyProduct
from app.services.branch_access import scope_by_branch
advanced_bp=Blueprint('advanced',__name__,url_prefix='/advanced')
def is_manager():
    role=(current_user.role.name if current_user.is_authenticated and current_user.role else '').lower().replace('_',' ')
    return role in {'admin','manager','branch manager'}
@advanced_bp.route('/')
@login_required
def index():
    if not is_manager(): return redirect(url_for('main.dashboard'))
    recent=RecoveryCallLog.query.filter(RecoveryCallLog.agent_id==current_user.id).order_by(RecoveryCallLog.created_at.desc()).limit(20).all()
    high_value=scope_by_branch(LapsedPolicy.query.filter(LapsedPolicy.premium_due>0), LapsedPolicy, agent_col=LapsedPolicy.assigned_agent_id).order_by(LapsedPolicy.premium_due.desc()).limit(20).all()
    products=PolicyProduct.query.filter_by(active=True).order_by(PolicyProduct.monthly_premium).limit(20).all()
    return render_template('advanced/index.html', recent=recent, high_value=high_value, products=products)
