from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Shop

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        elif current_user.shop_id:
            return redirect(url_for('vendor.shop_portal', shop_id=current_user.shop_id))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        elif current_user.shop_id:
            return redirect(url_for('vendor.shop_portal', shop_id=current_user.shop_id))

    shops = Shop.query.order_by(Shop.shop_number).all()

    if request.method == 'POST':
        login_type = request.form.get('login_type', 'vendor')

        if login_type == 'admin':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            user = User.query.filter_by(username=username, role='ADMIN').first()
            if user and user.check_password(password):
                login_user(user, remember=True)
                flash('Welcome back, Admin!', 'success')
                return redirect(url_for('admin.dashboard'))
            else:
                flash('Invalid admin credentials. Please try again.', 'error')

        elif login_type == 'vendor':
            shop_id = request.form.get('shop_id')
            pin = request.form.get('pin', '').strip()

            shop = db.session.get(Shop, int(shop_id))
            if shop and shop.pin == pin:
                # Find or create vendor user account for this shop
                user = User.query.filter_by(role='VENDOR', shop_id=shop.id).first()
                if not user:
                    user = User(
                        username=f"vendor_shop_{shop.shop_number}",
                        role='VENDOR',
                        shop_id=shop.id
                    )
                    user.set_password(pin)
                    db.session.add(user)
                    db.session.commit()

                login_user(user, remember=True)
                flash(f'Welcome, {shop.name}!', 'success')
                return redirect(url_for('vendor.shop_portal', shop_id=shop.id))
            else:
                flash('Invalid Shop PIN. Please check and try again.', 'error')

    return render_template('login.html', shops=shops)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
