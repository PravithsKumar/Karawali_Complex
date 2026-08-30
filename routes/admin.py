from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, extract
from models import db, User, Shop, Payment, Nudge

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Access restricted to Admin only.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    today = date.today()
    default_month = 9 if (today.year == 2026 and today.month < 9) else today.month
    default_year = 2026 if (today.year == 2026 and today.month < 9) else today.year
    selected_year = int(request.args.get('year', default_year))
    selected_month = int(request.args.get('month', default_month))

    shops = Shop.query.order_by(Shop.shop_number).all()

    # Building-wide calculations: Start active tracking from September 2026
    if selected_year < 2026 or (selected_year == 2026 and selected_month < 9):
        total_target_rent = 0.0
    else:
        total_target_rent = sum(float(s.monthly_rent) for s in shops if s.is_active)
    
    # Payments for selected month
    month_payments_sum = db.session.query(func.coalesce(func.sum(Payment.amount), 0))\
        .filter(extract('year', Payment.payment_date) == selected_year)\
        .filter(extract('month', Payment.payment_date) == selected_month)\
        .scalar()
    total_collected_month = float(month_payments_sum or 0.00)

    # Payments for today
    today_cash = db.session.query(func.coalesce(func.sum(Payment.amount), 0))\
        .filter(Payment.payment_date == today, Payment.payment_mode == 'CASH')\
        .scalar()
    today_upi = db.session.query(func.coalesce(func.sum(Payment.amount), 0))\
        .filter(Payment.payment_date == today, Payment.payment_mode.in_(['UPI', 'BANK_TRANSFER']))\
        .scalar()
    total_collected_today = float((today_cash or 0) + (today_upi or 0))

    # Compile data per shop
    shop_cards = []
    total_building_pending = 0.0
    total_this_month_remaining = 0.0
    total_building_advance = 0.0

    for s in shops:
        summary = s.get_financial_summary(selected_year, selected_month)
        has_nudge = s.has_pending_nudge_today()
        
        total_building_pending += summary['past_pending']
        total_this_month_remaining += summary['this_month_remaining']
        total_building_advance += summary['advance']
        
        shop_cards.append({
            'shop': s,
            'summary': summary,
            'has_nudge': has_nudge
        })

    # Active pending nudges count
    pending_nudges_count = Nudge.query.filter_by(nudge_date=today, status='PENDING').count()

    return render_template(
        'admin/dashboard.html',
        shop_cards=shop_cards,
        total_target_rent=total_target_rent,
        total_collected_month=total_collected_month,
        total_collected_today=total_collected_today,
        today_cash=float(today_cash or 0),
        today_upi=float(today_upi or 0),
        total_building_pending=total_building_pending,
        total_this_month_remaining=total_this_month_remaining,
        total_building_advance=total_building_advance,
        pending_nudges_count=pending_nudges_count,
        selected_year=selected_year,
        selected_month=selected_month,
        today=today
    )


