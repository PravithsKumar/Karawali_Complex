from datetime import datetime, date
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import extract
from models import db, Shop, Payment, Nudge

vendor_bp = Blueprint('vendor', __name__, url_prefix='/shop')

def vendor_access_required(f):
    @wraps(f)
    def decorated_function(shop_id, *args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        # Admin can view any shop; vendor can ONLY view their own assigned shop
        if not current_user.is_admin and current_user.shop_id != shop_id:
            flash('Access restricted. You can only view your own shop ledger.', 'error')
            return redirect(url_for('vendor.shop_portal', shop_id=current_user.shop_id))
        return f(shop_id, *args, **kwargs)
    return decorated_function


@vendor_bp.route('/<int:shop_id>')
@login_required
@vendor_access_required
def shop_portal(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    today = date.today()
    default_month = 9 if (today.year == 2026 and today.month < 9) else today.month
    default_year = 2026 if (today.year == 2026 and today.month < 9) else today.year
    selected_year = int(request.args.get('year', default_year))
    selected_month = int(request.args.get('month', default_month))

    summary = shop.get_financial_summary(selected_year, selected_month)

    # Monthly payments
    payments = shop.payments.filter(
        extract('year', Payment.payment_date) == selected_year,
        extract('month', Payment.payment_date) == selected_month
    ).all()

    # All recent payments history
    all_payments = shop.payments.limit(50).all()

    # Check if a nudge was already sent today
    today_nudge = shop.nudges.filter_by(nudge_date=today, status='PENDING').first()
    has_nudged_today = today_nudge is not None

    # Check if today's payment is already recorded
    today_payment = shop.payments.filter_by(payment_date=today).first()

    return render_template(
        'vendor/portal.html',
        shop=shop,
        summary=summary,
        payments=payments,
        all_payments=all_payments,
        has_nudged_today=has_nudged_today,
        today_payment=today_payment,
        selected_year=selected_year,
        selected_month=selected_month,
        today=today
    )


@vendor_bp.route('/<int:shop_id>/nudge', methods=['POST'])
@login_required
@vendor_access_required
def send_nudge(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    today = date.today()

    existing_nudge = shop.nudges.filter_by(nudge_date=today, status='PENDING').first()
    if existing_nudge:
        flash('Nudge already sent to Admin for today! Please allow some time for update.', 'info')
    else:
        nudge = Nudge(
            shop_id=shop.id,
            nudge_date=today,
            status='PENDING',
            message=f"{shop.name} reported payment done for today. Please update ledger."
        )
        db.session.add(nudge)
        db.session.commit()
        flash('Nudge sent! Admin has been notified to update today’s payment.', 'success')

    return redirect(url_for('vendor.shop_portal', shop_id=shop.id))
