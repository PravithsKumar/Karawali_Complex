from datetime import datetime, date
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='VENDOR')  # 'ADMIN' or 'VENDOR'
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id', ondelete='SET NULL'), nullable=True)
    
    shop = db.relationship('Shop', backref=db.backref('user_account', uselist=False))
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    @property
    def is_admin(self):
        return self.role == 'ADMIN'


class Shop(db.Model):
    __tablename__ = 'shops'
    
    id = db.Column(db.Integer, primary_key=True)
    shop_number = db.Column(db.Integer, unique=True, nullable=False)  # 1 to 9
    name = db.Column(db.String(120), nullable=False)                 # e.g., 'Namana Saloon'
    tenant_name = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    monthly_rent = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    status = db.Column(db.String(20), default='ACTIVE', nullable=False)  # 'ACTIVE' or 'VACANT'
    
    # Financial balances
    past_pending_balance = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    advance_balance = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    pin = db.Column(db.String(10), default='1234', nullable=False)  # 4-digit PIN for vendor login
    
    # Relationships
    payments = db.relationship('Payment', backref='shop', cascade='all, delete-orphan', order_by='Payment.payment_date.desc(), Payment.id.desc()', lazy='dynamic')
    nudges = db.relationship('Nudge', backref='shop', cascade='all, delete-orphan', order_by='Nudge.created_at.desc()', lazy='dynamic')

    @property
    def is_active(self):
        return self.status == 'ACTIVE'
        
    def has_pending_nudge_today(self):
        today = date.today()
        nudge = self.nudges.filter_by(nudge_date=today, status='PENDING').first()
        return nudge is not None

    def get_financial_summary(self, year=None, month=None):
        """
        Computes the complete ledger snapshot for the specified month/year:
        - Target Monthly Rent
        - Total Paid This Month
        - This Month's Remaining
        - Past Pending Balance
        - Advance Balance
        - Total Net Outstanding
        """
        if year is None or month is None:
            today = date.today()
            year = today.year
            month = today.month
            
        # System officially starts from September 1, 2026
        if year < 2026 or (year == 2026 and month < 9):
            target_rent = Decimal('0.00')
        else:
            target_rent = Decimal(str(self.monthly_rent if self.is_active else 0.00))
        
        # Calculate sum of payments for the given month
        from sqlalchemy import extract, func
        month_payments_sum = db.session.query(func.coalesce(func.sum(Payment.amount), 0))\
            .filter(Payment.shop_id == self.id)\
            .filter(extract('year', Payment.payment_date) == year)\
            .filter(extract('month', Payment.payment_date) == month)\
            .scalar()
            
        total_paid_this_month = Decimal(str(month_payments_sum or 0.00))
        
        # Balance & extra calculations
        past_pending = Decimal(str(self.past_pending_balance or 0.00))
        advance = Decimal(str(self.advance_balance or 0.00))
        
        # If advance existed previously, it covers current month
        effective_rent = max(Decimal('0.00'), target_rent - advance)
        
        if total_paid_this_month >= effective_rent:
            this_month_remaining = Decimal('0.00')
            extra_paid = total_paid_this_month - effective_rent
        else:
            this_month_remaining = effective_rent - total_paid_this_month
            extra_paid = Decimal('0.00')
            
        # If extra was paid this month:
        # Rule 1: extra cuts past pending balance
        # Rule 2: if past pending is 0, it becomes future advance
        net_past_pending = past_pending
        net_advance = Decimal('0.00')
        
        if extra_paid > 0:
            if net_past_pending > 0:
                if extra_paid >= net_past_pending:
                    remaining_extra = extra_paid - net_past_pending
                    net_past_pending = Decimal('0.00')
                    net_advance = remaining_extra
                else:
                    net_past_pending -= extra_paid
            else:
                net_advance = extra_paid
                
        total_net_due = this_month_remaining + net_past_pending - net_advance
        
        return {
            'target_rent': float(target_rent),
            'total_paid_this_month': float(total_paid_this_month),
            'this_month_remaining': float(this_month_remaining),
            'past_pending': float(net_past_pending),
            'advance': float(net_advance),
            'total_net_due': float(total_net_due),
            'is_fulfilled': total_paid_this_month >= effective_rent and net_past_pending == 0,
            'percentage_paid': min(100.0, round((float(total_paid_this_month) / float(target_rent) * 100), 1)) if target_rent > 0 else 100.0
        }


class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id', ondelete='CASCADE'), nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=date.today)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_mode = db.Column(db.String(20), default='UPI', nullable=False)  # 'CASH', 'UPI', 'BANK'
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Nudge(db.Model):
    __tablename__ = 'nudges'
    
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id', ondelete='CASCADE'), nullable=False)
    nudge_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), default='PENDING', nullable=False)  # 'PENDING', 'RESOLVED'
    message = db.Column(db.String(255), default='Payment made today, please update ledger', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
