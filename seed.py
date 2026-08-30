import os
from decimal import Decimal
from datetime import date, timedelta
from app import create_app
from models import db, User, Shop, Payment, Nudge

app = create_app()

SHOPS_DATA = [
    {"number": 1, "name": "Namana Saloon", "rent": Decimal("4000.00"), "status": "ACTIVE", "pin": "1001", "tenant": "Namana"},
    {"number": 2, "name": "Ozo Tech Mobiles", "rent": Decimal("3000.00"), "status": "ACTIVE", "pin": "1002", "tenant": "Ozo Tech"},
    {"number": 3, "name": "Matha Canteen", "rent": Decimal("7000.00"), "status": "ACTIVE", "pin": "1003", "tenant": "Matha"},
    {"number": 4, "name": "Kala Arts", "rent": Decimal("2500.00"), "status": "ACTIVE", "pin": "1004", "tenant": "Kala"},
    {"number": 5, "name": "Tailors", "rent": Decimal("3500.00"), "status": "ACTIVE", "pin": "1005", "tenant": "Tailor Master"},
    {"number": 6, "name": "Shop 6 (Vacant)", "rent": Decimal("0.00"), "status": "VACANT", "pin": "1006", "tenant": None},
    {"number": 7, "name": "Shop 7 (Vacant)", "rent": Decimal("0.00"), "status": "VACANT", "pin": "1007", "tenant": None},
    {"number": 8, "name": "Chinese Fast Food", "rent": Decimal("9000.00"), "status": "ACTIVE", "pin": "1008", "tenant": "Fast Food Chef"},
    {"number": 9, "name": "Fresh Chicken", "rent": Decimal("8000.00"), "status": "ACTIVE", "pin": "1009", "tenant": "Fresh Chicken Center"},
]

def seed_database():
    with app.app_context():
        print("Creating database tables...")
        db.create_all()

        # 1. Admin User
        admin_user = User.query.filter_by(role='ADMIN').first()
        if not admin_user:
            admin_user = User(
                username="admin",
                role="ADMIN"
            )
            admin_user.set_password("admin123")
            db.session.add(admin_user)
            print("Created Admin user: username='admin', password='admin123'")
        else:
            print("Admin user already exists.")

        # 2. Shops & Vendor accounts
        for data in SHOPS_DATA:
            shop = Shop.query.filter_by(shop_number=data["number"]).first()
            if not shop:
                shop = Shop(
                    shop_number=data["number"],
                    name=data["name"],
                    monthly_rent=data["rent"],
                    status=data["status"],
                    pin=data["pin"],
                    tenant_name=data["tenant"],
                    past_pending_balance=Decimal("0.00"),
                    advance_balance=Decimal("0.00")
                )
                db.session.add(shop)
                db.session.flush()  # get shop.id
                print(f"Created Shop {data['number']}: {data['name']} (Rent: Rs. {data['rent']}, PIN: {data['pin']})")
            else:
                shop.name = data["name"]
                shop.monthly_rent = data["rent"]
                shop.status = data["status"]
                shop.pin = data["pin"]

            # Ensure corresponding vendor user account exists
            vendor_user = User.query.filter_by(shop_id=shop.id).first()
            if not vendor_user:
                vendor_user = User(
                    username=f"shop_{shop.shop_number}",
                    role="VENDOR",
                    shop_id=shop.id
                )
                vendor_user.set_password(data["pin"])
                db.session.add(vendor_user)

        db.session.commit()

        print("Database initialized clean for September 1!")

if __name__ == "__main__":
    seed_database()
