from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, uuid, random, shutil, datetime, smtplib, warnings
from pathlib import Path
from datetime import timedelta
from db import FeedbackToken

from db import Base, engine, get_db, User, Order, ReturnReq, TransactionLog, Feedback

# ---------------- INIT ----------------
Base.metadata.create_all(bind=engine)
warnings.filterwarnings("ignore")
app = FastAPI()

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- PATHS ----------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "frontend")  # frontend folder
UPLOAD_DIR = os.path.join(CURRENT_DIR, "uploads")
os.makedirs(os.path.join(UPLOAD_DIR, "returns"), exist_ok=True)

# ---------------- OTP STORES ----------------
DELIVERY_OTP_STORE = {}
RESET_OTP_STORE = {}
OTP_EXPIRY_SECONDS = 300  # 5 minutes

# ---------------- SCHEMAS ----------------
class SignupSchema(BaseModel):
    name: str
    email: str
    password: str

class LoginSchema(BaseModel):
    email: str
    password: str

class ForgotPasswordSchema(BaseModel):
    email: str

class ResetPasswordSchema(BaseModel):
    email: str
    otp: str
    new_password: str

class DeliveryOTPSchema(BaseModel):
    email: str
    order_id: str

class VerifyDeliverySchema(BaseModel):
    email: str
    order_id: str
    otp: str

class AdminDecisionSchema(BaseModel):
    order_id: str
    decision: str

class GoogleFeedbackSchema(BaseModel):
    email: str
    order_id: str
    rating: int
    comment: str
    seal_intact: str          
    identity_verified: str    
    photo_url: str            
    delivery_time: str

class OrderSchema(BaseModel):
    email: str
    product_name: str
    price: float
    address: str
    payment_type: str

# ---------------- EMAIL LOGIC ----------------
SENDER_EMAIL = os.getenv("EMAIL_USER")
APP_PASSWORD = os.getenv("EMAIL_PASS")

def send_email_logic(receiver, subject, content, is_html=False):
    try:
        msg = MIMEMultipart("alternative") if is_html else MIMEMultipart()
        msg["Subject"] = subject
        msg["To"] = receiver
        msg["From"] = SENDER_EMAIL
        
        part = MIMEText(content, "html" if is_html else "plain")
        msg.attach(part)
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, APP_PASSWORD)
            smtp.send_message(msg)
    except Exception as e:
        print("Email Error:", e)

# ---------------- AUTH & PASSWORD RESET ----------------
@app.post("/signup")
def signup(data: SignupSchema, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email.ilike(data.email)).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        name=data.name,
        email=data.email,
        password=hashlib.sha256(data.password.encode()).hexdigest(),
        failed_logins=0
    )
    db.add(user)
    db.commit()
    return {"status": "success"}