@admin_bp.route('/shops/<int:shop_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def shop_detail(shop_id):
    shop = Shop.query.get_or_404(shop_id)
    today = date.today()
    selected_year = int(request.args.get('year', today.year))
    selected_month = int(request.args.get('month', today.month))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_payment':
            pay_date_str = request.form.get('payment_date')
            amount = request.form.get('amount')
            mode = request.form.get('payment_mode', 'UPI')
            notes = request.form.get('notes', '').strip()

            try:
                pay_date = datetime.strptime(pay_date_str, '%Y-%m-%d').date() if pay_date_str else today
                amount_decimal = Decimal(amount)
                if amount_decimal <= 0:
                    flash('Payment amount must be greater than zero.', 'error')
                else:
                    payment = Payment(
                        shop_id=shop.id,
                        payment_date=pay_date,
                        amount=amount_decimal,
                        payment_mode=mode,
                        notes=notes
                    )
                    db.session.add(payment)

                    # Auto-resolve any pending nudge for this shop on that date
                    pending_nudges = Nudge.query.filter_by(shop_id=shop.id, nudge_date=pay_date, status='PENDING').all()
                    for n in pending_nudges:
                        n.status = 'RESOLVED'

                    db.session.commit()
                    flash(f'Payment of ₹{amount_decimal:,.2f} recorded for {shop.name}!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error recording payment: {str(e)}', 'error')

            return redirect(url_for('admin.shop_detail', shop_id=shop.id, year=selected_year, month=selected_month))

        elif action == 'update_settings':
            shop.name = request.form.get('name', shop.name).strip()
            shop.tenant_name = request.form.get('tenant_name', '').strip()
            shop.phone = request.form.get('phone', '').strip()
            shop.status = request.form.get('status', 'ACTIVE')
            shop.pin = request.form.get('pin', shop.pin).strip()
            
            try:
                shop.monthly_rent = Decimal(request.form.get('monthly_rent', '0.00'))
                shop.past_pending_balance = Decimal(request.form.get('past_pending_balance', '0.00'))
                shop.advance_balance = Decimal(request.form.get('advance_balance', '0.00'))
                db.session.commit()
                flash(f'Settings updated for {shop.name}!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating settings: {str(e)}', 'error')

            return redirect(url_for('admin.shop_detail', shop_id=shop.id, year=selected_year, month=selected_month))

    summary = shop.get_financial_summary(selected_year, selected_month)
    payments = shop.payments.filter(
        extract('year', Payment.payment_date) == selected_year,
        extract('month', Payment.payment_date) == selected_month
    ).all()
    
    all_payments = shop.payments.limit(100).all()
    pending_nudge = shop.nudges.filter_by(nudge_date=today, status='PENDING').first()

    return render_template(
        'admin/shop_detail.html',
        shop=shop,
        summary=summary,
        payments=payments,
        all_payments=all_payments,
        pending_nudge=pending_nudge,
        selected_year=selected_year,
        selected_month=selected_month,
        today=today
    )


@admin_bp.route('/daily-sheet', methods=['GET', 'POST'])
@login_required
@admin_required
def daily_sheet():
    today = date.today()
    sheet_date_str = request.args.get('date', today.strftime('%Y-%m-%d'))
    try:
        sheet_date = datetime.strptime(sheet_date_str, '%Y-%m-%d').date()
    except ValueError:
        sheet_date = today

    active_shops = Shop.query.filter_by(status='ACTIVE').order_by(Shop.shop_number).all()

    if request.method == 'POST':
        entries_saved = 0
        for shop in active_shops:
            amount_str = request.form.get(f'amount_{shop.id}', '').strip()
            mode = request.form.get(f'mode_{shop.id}', 'UPI')
            notes = request.form.get(f'notes_{shop.id}', '').strip()

            if amount_str:
                try:
                    amt = Decimal(amount_str)
                    if amt > 0:
                        payment = Payment(
                            shop_id=shop.id,
                            payment_date=sheet_date,
                            amount=amt,
                            payment_mode=mode,
                            notes=notes
                        )
                        db.session.add(payment)

                        # Auto-resolve nudge
                        pending_nudges = Nudge.query.filter_by(shop_id=shop.id, nudge_date=sheet_date, status='PENDING').all()
                        for n in pending_nudges:
                            n.status = 'RESOLVED'

                        entries_saved += 1
                except Exception:
                    pass

        if entries_saved > 0:
            db.session.commit()
            flash(f'Successfully logged {entries_saved} payments for {sheet_date.strftime("%d %b %Y")}!', 'success')
        else:
            flash('No payments entered to save.', 'info')

        return redirect(url_for('admin.daily_sheet', date=sheet_date.strftime('%Y-%m-%d')))

    # Existing payments for this date
    existing_payments = {}
    day_payments = Payment.query.filter_by(payment_date=sheet_date).all()
    for p in day_payments:
        if p.shop_id not in existing_payments:
            existing_payments[p.shop_id] = []
        existing_payments[p.shop_id].append(p)

    return render_template(
        'admin/daily_sheet.html',
        active_shops=active_shops,
        sheet_date=sheet_date,
        existing_payments=existing_payments,
        today=today
    )


@admin_bp.route('/payments/<int:payment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    shop_id = payment.shop_id
    db.session.delete(payment)
    db.session.commit()
    flash('Payment entry deleted.', 'info')
    return redirect(url_for('admin.shop_detail', shop_id=shop_id))


@admin_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@admin_required
def profile():
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('admin.profile'))

        if new_username and new_username != current_user.username:
            existing = User.query.filter_by(username=new_username).first()
            if existing and existing.id != current_user.id:
                flash('That username is already taken. Please choose another.', 'error')
                return redirect(url_for('admin.profile'))
            current_user.username = new_username

        if new_password:
            if new_password != confirm_password:
                flash('New password and confirm password do not match.', 'error')
                return redirect(url_for('admin.profile'))
            if len(new_password) < 4:
                flash('New password must be at least 4 characters long.', 'error')
                return redirect(url_for('admin.profile'))
            current_user.set_password(new_password)

        db.session.commit()
        flash('Your admin credentials have been successfully updated!', 'success')
        return redirect(url_for('admin.profile'))

    return render_template('admin/profile.html')


@admin_bp.route('/nudges/<int:nudge_id>/resolve', methods=['POST'])
@login_required
@admin_required
def resolve_nudge(nudge_id):
    nudge = Nudge.query.get_or_404(nudge_id)
    nudge.status = 'RESOLVED'
    db.session.commit()
    flash(f'Nudge for Shop {nudge.shop.shop_number} marked as resolved.', 'success')
    return redirect(request.referrer or url_for('admin.dashboard'))
