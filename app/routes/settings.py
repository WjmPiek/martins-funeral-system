from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import SystemSetting, AuditLog
settings_bp=Blueprint('settings',__name__,url_prefix='/settings')

def is_admin():
    role=(current_user.role.name if current_user.is_authenticated and current_user.role else '').lower().replace('_',' ')
    return role in {'admin','super admin','superadmin'}

@settings_bp.route('/', methods=['GET','POST'])
@login_required
def index():
    if not is_admin(): return redirect(url_for('main.dashboard'))
    if request.method=='POST':
        cat=request.form.get('category','General').strip() or 'General'; key=request.form.get('key','').strip(); value=request.form.get('value',''); desc=request.form.get('description','')
        if not key: flash('Setting key is required','danger'); return redirect(url_for('settings.index'))
        s=SystemSetting.query.filter_by(category=cat,key=key).first() or SystemSetting(category=cat,key=key)
        s.value=value; s.description=desc; s.active=bool(request.form.get('active')); s.updated_by_id=current_user.id
        db.session.add(s); db.session.add(AuditLog(user_id=current_user.id, action='Update system setting', entity_type='SystemSetting', entity_id=f'{cat}:{key}', details=value[:500])); db.session.commit(); flash('Setting saved','success')
        return redirect(url_for('settings.index', category=cat))
    category=request.args.get('category') or 'WhatsApp'
    settings=SystemSetting.query.filter_by(category=category).order_by(SystemSetting.key).all()
    categories=[r[0] for r in db.session.query(SystemSetting.category).distinct().order_by(SystemSetting.category).all()] or ['WhatsApp','Email','Call Script','Products','Documents','Outcomes','Targets','Branches']
    return render_template('settings/index.html', settings=settings, categories=categories, category=category)

@settings_bp.route('/seed')
@login_required
def seed():
    if not is_admin(): return redirect(url_for('main.dashboard'))
    defaults=[('WhatsApp','signature_reminder','Good day {client_name}, please complete your Martin\'s Funerals signing link: {link}'),('Email','missing_documents','Please send the outstanding documents for your application.'),('Outcomes','required_outcomes','No Answer\nInterested\nNot Interested\nCallback\nApplication Started\nSignature Sent'),('Documents','required_fica','id_copy\nproof_of_address\nbank_statement'),('Targets','daily_calls_per_agent','40')]
    for cat,key,val in defaults:
        if not SystemSetting.query.filter_by(category=cat,key=key).first(): db.session.add(SystemSetting(category=cat,key=key,value=val,description='Default Phase 7 setting',updated_by_id=current_user.id))
    db.session.commit(); flash('Default settings created','success'); return redirect(url_for('settings.index'))
