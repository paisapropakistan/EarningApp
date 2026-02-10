from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os
from sqlalchemy import text
import random
import uuid
from flask import Flask, send_from_directory, render_template
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import os

app = Flask(__name__)

# ================= ENVIRONMENT CONFIG =================
# PostgreSQL / SQLite fallback
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or "sqlite:///paisapro.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Secret Key
app.secret_key = os.environ.get("SECRET_KEY") or "dev_secret_key"


UPLOAD_FOLDER = 'static/uploads/screenshots'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# ================= DATABASE MODELS =================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    plan = db.Column(db.String(50), default="Free")
    daily_ads = db.Column(db.Integer, default=0)
    last_reset = db.Column(db.Date, default=date.today)
    is_admin = db.Column(db.Boolean, default=False)
    
    # === Nayi Fields Referral System ke liye ===
    # Har user ki apni Unique ID (e.g. A1B2C3D4)
    referral_code = db.Column(db.String(20), unique=True) 
    
    # Kis user ne isay invite kiya (Inviter ka code save hoga)
    referred_by = db.Column(db.String(20)) 
    
    # Sirf referral se kitna kamaya (Optional: Tracking ke liye)
    referral_balance = db.Column(db.Float, default=0.0) 
    last_bonus_date = db.Column(db.Date, nullable=True) 


#pyment method
class PaymentRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plan_name = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    tid = db.Column(db.String(100), nullable=False)
    screenshot = db.Column(db.String(200)) 
    status = db.Column(db.String(20), default='Pending')

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    type = db.Column(db.String(100))
    amount = db.Column(db.Float)
    details = db.Column(db.String(200))
    status = db.Column(db.String(50), default="Pending")

# ================= DATABASE FIXER (CRITICAL) =================
# Ye section aapka OperationalError theek karega
with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            # Check if column exists, if not, add it
            conn.execute(text("ALTER TABLE payment_request ADD COLUMN screenshot VARCHAR(200)"))
            conn.commit()
            print("✅ Screenshot column added successfully!")
    except Exception:
        # Agar column pehle se hai to error skip karega
        pass

# ================= ROUTES =================

# Route to serve images from templates folder
@app.route('/images/<filename>')
def template_images(filename):
    return send_from_directory(os.path.join(app.root_path, 'templates'), filename)

@app.route("/")
def index():
    # 1. Login Check (Sab se pehle check karein user logged in hai ya nahi)
    if "user_id" not in session: 
        return redirect(url_for('login'))
        
    user = User.query.get(session["user_id"])
    
    # 2. Daily Ads Reset Logic (Jo aapne likhi thi, kuch remove nahi kiya)
    if user and user.last_reset != date.today():
        user.daily_ads = 0
        user.last_reset = date.today()
        db.session.commit()
            
    # 3. Leaderboard Data (Top 5 earners)
    # Dono variables 'leaderboard' aur 'earners' bhej raha hoon taake HTML mein jo bhi naam ho, masla na ho
    top_earners = User.query.order_by(User.balance.desc()).limit(5).all()
    
    # 4. Fake Online Counter Logic
    online_now = random.randint(1100, 1900)
    
    # 5. Final Return (Ek hi return mein sara data bhej diya)
    return render_template("index.html", 
                           user=user, 
                           leaderboard=top_earners, 
                           earners=top_earners, 
                           online=online_now)


import uuid


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = generate_password_hash(request.form.get("password"))
        
        # URL ya Form se referral code pakre ga
        ref_code = request.args.get("ref") or request.form.get("ref_code")
        
        if User.query.filter_by(email=email).first():
            flash("Email pehle se maujood hai!", "error")
            return redirect(url_for("register"))
            
        # Naya user banate waqt usay Unique UID dena
        user_uid = str(uuid.uuid4())[:8].upper() 
        
        new_user = User(
            username=username, 
            email=email, 
            password=password,
            referral_code=user_uid,
            referred_by=ref_code, # Sirf yaad rakhega kisne bulaya, paise abhi nahi milenge
            balance=0.0,
            daily_ads=0,
            plan="Free"
        )
        
        db.session.add(new_user)
        db.session.commit()
        flash(f"Account Created! Your UID is {user_uid}", "success")
        return redirect(url_for("login"))
        
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            return redirect(url_for("index"))
        flash("Ghalat email ya password!", "error")
    return render_template("login.html")
    
    

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))
    

