from flask import Flask, render_template, request, redirect, url_for, flash, session
from database import init_db
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime


app = Flask(__name__)
app.secret_key = "smartbank-secret-key-change-this-later"


init_db()
def log_audit(user_id, action, details=""):
    connection = sqlite3.connect("smartbank.db")

    connection.execute(
        """INSERT INTO audit_logs
        (user_id, action, details)
        VALUES (?, ?, ?)""",
        (user_id, action, details)
    )

    connection.commit()
    connection.close()


@app.route("/")
def home():
    return render_template("register.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()
        password = request.form["password"]
        pin = request.form["pin"]

        if len(password) < 8:
            flash("Password must be at least 8 characters.")
            return redirect(url_for("register"))

        if len(pin) != 4 or not pin.isdigit():
            flash("PIN must be exactly 4 digits.")
            return redirect(url_for("register"))

        if len(phone) != 10 or not phone.isdigit():
            flash("Phone number must be exactly 10 digits.")
            return redirect(url_for("register"))

        connection = sqlite3.connect("smartbank.db")
        connection.row_factory = sqlite3.Row

        existing_user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            connection.close()
            flash("This email is already registered.")
            return redirect(url_for("register"))

        total_users = connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        account_number = "SB" + str(100001 + total_users)

        connection.execute(
            """INSERT INTO users
            (full_name, account_number, email, phone, password_hash, pin_hash, balance)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                full_name,
                account_number,
                email,
                phone,
                generate_password_hash(password),
                generate_password_hash(pin),
                5000.0
            )
        )

        connection.commit()
        connection.close()

        flash(f"Account created successfully. Your account number is {account_number}")
        return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        account_number = request.form["account_number"].strip()
        password = request.form["password"]

        connection = sqlite3.connect("smartbank.db")
        connection.row_factory = sqlite3.Row

        user = connection.execute(
            "SELECT * FROM users WHERE account_number = ?",
            (account_number,)
        ).fetchone()

        connection.close()

        if user and check_password_hash(user["password_hash"], password):
            if user["status"] in ["blocked", "deactivated"]:
                flash("Your account has been blocked. Contact support.")
                return redirect(url_for("login"))
            log_audit(user["id"], "login_success", "User logged in")
            session["user_id"] = user["id"]
            flash("Login successful.")
            return redirect(url_for("dashboard"))
        if user:
            log_audit(user["id"], "login_failed", "Incorrect password")
        else:
            log_audit(None, "login_failed", f"Unknown account: {account_number}")
        flash("Invalid account number or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    user = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    transactions = connection.execute(
        """SELECT * FROM transactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 5""",
        (session["user_id"],)
    ).fetchall()

    goals = connection.execute(
        "SELECT * FROM goals WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()

    connection.close()

    return render_template(
        "dashboard.html",
        user=user,
        transactions=transactions,
        goals=goals
    )


@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    transactions = connection.execute(
        """SELECT * FROM transactions
        WHERE user_id = ?
        ORDER BY created_at DESC""",
        (session["user_id"],)
    ).fetchall()

    connection.close()

    return render_template("history.html", transactions=transactions)


@app.route("/transfer", methods=["GET", "POST"])
def transfer():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    sender = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    if request.method == "POST":
        receiver_account = request.form["receiver_account"].strip()
        amount = float(request.form["amount"])
        category = request.form["category"]
        description = request.form["description"].strip()
        pin = request.form["pin"]

        if amount <= 0:
            connection.close()
            flash("Enter a valid amount.")
            return redirect(url_for("transfer"))

        if amount > sender["balance"]:
            connection.close()
            flash("Insufficient balance.")
            return redirect(url_for("transfer"))

        receiver = connection.execute(
            "SELECT * FROM users WHERE account_number = ?",
            (receiver_account,)
        ).fetchone()

        if not receiver:
            connection.close()
            flash("Receiver account not found.")
            return redirect(url_for("transfer"))

        if receiver["id"] == sender["id"]:
            connection.close()
            flash("You cannot transfer money to yourself.")
            return redirect(url_for("transfer"))

        if not check_password_hash(sender["pin_hash"], pin):
            connection.close()
            flash("Incorrect transaction PIN.")
            return redirect(url_for("transfer"))

        new_sender_balance = sender["balance"] - amount
        new_receiver_balance = receiver["balance"] + amount

        connection.execute(
            "UPDATE users SET balance = ? WHERE id = ?",
            (new_sender_balance, sender["id"])
        )

        connection.execute(
            "UPDATE users SET balance = ? WHERE id = ?",
            (new_receiver_balance, receiver["id"])
        )

        connection.execute(
            """INSERT INTO transactions
            (user_id, type, amount, category, description, balance_after)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                sender["id"],
                "debit",
                amount,
                category,
                f"Transfer to {receiver_account}",
                new_sender_balance
            )
        )

        connection.execute(
            """INSERT INTO transactions
            (user_id, type, amount, category, description, balance_after)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                receiver["id"],
                "credit",
                amount,
                category,
                f"Transfer from {sender['account_number']}",
                new_receiver_balance
            )
        )

        connection.execute(
            """INSERT INTO transfers
            (sender_id, receiver_id, amount, status)
            VALUES (?, ?, ?, ?)""",
            (sender["id"], receiver["id"], amount, "success")
        )

        connection.commit()
        connection.close()
        log_audit(
            sender["id"],
            "transfer_success",
            f"Transferred Rs. {amount} to {receiver_account}"
        )
        flash("Transfer successful.")
        return redirect(url_for("dashboard"))

    connection.close()
    return render_template("transfer.html", user=sender)


@app.route("/goals", methods=["GET", "POST"])
def goals():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    if request.method == "POST":
        goal_name = request.form["goal_name"].strip()
        target_amount = float(request.form["target_amount"])
        saved_amount = float(request.form["saved_amount"])
        deadline = request.form["deadline"]

        if target_amount <= 0:
            connection.close()
            flash("Target amount must be greater than zero.")
            return redirect(url_for("goals"))

        connection.execute(
            """INSERT INTO goals
            (user_id, goal_name, target_amount, saved_amount, deadline)
            VALUES (?, ?, ?, ?, ?)""",
            (session["user_id"], goal_name, target_amount, saved_amount, deadline)
        )

        connection.commit()
        connection.close()

        flash("Savings goal created successfully.")
        return redirect(url_for("goals"))

    goals = connection.execute(
        "SELECT * FROM goals WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()

    goal_progress = {}

    for goal in goals:
        progress = (goal["saved_amount"] / goal["target_amount"]) * 100

        if progress > 100:
            progress = 100

        goal_progress[goal["id"]] = round(progress, 2)

    connection.close()

    return render_template(
        "goals.html",
        goals=goals,
        goal_progress=goal_progress
    )


@app.route("/add-goal-money", methods=["POST"])
def add_goal_money():
    if "user_id" not in session:
        return redirect(url_for("login"))

    goal_id = int(request.form["goal_id"])
    amount = float(request.form["amount"])

    if amount <= 0:
        flash("Enter a valid amount.")
        return redirect(url_for("goals"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    goal = connection.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?",
        (goal_id, session["user_id"])
    ).fetchone()

    if not goal:
        connection.close()
        flash("Goal not found.")
        return redirect(url_for("goals"))

    new_saved_amount = goal["saved_amount"] + amount

    connection.execute(
        "UPDATE goals SET saved_amount = ? WHERE id = ?",
        (new_saved_amount, goal_id)
    )

    connection.commit()
    connection.close()

    flash("Money added to your savings goal.")
    return redirect(url_for("goals"))


@app.route("/insights")
def insights():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    income = connection.execute(
        """SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ? AND type = 'credit'""",
        (session["user_id"],)
    ).fetchone()[0]

    expense = connection.execute(
        """SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ? AND type = 'debit'""",
        (session["user_id"],)
    ).fetchone()[0]

    category_spending = connection.execute(
        """SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE user_id = ? AND type = 'debit'
        GROUP BY category
        ORDER BY total DESC""",
        (session["user_id"],)
    ).fetchall()

    connection.close()

    total_income = round(income, 2)
    total_expense = round(expense, 2)
    net_change = round(total_income - total_expense, 2)

    category_data = []

    if total_expense > 0:
        for item in category_spending:
            percentage = (item["total"] / total_expense) * 100

            category_data.append({
                "category": item["category"],
                "total": round(item["total"], 2),
                "percentage": round(percentage, 2)
            })

    return render_template(
        "insights.html",
        total_income=total_income,
        total_expense=total_expense,
        net_change=net_change,
        category_spending=category_data
    )


@app.route("/report")
def report():
    if "user_id" not in session:
        return redirect(url_for("login"))

    now = datetime.now()

    month_name = now.strftime("%B %Y")

    start_date = now.strftime("%Y-%m-01")

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    transactions = connection.execute(
        """SELECT * FROM transactions
        WHERE user_id = ? AND date(created_at) >= ?
        ORDER BY created_at DESC""",
        (session["user_id"], start_date)
    ).fetchall()

    total_income = 0
    total_expense = 0

    for transaction in transactions:
        if transaction["type"] == "credit":
            total_income += transaction["amount"]
        elif transaction["type"] == "debit":
            total_expense += transaction["amount"]

    connection.close()

    total_income = round(total_income, 2)
    total_expense = round(total_expense, 2)
    net_savings = round(total_income - total_expense, 2)

    return render_template(
        "report.html",
        month_name=month_name,
        transactions=transactions,
        total_income=total_income,
        total_expense=total_expense,
        net_savings=net_savings
    )


@app.route("/activity")
def activity():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    transactions = connection.execute(
        """SELECT * FROM transactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 10""",
        (session["user_id"],)
    ).fetchall()

    transfers = connection.execute(
        """SELECT * FROM transfers
        WHERE sender_id = ?
        ORDER BY created_at DESC
        LIMIT 5""",
        (session["user_id"],)
    ).fetchall()

    connection.close()

    return render_template(
        "activity.html",
        transactions=transactions,
        transfers=transfers
    )


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    user = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    connection.close()

    return render_template("profile.html", user=user)


@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    user = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()

        if len(phone) != 10 or not phone.isdigit():
            connection.close()
            flash("Phone number must be exactly 10 digits.")
            return redirect(url_for("edit_profile"))

        existing_email = connection.execute(
            "SELECT * FROM users WHERE email = ? AND id != ?",
            (email, session["user_id"])
        ).fetchone()

        if existing_email:
            connection.close()
            flash("This email is already used by another account.")
            return redirect(url_for("edit_profile"))

        connection.execute(
            """UPDATE users
            SET full_name = ?, email = ?, phone = ?
            WHERE id = ?""",
            (full_name, email, phone, session["user_id"])
        )

        connection.commit()
        connection.close()

        flash("Profile updated successfully.")
        return redirect(url_for("profile"))

    connection.close()

    return render_template("edit_profile.html", user=user)


@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    user = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if not check_password_hash(user["password_hash"], current_password):
            connection.close()
            flash("Current password is incorrect.")
            return redirect(url_for("change_password"))

        if len(new_password) < 8:
            connection.close()
            flash("New password must be at least 8 characters.")
            return redirect(url_for("change_password"))

        if new_password != confirm_password:
            connection.close()
            flash("New passwords do not match.")
            return redirect(url_for("change_password"))

        new_password_hash = generate_password_hash(new_password)

        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, session["user_id"])
        )

        connection.commit()
        connection.close()

        flash("Password changed successfully.")
        return redirect(url_for("profile"))

    connection.close()

    return render_template("change_password.html")


@app.route("/admin")
def admin():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_id") != 1:
        flash("Admin access required.")
        return redirect(url_for("dashboard"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    total_users = connection.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    total_transactions = connection.execute(
        "SELECT COUNT(*) FROM transactions"
    ).fetchone()[0]

    total_transfers = connection.execute(
        "SELECT COUNT(*) FROM transfers"
    ).fetchone()[0]

    users = connection.execute(
        """SELECT full_name, account_number, email, balance
        FROM users
        ORDER BY id DESC
        LIMIT 10"""
    ).fetchall()

    connection.close()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_transactions=total_transactions,
        total_transfers=total_transfers,
        users=users
    )

@app.route("/admin-users")
def admin_users():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_id") != 1:
        flash("Admin access required.")
        return redirect(url_for("dashboard"))

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "")

    query = """
    SELECT * FROM users
    WHERE 1 = 1
    """

    params = []

    if search:
        query += """
        AND (
            full_name LIKE ? OR
            account_number LIKE ? OR
            email LIKE ?
        )
        """

        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    if status in ["active", "blocked"]:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY id ASC"

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    users = connection.execute(query, params).fetchall()

    connection.close()

    return render_template(
        "admin_users.html",
        users=users,
        search=search,
        status=status
    )


@app.route("/block-user", methods=["POST"])
def block_user():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_id") != 1:
        flash("Admin access required.")
        return redirect(url_for("dashboard"))

    user_id = int(request.form["user_id"])

    connection = sqlite3.connect("smartbank.db")

    connection.execute(
        "UPDATE users SET status = 'blocked' WHERE id = ?",
        (user_id,)
    )

    connection.commit()
    connection.close()
    log_audit(session["user_id"], "user_blocked", f"User ID {user_id} blocked")
    flash("User blocked successfully.")
    return redirect(url_for("admin_users"))


@app.route("/unblock-user", methods=["POST"])
def unblock_user():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_id") != 1:
        flash("Admin access required.")
        return redirect(url_for("dashboard"))

    user_id = int(request.form["user_id"])

    connection = sqlite3.connect("smartbank.db")

    connection.execute(
        "UPDATE users SET status = 'active' WHERE id = ?",
        (user_id,)
    )

    connection.commit()
    connection.close()
    log_audit(session["user_id"], "user_unblocked", f"User ID {user_id} unblocked")
    flash("User unblocked successfully.")
    return redirect(url_for("admin_users"))

@app.route("/change-pin", methods=["GET", "POST"])
def change_pin():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    user = connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    if request.method == "POST":
        current_pin = request.form["current_pin"]
        new_pin = request.form["new_pin"]
        confirm_pin = request.form["confirm_pin"]

        if not check_password_hash(user["pin_hash"], current_pin):
            connection.close()
            flash("Current PIN is incorrect.")
            return redirect(url_for("change_pin"))

        if len(new_pin) != 4 or not new_pin.isdigit():
            connection.close()
            flash("New PIN must be exactly 4 digits.")
            return redirect(url_for("change_pin"))

        if new_pin != confirm_pin:
            connection.close()
            flash("New PINs do not match.")
            return redirect(url_for("change_pin"))

        if check_password_hash(user["pin_hash"], new_pin):
            connection.close()
            flash("New PIN cannot be the same as the current PIN.")
            return redirect(url_for("change_pin"))

        new_pin_hash = generate_password_hash(new_pin)

        connection.execute(
            "UPDATE users SET pin_hash = ? WHERE id = ?",
            (new_pin_hash, session["user_id"])
        )

        connection.commit()
        connection.close()

        flash("Transaction PIN changed successfully.")
        return redirect(url_for("profile"))

    connection.close()

    return render_template("change_pin.html")
@app.route("/scam-awareness")
def scam_awareness():
    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template("scam_awareness.html")
@app.route("/audit-logs")
def audit_logs():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_id") != 1:
        flash("Admin access required.")
        return redirect(url_for("dashboard"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    logs = connection.execute(
        "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 100"
    ).fetchall()

    connection.close()

    return render_template("audit_logs.html", logs=logs)
@app.route("/admin-analytics")
def admin_analytics():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_id") != 1:
        flash("Admin access required.")
        return redirect(url_for("dashboard"))

    connection = sqlite3.connect("smartbank.db")
    connection.row_factory = sqlite3.Row

    total_users = connection.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    active_users = connection.execute(
        "SELECT COUNT(*) FROM users WHERE status = 'active'"
    ).fetchone()[0]

    blocked_users = connection.execute(
        "SELECT COUNT(*) FROM users WHERE status = 'blocked'"
    ).fetchone()[0]

    total_transfers = connection.execute(
        "SELECT COUNT(*) FROM transfers"
    ).fetchone()[0]

    total_transaction_amount = connection.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions"
    ).fetchone()[0]

    top_categories = connection.execute(
        """SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE type = 'debit'
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5"""
    ).fetchall()

    connection.close()

    category_data = []

    if top_categories:
        highest_total = top_categories[0]["total"]

        if highest_total > 0:
            for item in top_categories:
                percentage = (item["total"] / highest_total) * 100

                category_data.append({
                    "category": item["category"],
                    "total": round(item["total"], 2),
                    "percentage": round(percentage, 2)
                })

    return render_template(
        "admin_analytics.html",
        total_users=total_users,
        active_users=active_users,
        blocked_users=blocked_users,
        total_transfers=total_transfers,
        total_transaction_amount=round(total_transaction_amount, 2),
        top_categories=category_data
    )
@app.route("/delete-user", methods=["POST"])
def delete_user():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_id") != 1:
        flash("Admin access required.")
        return redirect(url_for("dashboard"))

    user_id = int(request.form["user_id"])

    if user_id == 1:
        flash("You cannot delete the admin account.")
        return redirect(url_for("admin_users"))

    connection = sqlite3.connect("smartbank.db")

    connection.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
    connection.execute("DELETE FROM transfers WHERE sender_id = ?", (user_id,))
    connection.execute("DELETE FROM transfers WHERE receiver_id = ?", (user_id,))
    connection.execute("DELETE FROM savings_goals WHERE user_id = ?", (user_id,))
    connection.execute("DELETE FROM users WHERE id = ?", (user_id,))

    connection.commit()
    connection.close()

    log_audit(session["user_id"], "user_deleted", f"User ID {user_id} deleted")

    flash("User deleted successfully.")
    return redirect(url_for("admin_users"))
@app.route("/pocket-mentor", methods=["GET", "POST"])
def pocket_mentor():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if "mentor_chat" not in session:
        session["mentor_chat"] = [
            {
                "type": "mentor-message",
                "text": "Hello! I am your Pocket Mentor. Ask me about banking terms, savings, credit score, UPI, OTP, or paste a suspicious message for a safety check."
            }
        ]

    if request.method == "POST":
        user_message = request.form["user_message"].strip()
        message_lower = user_message.lower()

        session["mentor_chat"].append({
            "type": "user-message",
            "text": user_message
        })

        if "otp" in message_lower and (
            "share" in message_lower or
            "enter" in message_lower or
            "click" in message_lower or
            "verify" in message_lower or
            "blocked" in message_lower
        ):
            reply = (
                "This looks like a possible phishing or OTP scam. "
                "Never share your OTP, PIN, password, CVV, or UPI PIN with anyone. "
                "Do not click the link. Open the official bank app or website yourself."
            )

        elif "otp" in message_lower:
            reply = (
                "OTP means One-Time Password. Never share it with anyone."
            )

        elif "upi" in message_lower:
            reply = (
                "UPI means Unified Payments Interface. You do not need to enter a UPI PIN to receive money."
            )

        else:
            reply = (
                "Ask about banking terms such as OTP, UPI, EMI, credit score, savings, "
                "or paste a suspicious message for a scam check."
            )

        session["mentor_chat"].append({
            "type": "mentor-message",
            "text": reply
        })

        session.modified = True

        return redirect(url_for("pocket_mentor"))

    return render_template(
        "pocket_mentor.html",
        chat_history=session["mentor_chat"]
    )
@app.route("/request-deactivation", methods=["POST"])
def request_deactivation():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = sqlite3.connect("smartbank.db")

    connection.execute(
        """UPDATE users
        SET status = 'deactivation_requested'
        WHERE id = ? AND status = 'active'""",
        (session["user_id"],)
    )

    connection.commit()
    connection.close()

    log_audit(
        session["user_id"],
        "deactivation_requested",
        "User requested account deactivation"
    )

    flash("Your account deactivation request has been submitted. Contact support for assistance.")
    return redirect(url_for("profile"))
@app.route("/approve-deactivation", methods=["POST"])
def approve_deactivation():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("user_id") != 1:
        flash("Admin access required.")
        return redirect(url_for("dashboard"))

    user_id = int(request.form["user_id"])

    connection = sqlite3.connect("smartbank.db")

    connection.execute(
        """UPDATE users
        SET status = 'deactivated'
        WHERE id = ? AND status = 'deactivation_requested'""",
        (user_id,)
    )

    connection.commit()
    connection.close()

    log_audit(
        session["user_id"],
        "account_deactivated",
        f"User ID {user_id} deactivated"
    )

    flash("User account deactivated successfully.")
    return redirect(url_for("admin_users"))
if __name__ == "__main__":
    app.run(debug=True)
import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))