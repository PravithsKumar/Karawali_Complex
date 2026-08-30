import os
import calendar
from datetime import datetime, date
from flask import Flask
from flask_login import LoginManager
from config import Config
from models import db, User

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.vendor import vendor_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(vendor_bp)

    # Jinja2 template filters
    @app.template_filter('inr')
    def inr_format(value):
        try:
            val = float(value or 0)
            # Format Indian style: e.g. 12,345
            formatted = f"{val:,.2f}".rstrip('0').rstrip('.') if val % 1 == 0 else f"{val:,.2f}"
            return f"₹{formatted}"
        except (ValueError, TypeError):
            return f"₹{value}"

    @app.template_filter('format_date')
    def format_date_filter(d, fmt='%d %b %Y'):
        if not d:
            return '-'
        if isinstance(d, (datetime, date)):
            return d.strftime(fmt)
        return str(d)

    @app.template_filter('month_name')
    def month_name_filter(month_num):
        try:
            return calendar.month_name[int(month_num)]
        except Exception:
            return str(month_num)

    @app.context_processor
    def inject_globals():
        return {
            'current_year': date.today().year,
            'current_month': date.today().month,
            'today_date': date.today()
        }

    return app

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # Accessible locally and via network on port 5000
    app.run(debug=True, host='0.0.0.0', port=5000)
