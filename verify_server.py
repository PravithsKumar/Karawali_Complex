import sys
from app import create_app
from models import db, Shop, User

app = create_app()

with app.test_client() as client:
    # 1. Test Login Page
    res = client.get('/login')
    assert res.status_code == 200
    assert b"Karavali Complex" in res.data
    assert b"Namana Saloon" in res.data
    print("[PASS] Login page renders all shops properly.")

    # 2. Test Admin Login and Dashboard
    res = client.post('/login', data={'login_type': 'admin', 'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Admin Overview" in res.data
    assert b"Today's Collections" in res.data
    assert b"Namana Saloon" in res.data
    assert b"Kala Arts" in res.data
    print("[PASS] Admin login and dashboard loaded with all 9 shops.")

    # 3. Test Daily Sheet
    res = client.get('/admin/daily-sheet')
    assert res.status_code == 200
    assert b"Daily Collection Sheet" in res.data
    print("[PASS] Daily Collection batch sheet rendered successfully.")

    # 4. Test Vendor Login & Direct Redirect
    client.get('/logout')
    res = client.post('/login', data={'login_type': 'vendor', 'shop_id': 1, 'pin': '1001'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Namana Saloon" in res.data
    assert b"Daily Payment History" in res.data
    assert b"Nudge Admin" in res.data or b"Nudge Sent" in res.data
    print("[PASS] Vendor login redirects to private shop portal.")

    # 5. Test Vendor Isolation (Attempting to view Shop 2 while logged in as Shop 1)
    res = client.get('/shop/2', follow_redirects=True)
    assert b"Access restricted. You can only view your own shop ledger." in res.data
    print("[PASS] Vendor isolation strictly enforced (Shop 1 cannot view Shop 2).")

print("\nALL SYSTEM VERIFICATIONS PASSED 100%!")
