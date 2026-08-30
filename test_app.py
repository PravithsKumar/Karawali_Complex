import unittest
from decimal import Decimal
from datetime import date, timedelta
from app import create_app
from models import db, User, Shop, Payment, Nudge

class KaravaliComplexTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            # Seed Admin
            admin = User(username='admin', role='ADMIN')
            admin.set_password('admin123')
            db.session.add(admin)

            # Seed Shop 1 (Namana Saloon, 4000)
            shop1 = Shop(
                shop_number=1,
                name='Namana Saloon',
                monthly_rent=Decimal('4000.00'),
                status='ACTIVE',
                pin='1001',
                past_pending_balance=Decimal('500.00'), # 500 pending from past
                advance_balance=Decimal('0.00')
            )
            db.session.add(shop1)

            # Seed Shop 2 (Ozo Tech Mobiles, 3000)
            shop2 = Shop(
                shop_number=2,
                name='Ozo Tech Mobiles',
                monthly_rent=Decimal('3000.00'),
                status='ACTIVE',
                pin='1002'
            )
            db.session.add(shop2)
            db.session.commit()

            # Create Vendor Users
            v1 = User(username='shop_1', role='VENDOR', shop_id=shop1.id)
            v1.set_password('1001')
            db.session.add(v1)

            v2 = User(username='shop_2', role='VENDOR', shop_id=shop2.id)
            v2.set_password('1002')
            db.session.add(v2)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_financial_calculation_and_advance_rules(self):
        """Test daily ledger calculations, pending balance, and advance rollover"""
        with self.app.app_context():
            shop1 = Shop.query.get(1)
            today = date.today()

            # Initially: target 4000, 0 paid, past pending 500
            fin1 = shop1.get_financial_summary(today.year, today.month)
            self.assertEqual(fin1['target_rent'], 4000.0)
            self.assertEqual(fin1['total_paid_this_month'], 0.0)
            self.assertEqual(fin1['this_month_remaining'], 4000.0)
            self.assertEqual(fin1['past_pending'], 500.0)
            self.assertEqual(fin1['total_net_due'], 4500.0)

            # Pay 2000 (partial payment)
            p1 = Payment(shop_id=1, payment_date=today, amount=Decimal('2000.00'), payment_mode='UPI')
            db.session.add(p1)
            db.session.commit()

            fin2 = shop1.get_financial_summary(today.year, today.month)
            self.assertEqual(fin2['total_paid_this_month'], 2000.0)
            self.assertEqual(fin2['this_month_remaining'], 2000.0)
            self.assertEqual(fin2['past_pending'], 500.0)
            self.assertEqual(fin2['total_net_due'], 2500.0)

            # Pay extra: Add 2500 more -> Total paid = 4500. Target was 4000.
            # Extra 500 should clear the 500 past pending!
            p2 = Payment(shop_id=1, payment_date=today, amount=Decimal('2500.00'), payment_mode='CASH')
            db.session.add(p2)
            db.session.commit()

            fin3 = shop1.get_financial_summary(today.year, today.month)
            self.assertEqual(fin3['total_paid_this_month'], 4500.0)
            self.assertEqual(fin3['this_month_remaining'], 0.0)
            self.assertEqual(fin3['past_pending'], 0.0)
            self.assertEqual(fin3['advance'], 0.0)
            self.assertEqual(fin3['total_net_due'], 0.0)

            # Pay another 300 extra -> Now past pending is 0, so 300 becomes advance credit!
            p3 = Payment(shop_id=1, payment_date=today, amount=Decimal('300.00'), payment_mode='UPI')
            db.session.add(p3)
            db.session.commit()

            fin4 = shop1.get_financial_summary(today.year, today.month)
            self.assertEqual(fin4['total_paid_this_month'], 4800.0)
            self.assertEqual(fin4['advance'], 300.0)
            self.assertEqual(fin4['total_net_due'], -300.0)

    def test_vendor_login_and_isolation(self):
        """Ensure Vendor cannot access /admin or other vendor shop pages"""
        # Login as Shop 1 Vendor
        res = self.client.post('/login', data={
            'login_type': 'vendor',
            'shop_id': 1,
            'pin': '1001'
        }, follow_redirects=True)
        self.assertIn(b'Namana Saloon', res.data)

        # Try to access Admin Dashboard -> Must be blocked and redirected
        admin_res = self.client.get('/admin/', follow_redirects=True)
        self.assertIn(b'Access restricted to Admin only', admin_res.data)

        # Try to access Shop 2 Portal -> Must be redirected to Shop 1
        shop2_res = self.client.get('/shop/2', follow_redirects=True)
        self.assertIn(b'Access restricted. You can only view your own shop ledger', shop2_res.data)

    def test_nudge_and_auto_resolution(self):
        """Test vendor 1-tap nudge and auto-resolution upon payment logging"""
        # 1. Vendor triggers nudge
        self.client.post('/login', data={'login_type': 'vendor', 'shop_id': 1, 'pin': '1001'}, follow_redirects=True)
        nudge_res = self.client.post('/shop/1/nudge', follow_redirects=True)
        self.assertIn(b'Nudge sent! Admin has been notified', nudge_res.data)

        with self.app.app_context():
            nudge = Nudge.query.filter_by(shop_id=1, status='PENDING').first()
            self.assertIsNotNone(nudge)

        # 2. Admin logs in and records payment for today
        self.client.get('/logout', follow_redirects=True)
        self.client.post('/login', data={'login_type': 'admin', 'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        
        today_str = date.today().strftime('%Y-%m-%d')
        pay_res = self.client.post('/admin/shops/1', data={
            'action': 'add_payment',
            'payment_date': today_str,
            'amount': '500.00',
            'payment_mode': 'UPI',
            'notes': 'Settled nudge'
        }, follow_redirects=True)
        self.assertIn(b'Payment of', pay_res.data)

        # 3. Verify nudge is auto-resolved
        with self.app.app_context():
            nudge = Nudge.query.filter_by(shop_id=1).first()
            self.assertEqual(nudge.status, 'RESOLVED')

if __name__ == '__main__':
    unittest.main()