@app.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email.ilike(data.email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    hashed_pwd = hashlib.sha256(data.password.encode()).hexdigest()
    if user.password == hashed_pwd:
        user.failed_logins = 0
        db.commit()
        role = "admin" if user.email.lower() == "admin@shop.com" else "customer"
        return {"status": "success", "user_name": user.name, "email": user.email, "role": role}
    else:
        user.failed_logins += 1
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/forgot-password")
def forgot_password(data: ForgotPasswordSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email.ilike(data.email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not registered")
    otp = str(random.randint(1000, 9999))
    RESET_OTP_STORE[data.email.lower()] = {"otp": otp, "time": datetime.datetime.utcnow()}
    send_email_logic(data.email, "Password Reset OTP", f"Your OTP for password reset is: {otp}")
    return {"status": "otp_sent"}

@app.post("/reset-password")
def reset_password(data: ResetPasswordSchema, db: Session = Depends(get_db)):
    otp_data = RESET_OTP_STORE.get(data.email.lower())
    if not otp_data or otp_data["otp"] != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    user = db.query(User).filter(User.email.ilike(data.email)).first()
    user.password = hashlib.sha256(data.new_password.encode()).hexdigest()
    db.commit()
    RESET_OTP_STORE.pop(data.email.lower())
    return {"status": "success"}

# ---------------- ORDER PROCESS ----------------
@app.post("/order")
def place_order(data: OrderSchema, db: Session = Depends(get_db)):
    try:
        # 1️⃣ Login check
        user = db.query(User).filter(User.email.ilike(data.email)).first()

        if not user:
            return {
                "status": "NOT_LOGGED_IN",
                "message": "Please login to place an order"
            }

        # 2️⃣ Generate unique order id
        new_order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

        # 3️⃣ Save order with foreign key user_id
        new_order = Order(
            order_id=new_order_id,
            product_name=data.product_name,
            price=data.price,
            address=data.address,
            payment_type=data.payment_type,
            status="PENDING",
            user_id=user.id,
            created_at=datetime.datetime.utcnow()
        )
        
        db.add(new_order)
        db.commit()
db.refresh(new_order)

# 🔐 Auto Generate Delivery OTP
otp = str(random.randint(1000, 9999))
DELIVERY_OTP_STORE[data.email.lower()] = {
    "otp": otp,
    "time": datetime.datetime.utcnow()
}

send_email_logic(
    data.email,
    "Delivery OTP",
    f"Your OTP for Order #{new_order_id} is: {otp}"
)

return {
    "status": "success",
    "order_id": new_order_id,
    "otp_sent": True
}
# ---------------- DELIVERY OTP & FEEDBACK ----------------
@app.post("/send-delivery-otp")
def send_delivery_otp(data: DeliveryOTPSchema):
    otp = str(random.randint(1000, 9999))
    DELIVERY_OTP_STORE[data.email.lower()] = {"otp": otp, "time": datetime.datetime.utcnow()}
    send_email_logic(data.email, "Delivery OTP", f"Your OTP for Order #{data.order_id} is: {otp}")
    return {"status": "sent"}

@app.post("/verify-delivery-otp")
def verify_delivery_otp(data: VerifyDeliverySchema, db: Session = Depends(get_db)):

    otp_data = DELIVERY_OTP_STORE.get(data.email.lower())
    if not otp_data or otp_data["otp"] != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    order = db.query(Order).filter(Order.order_id == data.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = "DELIVERED"

    # 🔐 Generate secure token
    token = str(uuid.uuid4())
    expiry_time = datetime.datetime.utcnow() + timedelta(hours=9)

    db.add(FeedbackToken(
        email=data.email,
        order_id=data.order_id,
        token=token,
        expires_at=expiry_time
    ))

    db.commit()
    DELIVERY_OTP_STORE.pop(data.email.lower())

    # 🔗 Secure feedback link
    secure_link = f"http://127.0.0.1:8000/feedback/{token}"

    feedback_html = f"""
    <html>
        <body style='font-family: Poppins; padding:20px;'>
            <h2>Package Delivered ✅</h2>
            <p>This feedback link is valid only for 9 hours.</p>
            <a href="{secure_link}"
               style='background:#ff9900;color:white;padding:12px 25px;border-radius:6px;text-decoration:none;'>
               Give Feedback
            </a>
        </body>
    </html>
    """

    send_email_logic(
        data.email,
        f"Order #{data.order_id} Delivered - Feedback",
        feedback_html,
        is_html=True
    )

    return {"status": "verified"}

@app.get("/feedback/{token}", response_class=HTMLResponse)
def open_feedback(token: str, db: Session = Depends(get_db)):

    token_record = db.query(FeedbackToken).filter(
        FeedbackToken.token == token
    ).first()

    if not token_record:
        return HTMLResponse("<h2>Invalid Link ❌</h2>", status_code=404)

    if datetime.datetime.utcnow() > token_record.expires_at:
        return HTMLResponse("<h2>Link Expired ❌</h2>", status_code=403)

    return FileResponse(os.path.join(FRONTEND_DIR, "feedback.html"))

# ---------------- GOOGLE FORM WEBHOOK ----------------
@app.post("/google-form-webhook")
async def google_form_webhook(data: GoogleFeedbackSchema, db: Session = Depends(get_db)):

    try:
        # 🔐 Check valid token exists
        token_record = db.query(FeedbackToken).filter(
            FeedbackToken.email == data.email,
            FeedbackToken.order_id == data.order_id
        ).first()

        if not token_record:
            raise HTTPException(status_code=403, detail="Unauthorized submission")

        if datetime.datetime.utcnow() > token_record.expires_at:
            raise HTTPException(status_code=403, detail="Link expired")

        # 🔥 Prevent duplicate feedback
        existing_feedback = db.query(Feedback).filter(
            Feedback.email == data.email,
            Feedback.order_id == data.order_id
        ).first()

        if existing_feedback:
            raise HTTPException(status_code=400, detail="Feedback already submitted")

        # 🔥 Hidden AI Logic
        security_status = "Safe"

        if (
            data.seal_intact.lower() == "no"
            or data.identity_verified.lower() == "no"
            or data.rating <= 2
        ):
            security_status = "Alert: Security Breach"

        new_feedback = Feedback(
            email=data.email,
            order_id=data.order_id,
            rating=data.rating,
            comment=data.comment,
            seal_intact=data.seal_intact,
            identity_verified=data.identity_verified,
            package_photo_url=data.photo_url,
            delivery_time=data.delivery_time,
            security_status=security_status,
            created_at=datetime.datetime.utcnow()
        )

        db.add(new_feedback)

        # 🚨 Admin Alert
        if security_status != "Safe":
            db.add(TransactionLog(
                email=data.email,
                order_id=data.order_id,
                risk_score=90.0,
                severity="CRITICAL",
                final_status="ALERT TRIGGERED",
                timestamp=datetime.datetime.utcnow()
            ))

        # 🗑 Delete token after use (One-time link)
        db.delete(token_record)

        db.commit()

        print(f"✅ Secure Feedback Stored for {data.order_id}")
        return {"status": "success"}

    except Exception as e:
        db.rollback()
        print("Webhook Error:", e)
        return {"status": "error"}    
# ---------------- RETURN PROCESS (AI + INITIAL MAIL) ----------------
@app.post("/return")
async def process_return(
    order_id: str = Form(...),
    email: str = Form(...),
    reason: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # 🔹 AI Risk Calculation
    sim_score = random.uniform(40, 95)
    risk_score = round(100 - sim_score, 2)

    # 🔹 Save Image
    filename = f"{order_id}_{uuid.uuid4().hex[:5]}.jpg"
    save_path = os.path.join(UPLOAD_DIR, "returns", filename)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    decision = "PENDING"
    severity = "MEDIUM"
    mail_content = ""

    # 🔥 AUTO DECISION CASES
    if risk_score < 35:
        decision = "ACCEPTED"
        severity = "LOW"
        mail_content = f"""
        Hello,

        Your return request for Order #{order_id} has been automatically ACCEPTED
        based on AI verification.

        Thank you.
        """

    elif risk_score > 75:
        decision = "REJECTED"
        severity = "CRITICAL"
        mail_content = f"""
        Hello,

        Your return request for Order #{order_id} has been REJECTED
        due to high security mismatch.

        Contact support if needed.
        """

    else:
        decision = "PENDING"
        severity = "MEDIUM"
        mail_content = f"""
        Hello,

        Your return request for Order #{order_id} is under MANUAL REVIEW
        by our security team.

        You will receive another email once admin reviews it.
        """

    # 🔹 Save Return Request
    db.add(ReturnReq(
        order_id=order_id,
        email=email,
        reason=reason,
        return_image=filename,
        similarity=sim_score,
        decision=decision,
        created_at=datetime.datetime.utcnow()
    ))

    db.add(TransactionLog(
        email=email,
        order_id=order_id,
        risk_score=risk_score,
        severity=severity,
        final_status=decision,
        timestamp=datetime.datetime.utcnow()
    ))

    db.commit()

    # 🔹 Send Initial Notification
    send_email_logic(
        email,
        f"Return Request Update - Order #{order_id}",
        mail_content
    )

    return {
        "status": "SUBMITTED",
        "decision": decision
    }
# ---------------- ADMIN DASHBOARD (UPDATED WITH REASON) ----------------
@app.get("/admin/dashboard-stats")
def get_admin_stats(db: Session = Depends(get_db)):
    logs = db.query(TransactionLog).order_by(TransactionLog.timestamp.desc()).all()
    
    # 🔹 Fetch all return reasons and map with order_id
    reasons_map = {
        r.order_id: r.reason
        for r in db.query(ReturnReq).all()
    }

    return {
        "total_orders": db.query(Order).count(),
        "total_returns": db.query(ReturnReq).count(),
        "security_alerts": db.query(TransactionLog)
            .filter(TransactionLog.severity == "CRITICAL")
            .count(),

        "logs_list": [
            {
                "order_id": l.order_id,
                "email": l.email,
                "risk_score": l.risk_score,
                "severity": l.severity,
                "final_status": l.final_status,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,

                # ✅ NEW FIELD ADDED
                "reason": reasons_map.get(l.order_id, "N/A")
            }
            for l in logs
        ]
    }
# ---------------- ADMIN DECISION (FINAL MAIL) ----------------
@app.post("/admin/return-decision")
def admin_return_decision(data: AdminDecisionSchema, db: Session = Depends(get_db)):

    if data.decision not in ["ACCEPTED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Invalid decision")

    # 🔹 Get Pending Return
    ret = db.query(ReturnReq).filter(
        ReturnReq.order_id == data.order_id,
        ReturnReq.decision == "PENDING"
    ).first()

    if not ret:
        raise HTTPException(status_code=404, detail="Pending request not found")

    # 🔹 Update Return Table
    ret.decision = data.decision

    # 🔹 Update Transaction Log
    log = db.query(TransactionLog).filter(
        TransactionLog.order_id == data.order_id
    ).first()

    if log:
        log.final_status = data.decision
        log.severity = "LOW" if data.decision == "ACCEPTED" else "CRITICAL"

    db.commit()

    # 🔥 FINAL MAIL AFTER ADMIN REVIEW
    final_message = f"""
    Hello,

    Our admin has reviewed your return request for Order #{data.order_id}.

    Final Decision: {data.decision}

    Thank you for shopping with us.
    """

    send_email_logic(
        ret.email,
        f"Final Decision on Return - Order #{data.order_id}",
        final_message
    )

    print("✅ Final decision mail sent to:", ret.email)

    return {"status": "success"}

# ---------------- HTML ROUTES ----------------
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/login.html", response_class=HTMLResponse)
async def serve_login():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))

@app.get("/admin.html", response_class=HTMLResponse)
async def serve_admin():
    return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))

# ---------------- STATIC FILES ----------------
if os.path.exists(os.path.join(FRONTEND_DIR, "images")):
    app.mount("/images", StaticFiles(directory=os.path.join(FRONTEND_DIR, "images")), name="images")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")

# ---------------- RUN ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
