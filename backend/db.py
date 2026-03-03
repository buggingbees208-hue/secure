from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import datetime

# ---------------- DATABASE CONNECTION ----------------
DATABASE_URL = "postgresql://security3_user:KhYDop2NR4BawQnXecJWLiUXfUKLF8mq@dpg-d6in21fgi27c738m72u0-a.oregon-postgres.render.com/security3"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------- USER TABLE ----------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    failed_logins = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    orders = relationship("Order", back_populates="owner", cascade="all, delete")
    transactions = relationship("TransactionLog", back_populates="user", cascade="all, delete")

# ---------------- ORDER TABLE ----------------
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    order_id = Column(String(50), unique=True, index=True, nullable=False)
    product_name = Column(String(150), nullable=False)
    price = Column(Float, nullable=False)
    address = Column(String(255), nullable=False)
    payment_type = Column(String(50), nullable=False)
    status = Column(String(50), default="PENDING", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="orders")
    feedbacks = relationship("Feedback", back_populates="parent_order", cascade="all, delete-orphan")

# ---------------- RETURN REQUEST TABLE ----------------
class ReturnReq(Base):
    __tablename__ = "returns"

    id = Column(Integer, primary_key=True)
    order_id = Column(String(50), ForeignKey("orders.order_id"))
    email = Column(String(150))
    reason = Column(String(150))
    description = Column(Text, nullable=True)
    return_image = Column(String(255))
    similarity = Column(Float)
    decision = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# ---------------- TRANSACTION LOG TABLE ----------------
class TransactionLog(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    order_id = Column(String(50))
    email = Column(String(150))
    risk_score = Column(Float)
    similarity = Column(Float)
    severity = Column(String(50))
    final_status = Column(String(50))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", back_populates="transactions")


class FeedbackToken(Base):
    __tablename__ = "feedback_tokens"

    id = Column(Integer, primary_key=True)
    email = Column(String(255))
    order_id = Column(String(50))
    token = Column(String(255), unique=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# ---------------- UPDATED FEEDBACK TABLE ----------------
class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True)
    order_id = Column(String(50), ForeignKey("orders.order_id"))
    email = Column(String(150))
    rating = Column(Integer)
    comment = Column(Text)

    # 🔥 Newly Added Columns
    seal_intact = Column(String(10))
    identity_verified = Column(String(10))
    package_photo_url = Column(String(255))
    delivery_time = Column(String(100))
    security_status = Column(String(100))

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    parent_order = relationship("Order", back_populates="feedbacks")

# ---------------- DATABASE INIT ----------------
def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------- FEEDBACK INSERT FUNCTION ----------------
def insert_feedback(
    db,
    order_id,
    email,
    rating,
    comment,
    seal_intact,
    identity_verified,
    photo_url,
    delivery_time
):
    """
    Google Form data database-la insert pannum.
    Background-la AI Security Status check pannum.
    """

    # 🔍 Hidden AI Security Logic
    security_status = "Safe"

    if (
        seal_intact.lower() == "no"
        or identity_verified.lower() == "no"
        or rating <= 2
    ):
        security_status = "Alert: Security Breach"

    new_feedback = Feedback(
        order_id=order_id,
        email=email,
        rating=rating,
        comment=comment,
        seal_intact=seal_intact,
        identity_verified=identity_verified,
        package_photo_url=photo_url,
        delivery_time=delivery_time,
        security_status=security_status,
        created_at=datetime.datetime.utcnow()
    )

    db.add(new_feedback)
    db.commit()
    db.refresh(new_feedback)

    print(f"✅ Feedback stored for Order: {order_id}")
    print(f"🔒 Internal Security Scan: {security_status}")

    return new_feedback


if __name__ == "__main__":
    create_tables()
    print("✅ Database tables initialized successfully in 'security3'!")


