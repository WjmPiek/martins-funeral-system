
import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models import RecoveryCallLog, CallSummary, CallRecording, ComplianceFlag, AuditLog
from app.security import require_manager_or_admin

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')

def _simple_ai_summary(call):
    text=(call.notes or '') + ' ' + (call.outcome or '')
    lower=text.lower()
    flags=[]
    if 'complaint' in lower or 'angry' in lower: flags.append('Possible complaint')
    if 'not explained' in lower or 'confused' in lower: flags.append('Product explanation risk')
    if 'bank' in lower and 'confirm' not in lower: flags.append('Check debit-order confirmation')
    next_action='Follow normal callback process'
    if 'no answer' in lower: next_action='Retry call later today or tomorrow'
    elif 'interested' in lower: next_action='Send application/signing link'
    elif 'fica' in lower: next_action='Request outstanding FICA documents'
    summary=f"Outcome: {call.outcome}. Notes captured: {(call.notes or '')[:300]}"
    return summary,next_action,flags

@analytics_bp.route('/')
@login_required
def index():
    blocked=require_manager_or_admin()
    if blocked: return blocked
    summaries=CallSummary.query.order_by(CallSummary.created_at.desc()).limit(20).all()
    flags=ComplianceFlag.query.order_by(ComplianceFlag.created_at.desc()).limit(20).all()
    recordings=CallRecording.query.order_by(CallRecording.uploaded_at.desc()).limit(20).all()
    return render_template('analytics/index.html', summaries=summaries, flags=flags, recordings=recordings)

@analytics_bp.route('/summarize/<int:call_log_id>', methods=['POST'])
@login_required
def summarize(call_log_id):
    call=db.session.get(RecoveryCallLog, call_log_id)
    if not call:
        flash('Call log not found.','danger'); return redirect(url_for('analytics.index'))
    summary,next_action,flags=_simple_ai_summary(call)
    cs=CallSummary(call_log_id=call.id, summary=summary, next_best_action=next_action, risk_flags='; '.join(flags))
    db.session.add(cs)
    for f in flags:
        db.session.add(ComplianceFlag(call_log_id=call.id, flag_type=f, severity='medium', details=summary))
    db.session.add(AuditLog(user_id=current_user.id, action='CALL_SUMMARY_CREATED', entity_type='call_log', entity_id=str(call.id), details='AI-style rule summary generated'))
    db.session.commit(); flash('Call summary generated.','success')
    return redirect(url_for('analytics.index'))

@analytics_bp.route('/upload-recording/<int:call_log_id>', methods=['POST'])
@login_required
def upload_recording(call_log_id):
    f=request.files.get('recording')
    if not f or not f.filename:
        flash('Choose a recording file.','warning'); return redirect(url_for('analytics.index'))
    folder=os.path.join(current_app.config['UPLOAD_FOLDER'],'call_recordings')
    os.makedirs(folder, exist_ok=True)
    name=secure_filename(f.filename)
    path=os.path.join(folder, f"call_{call_log_id}_{name}")
    f.save(path)
    rec=CallRecording(call_log_id=call_log_id, agent_id=current_user.id, file_path=path, original_filename=name)
    db.session.add(rec); db.session.commit(); flash('Recording uploaded.','success')
    return redirect(url_for('analytics.index'))
