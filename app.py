from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date
import os
from sqlalchemy import text
import random
import uuid
import secrets

app = Flask(__name__)

# ================= ENVIRONMENT CONFIG =================
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or "sqlite:///paisapro.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    referral_code = db.Column(db.String(20), unique=True)
    referred_by = db.Column(db.String(20))
    referral_balance = db.Column(db.Float, default=0.0)
    last_bonus_date = db.Column(db.Date, nullable=True)

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

# ================= DATABASE FIXER =================
with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE payment_request ADD COLUMN screenshot VARCHAR(200)"))
            conn.commit()
            print("✅ Screenshot column added successfully!")
    except Exception:
        pass

# ================= ROUTES =================

# Serve images
@app.route('/images/<filename>')
def template_images(filename):
    return send_from_directory(os.path.join(app.root_path, 'templates'), filename)

# Home / Dashboard
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for('login'))
    user = User.query.get(session["user_id"])
    if user.last_reset != date.today():
        user.daily_ads = 0
        user.last_reset = date.today()
        db.session.commit()
    top_earners = User.query.order_by(User.balance.desc()).limit(5).all()
    online_now = random.randint(1100, 1900)
    return render_template("index.html", user=user, leaderboard=top_earners, earners=top_earners, online=online_now)

# Registration
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = generate_password_hash(request.form.get("password"))
        ref_code = request.args.get("ref") or request.form.get("ref_code")
        if User.query.filter_by(email=email).first():
            flash("Email already exists!", "error")
            return redirect(url_for("register"))
        user_uid = str(uuid.uuid4())[:8].upper()
        new_user = User(username=username, email=email, password=password,
                        referral_code=user_uid, referred_by=ref_code)
        db.session.add(new_user)
        db.session.commit()
        flash(f"Account Created! Your UID is {user_uid}", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# Login
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            return redirect(url_for("index"))
        flash("Invalid email or password!", "error")
    return render_template("login.html")

# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

# Buy Plan
@app.route("/buy_plan", methods=["POST"])
def buy_plan():
    if "user_id" not in session: return redirect(url_for("login"))
    user_id = session["user_id"]
    plan_name = request.form.get("plan_name")
    amount = request.form.get("amount")
    tid = request.form.get("tid")
    file = request.files.get("screenshot")
    if not tid or not file:
        flash("TID and Screenshot required!", "error")
        return redirect(url_for("index"))
    filename = secure_filename(f"TID_{tid}_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{file.filename}")
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    new_request = PaymentRequest(user_id=user_id, plan_name=plan_name, amount=float(amount),
                                 tid=tid, screenshot=filename)
    db.session.add(new_request)
    db.session.commit()
    flash(f"{plan_name} request submitted! Admin will verify.", "success")
    return redirect(url_for("index"))

# Withdraw
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
        flash("Enter valid amount!", "error")
        return redirect(url_for('withdraw_page'))
    if amount < 2000:
        flash("Minimum withdrawal Rs. 2000!", "error")
        return redirect(url_for('withdraw_page'))
    if amount > user.balance:
        flash("Insufficient balance!", "error")
        return redirect(url_for('withdraw_page'))
    new_request = Transaction(user_id=user.id, type=f"Withdraw ({method})",
                              amount=amount, details=account_no, status="Pending")
    user.balance -= amount
    db.session.add(new_request)
    db.session.commit()
    flash(f"Rs. {amount} withdrawal request submitted!", "success")
    return redirect(url_for('index'))

# Watch Ads
@app.route("/watch-ads")
def watch_ads_page():
    if "user_id" not in session: return redirect(url_for('login'))
    user = User.query.get(session["user_id"])
    if user.last_reset != date.today():
        user.daily_ads = 0
        user.last_reset = date.today()
        db.session.commit()
    return render_template("watch_ads.html", user=user)

@app.route("/api/complete_ad", methods=["POST"])
def complete_ad():
    if "user_id" not in session:
        return jsonify({"status":"error","message":"Login required"}),401
    user = User.query.get(session["user_id"])
    plan_rewards = {"Free":(50,5),"Gold":(70,10),"Diamond":(70,15)}
    limit,reward = plan_rewards.get(user.plan, (50,5))
    if user.daily_ads >= limit:
        return jsonify({"status":"error","message":f"Daily limit reached ({limit})"})
    user.balance += reward
    user.daily_ads += 1
    db.session.commit()
    return jsonify({"status":"success","message":f"Rs. {reward} added! ({user.daily_ads}/{limit} ads)",
                    "new_balance":round(user.balance,2)})

# Add Reward (force redirect)
@app.route("/add_reward")
def add_reward():
    if "user_id" not in session: return redirect(url_for('login'))
    user = User.query.get(session["user_id"])
    plan_rewards = {"Free":(50,5),"Gold":(70,10),"Diamond":(70,15)}
    limit,reward = plan_rewards.get(user.plan,(50,5))
    if user.daily_ads < limit:
        user.balance += reward
        user.daily_ads += 1
        db.session.commit()
        flash(f"Rs. {reward} added!", "success")
    else:
        flash(f"Daily limit ({limit}) reached!", "error")
    return redirect(url_for('watch_ads_page'))

# Claim daily bonus
@app.route("/claim_daily")
def claim_daily():
    if "user_id" not in session: return redirect(url_for('login'))
    user = User.query.get(session["user_id"])
    today = date.today()
    if user.last_bonus_date == today:
        flash("Daily bonus already claimed!", "error")
        return redirect(url_for('index'))
    bonus_amount = round(random.uniform(1.0,5.0),2)
    user.balance += bonus_amount
    user.last_bonus_date = today
    db.session.commit()
    flash(f"Rs. {bonus_amount} Daily Bonus added!", "success")
    return redirect(url_for('index'))

# ================= ADMIN PANEL =================
@app.route("/admin/dashboard")
def admin_dashboard():
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    if admin and (admin.email=='paisapropakistan@gmail.com' or admin.is_admin):
        upgrades = PaymentRequest.query.filter_by(status='Pending').all()
        withdraws = Transaction.query.filter_by(status='Pending').all()
        return render_template("admin_panel.html", upgrades=upgrades, withdraws=withdraws)
    return "Unauthorized",403

@app.route("/admin/approve_plan/<int:id>")
def approve_plan(id):
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    if not (admin.email=='paisapropakistan@gmail.com' or admin.is_admin): return "Unauthorized",403
    req = PaymentRequest.query.get(id)
    if req:
        user = User.query.get(req.user_id)
        if user.referred_by and user.plan=="Free":
            inviter = User.query.filter_by(referral_code=user.referred_by).first()
            if inviter:
                inviter.balance += 100.0
                inviter.referral_balance += 100.0
        user.plan = req.plan_name
        user.daily_ads = 0
        user.last_reset = date.today()
        req.status = "Approved"
        db.session.commit()
        flash(f"{user.username} approved for {req.plan_name}", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/reject_plan/<int:id>")
def reject_plan(id):
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    if not (admin.email=='paisapropakistan@gmail.com' or admin.is_admin): return "Unauthorized",403
    req = PaymentRequest.query.get(id)
    if req:
        req.status = "Rejected"
        db.session.commit()
        flash("Plan request rejected.", "danger")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/approve_withdraw/<int:id>")
def approve_withdraw(id):
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    if not (admin.email=='paisapropakistan@gmail.com' or admin.is_admin): return "Unauthorized",403
    trans = Transaction.query.get(id)
    if trans:
        trans.status = "Paid"
        db.session.commit()
        flash("Withdrawal marked as PAID!", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/reject_withdraw/<int:id>")
def reject_withdraw(id):
    if "user_id" not in session: return redirect(url_for('login'))
    admin = User.query.get(session["user_id"])
    if not (admin.email=='paisapropakistan@gmail.com' or admin.is_admin): return "Unauthorized",403
    trans = Transaction.query.get(id)
    if trans:
        user = User.query.get(trans.user_id)
        user.balance += trans.amount
        trans.status = "Rejected"
        db.session.commit()
        flash("Withdrawal rejected and refunded!", "danger")
    return redirect(url_for('admin_dashboard'))

# ================= RUN APP =================
if __name__=="__main__":
    app.run(debug=True, port=5000)