@app.route("/buy_plan", methods=["POST"])
def buy_plan():
    if "user_id" not in session: return redirect(url_for("login"))
    
    user_id = session["user_id"]
    plan_name = request.form.get("plan_name")
    amount = request.form.get("amount")
    tid = request.form.get("tid")
    file = request.files.get('screenshot')
    
    if not tid or not file:
        flash("TID aur Screenshot dono lazmi hain!", "error")
        return redirect(url_for("index"))
        
    if file:
        # Unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = secure_filename(f"TID_{tid}_{timestamp}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        new_request = PaymentRequest(
            user_id=user_id, 
            plan_name=plan_name, 
            amount=float(amount), 
            tid=tid,
            screenshot=filename
        )
        db.session.add(new_request)
        db.session.commit()
        
        flash(f"{plan_name} request submit ho gayi! Admin verify kar raha hai.", "success")
    
    return redirect(url_for("index"))



@app.route("/withdraw")
def withdraw_page():
    if "user_id" not in session: return redirect(url_for('login'))
    user = User.query.get(session["user_id"])
    return render_template("withdraw.html", user=user)

@app.route("/submit_withdrawal", methods=["POST"])
def submit_withdrawal():
    if "user_id" not in session: return redirect(url_for('login'))
    
    user = User.query.get(session["user_id"])
    method = request.form.get("method")
    account_no = request.form.get("details")
    
    try:
        amount = float(request.form.get("amount"))
    except:
        flash("Sahi raqam likhein!", "error")
        return redirect(url_for('withdraw_page'))
    
    if amount < 2000:
        flash("Minimum withdrawal Rs. 2000 hai!", "error")
        return redirect(url_for('withdraw_page'))
    
    if amount > user.balance:
        flash("Aapka balance kam hai!", "error")
        return redirect(url_for('withdraw_page'))
    
    new_request = Transaction(
        user_id=user.id,
        type=f"Withdraw ({method})",
        amount=amount,
        details=account_no,
        status="Pending"
    )
    
    user.balance -= amount
    db.session.add(new_request)
    db.session.commit()
    
    flash(f"Rs. {amount} ki request bhej di gayi hai!", "success")
    return redirect(url_for('index'))
    
    

@app.route("/watch-ads")
def watch_ads_page():
    if "user_id" not in session: return redirect(url_for('login'))
    user = User.query.get(session["user_id"])
    
    # Extra safety: Yahan bhi reset logic daal dein
    if user.last_reset != date.today():
        user.daily_ads = 0
        user.last_reset = date.today()
        db.session.commit()
        
    return render_template("watch_ads.html", user=user)

    
    
    
@app.route("/api/complete_ad", methods=["POST"])
def complete_ad():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Please Login First!"}), 401
    
    user = User.query.get(session["user_id"])
    
    # ================= NEW LOGIC: LOW REWARD + HIGH LIMIT =================
    if user.plan == "Gold":
        # Gold Plan: Rs. 0.60 per ad
        # Rs. 50 kamane ke liye takreeban 84 ads chahiye
        limit = 700 
        reward = 0.60
    elif user.plan == "Diamond":
        # Diamond Plan: Maan lete hain Rs. 1.0 per ad
        limit = 1000
        reward = 1.0
    else:  
        # Free Plan: Rs. 0.50 per ad
        # Rs. 50 kamane ke liye 100 ads lazmi hain
        limit = 300
        reward = 0.50
    # ======================================================================

    # 1. Check limit
    if user.daily_ads >= limit: 
        return jsonify({
            "status": "error", 
            "message": f"Daily limit reached! You have completed your {limit} ads for today."
        })
    
    # 2. Database update
    user.balance += reward
    user.daily_ads += 1
    db.session.commit()
    
    return jsonify({
        "status": "success", 
        "message": f"Rs. {reward} added to balance! ({user.daily_ads}/{limit} ads)",
        "new_balance": round(user.balance, 2) # Balance ko point mein saaf dikhane ke liye
    })


@app.route("/add_reward")
def add_reward():
    if "user_id" not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session["user_id"])
    
    # Plans ke mutabiq limits (Jo humne pehle set ki thi)
    if user.plan == "Diamond":
        limit = 1000
        reward = 1.00
    elif user.plan == "Gold":
        limit = 700
        reward = 0.60
    else:
        limit = 300
        reward = 0.50

    # Ads Limit Check
    if user.daily_ads < limit:
        user.balance += reward
        user.daily_ads += 1
        db.session.commit()
        flash(f"Mubarak! Rs. {reward} balance mein add ho gaye.", "success")
    else:
        flash(f"Aapki daily limit ({limit} ads) puri ho chuki hai!", "error")
        
    # FORCE REDIRECT: Ab ye hamesha ads page par hi rakhega
    return redirect(url_for('watch_ads_page'))





# ==========================================
#         ADMIN PANEL ROUTES (STABLE)
# ==========================================

