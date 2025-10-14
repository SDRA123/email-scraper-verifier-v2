"""Initialize admin user"""
from database import SessionLocal
from models import User
from auth import get_password_hash

def create_admin_user():
    db = SessionLocal()
    try:
        # Check if admin already exists
        admin = db.query(User).filter(User.username == "admin").first()

        if admin:
            print("Admin user already exists")
            # Update password and ensure admin status
            admin.hashed_password = get_password_hash("admin")
            admin.is_admin = True
            admin.is_active = True
            db.commit()
            print("Admin user password reset to 'admin' and admin status confirmed")
        else:
            # Create new admin user
            admin = User(
                username="admin",
                email="admin@admin.com",
                hashed_password=get_password_hash("admin"),
                is_admin=True,
                is_active=True
            )
            db.add(admin)
            db.commit()
            print("Admin user created successfully!")
            print("Username: admin")
            print("Password: admin")
            print("⚠️  Please change the password after first login!")

    except Exception as e:
        print(f"Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()
