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
            return {
                'target_rent': 0.0,
                'total_paid_this_month': 0.0,
                'this_month_remaining': 0.0,
                'past_pending': 0.0,
                'advance': 0.0,
                'total_net_due': 0.0,
                'is_fulfilled': True,
                'percentage_paid': 100.0
            }

        from sqlalchemy import extract, func

        # Initial baseline before system launch (e.g. historical arrears set on Sep 30)
        current_pending = Decimal(str(self.past_pending_balance or 0.00))
        current_advance = Decimal(str(self.advance_balance or 0.00))

        # Generator for sequential month rollover from September 2026 up to viewed (year, month)
        def iter_months(s_y, s_m, e_y, e_m):
            cur_y, cur_m = s_y, s_m
            while (cur_y < e_y) or (cur_y == e_y and cur_m <= e_m):
                yield cur_y, cur_m
                cur_m += 1
                if cur_m > 12:
                    cur_m = 1
                    cur_y += 1

        target_rent = Decimal('0.00')
        total_paid_this_month = Decimal('0.00')
        this_month_remaining = Decimal('0.00')
        effective_rent = Decimal('0.00')

        for y, m in iter_months(2026, 9, year, month):
            is_target_month = (y == year and m == month)
            m_target = Decimal(str(self.monthly_rent if self.is_active else 0.00))

            # Shop 6 and 7 were vacant during September 2026; Shop 7 started in October 2026
            if self.shop_number in (6, 7) and (y == 2026 and m < 10):
                m_target = Decimal('0.00')

            m_paid_sum = db.session.query(func.coalesce(func.sum(Payment.amount), 0))\
                .filter(Payment.shop_id == self.id)\
                .filter(extract('year', Payment.payment_date) == y)\
                .filter(extract('month', Payment.payment_date) == m)\
                .scalar()
            m_paid = Decimal(str(m_paid_sum or 0.00))

            if is_target_month:
                target_rent = m_target
                total_paid_this_month = m_paid

            # Apply previous advance if available
            if current_advance > 0:
                if current_advance >= m_target:
                    effective_rent = Decimal('0.00')
                    current_advance -= m_target
                else:
                    effective_rent = m_target - current_advance
                    current_advance = Decimal('0.00')
            else:
                effective_rent = m_target

            if m_paid >= effective_rent:
                extra = m_paid - effective_rent
                remaining = Decimal('0.00')
                if extra > 0:
                    if current_pending > 0:
                        if extra >= current_pending:
                            extra -= current_pending
                            current_pending = Decimal('0.00')
                            current_advance += extra
                        else:
                            current_pending -= extra
                    else:
                        current_advance += extra
            else:
                remaining = effective_rent - m_paid
                if not is_target_month:
                    # Unpaid rent from previous months automatically rolls over into past pending dues!
                    current_pending += remaining

            if is_target_month:
                this_month_remaining = remaining

        total_net_due = this_month_remaining + current_pending - current_advance

        return {
            'target_rent': float(target_rent),
            'total_paid_this_month': float(total_paid_this_month),
            'this_month_remaining': float(this_month_remaining),
            'past_pending': float(current_pending),
            'advance': float(current_advance),
            'total_net_due': float(total_net_due),
            'is_fulfilled': total_paid_this_month >= effective_rent and current_pending == 0,
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