# --- 1. ADMIN DASHBOARD ---
@app.route("/admin/dashboard")
def admin_dashboard():
    # Login Check
    if "user_id" not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session["user_id"])
    
    # HARDCODED ADMIN ACCESS (Ali Abbas Bhai Power)
    if user and (user.email == 'paisapropakistan@gmail.com' or 
                 user.username == 'aliabbas786' or 
                 user.is_admin):
        
        # Pending Upgrades (Plan changes)
        upgrades = PaymentRequest.query.filter_by(status='Pending').all()
        # Pending Withdrawals (Paisa nikalna)
        withdraws = Transaction.query.filter_by(status='Pending').all() 
        
        return render_template("admin_panel.html", upgrades=upgrades, withdraws=withdraws)
    
    return "Unauthorized Access!", 403

# --- 2. APPROVE PLAN UPGRADE ---
@app.route("/admin/approve_plan/<int:id>")
def approve_plan(id):
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    
    # Admin Access Check
    if not (admin.email == 'paisapropakistan@gmail.com' or admin.is_admin): 
        return "Unauthorized", 403

    req = PaymentRequest.query.get(id)
    if req:
        user = User.query.get(req.user_id)
        
        # ================= REFERRAL BONUS LOGIC (NEW) =================
        # 1. Check karein kya is user ko kisi ne invite kiya tha?
        # 2. Check karein kya ye user pehli baar plan buy kar raha hai (Free to Paid)?
        if user.referred_by and user.plan == "Free":
            inviter = User.query.filter_by(referral_code=user.referred_by).first()
            if inviter:
                inviter.balance += 100.0  # Inviter ko Rs. 50 mil gaye
                inviter.referral_balance += 100.0 # Record ke liye
                print(f"💰 Referral Success: Rs. 100 added to {inviter.username}")
        # =============================================================

        # Plan Update
        user.plan = req.plan_name
        
        # Reset ads limit on new plan activation
        user.daily_ads = 0
        user.last_reset = date.today() # Taake usi din se nayi limit shuru ho
            
        req.status = "Approved"
        db.session.commit()
        
        flash(f"User {user.username} approved for {req.plan_name}! Referral bonus processed.", "success")
        
    return redirect(url_for('admin_dashboard'))

# --- 3. REJECT PLAN UPGRADE ---
@app.route("/admin/reject_plan/<int:id>")
def reject_plan(id):
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    if not (admin.email == 'paisapropakistan@gmail.com' or admin.is_admin): return "Unauthorized", 403

    req = PaymentRequest.query.get(id)
    if req:
        req.status = "Rejected"
        db.session.commit()
        flash("Plan request rejected.", "danger")
    return redirect(url_for('admin_dashboard'))

# --- 4. APPROVE WITHDRAW (PAID) ---
@app.route("/admin/approve_withdraw/<int:id>")
def approve_withdraw(id):
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    if not (admin.email == 'paisapropakistan@gmail.com' or admin.is_admin): return "Unauthorized", 403

    trans = Transaction.query.get(id)
    if trans:
        trans.status = "Paid"  # Status update kar diya
        db.session.commit()
        flash("Withdrawal marked as PAID!", "success")
    return redirect(url_for('admin_dashboard'))

# --- 5. REJECT WITHDRAW ---
@app.route("/admin/reject_withdraw/<int:id>")
def reject_withdraw(id):
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    if not (admin.email == 'paisapropakistan@gmail.com' or admin.is_admin): return "Unauthorized", 403

    trans = Transaction.query.get(id)
    if trans:
        # Pese wapis user ke balance mein daalna (Optional but fair)
        user = User.query.get(trans.user_id)
        user.balance += trans.amount
        
        trans.status = "Rejected"
        db.session.commit()
        flash("Withdrawal rejected and amount refunded.", "danger")
    return redirect(url_for('admin_dashboard'))





@app.route("/claim_daily")
def claim_daily():
    if "user_id" not in session: 
        return redirect(url_for('login'))
        
    user = User.query.get(session["user_id"])
    today = date.today()

    # CHECK: Kya user aaj pehle hi bonus le chuka hai?
    if user.last_bonus_date == today:
        flash("Aap aaj ka bonus pehle hi claim kar chuke hain! Kal wapis aayein.", "error")
        return redirect(url_for('index'))

    # Reward Logic: Agar aaj nahi liya to bonus dein
    bonus_amount = round(random.uniform(1.0, 5.0), 2)
    user.balance += bonus_amount
    user.last_bonus_date = today # Aaj ki date save kar dein
    
    db.session.commit()
    
    flash(f"Mubarak! Rs. {bonus_amount} Daily Bonus aapke account mein add ho gaya.", "success")
    return redirect(url_for('index'))



if __name__ == "__main__":
    app.run(debug=True, port=5000)
