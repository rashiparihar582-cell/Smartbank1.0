# SmartBank

SmartBank is a Flask-based banking simulation web application. It provides user account management, money transfers, savings goals, spending insights, monthly reports, scam awareness, an AI-based Pocket Mentor, and admin management tools.

## Features

- User registration and login
- Account dashboard
- Transaction history
- Money transfer with transaction PIN
- Savings goals and progress tracking
- Spending insights and monthly report
- Activity timeline
- Profile management
- Password and transaction PIN change
- Admin dashboard
- Admin user search, block, unblock, and delete
- Audit logs
- Admin analytics
- Scam awareness page
- Pocket Mentor banking guide and scam-message checker
- Account deactivation request and admin approval

## Technologies Used

- Python
- Flask
- SQLite
- HTML
- CSS
- Jinja2
- Werkzeug security utilities

## Project Structure

```text
smartbank/
├── app.py
├── database.py
├── smartbank.db
├── requirements.txt
├── README.md
├── .gitignore
└── templates/
    ├── register.html
    ├── login.html
    ├── dashboard.html
    ├── history.html
    ├── transfer.html
    ├── goals.html
    ├── insights.html
    ├── report.html
    ├── activity.html
    ├── profile.html
    ├── edit_profile.html
    ├── change_password.html
    ├── change_pin.html
    ├── admin.html
    ├── admin_users.html
    ├── audit_logs.html
    ├── admin_analytics.html
    ├── scam_awareness.html
    └── pocket_mentor.html
```

## How to Run

1. Install Python 3.
2. Open the project folder in VS Code.
3. Install Flask:

```bash
pip install Flask
```

4. Run the application:

```bash
python app.py
```

5. Open this URL in your browser:

```text
http://127.0.0.1:5000
```

## Default Admin Account

The first registered user becomes the admin because the application checks:

```python
session.get("user_id") == 1
```

For a real application, admin access should use a proper role-based permission system.

## Security Notes

- Passwords and transaction PINs are stored as hashed values.
- Users cannot access another user’s data without logging in.
- Admin actions are protected by an admin check.
- Blocked and deactivated users cannot log in.
- Audit logs record important security-related events.
- Pocket Mentor provides awareness only; it does not replace official bank support.

## Important Disclaimer

SmartBank is an educational project. It is not connected to a real bank and should not be used for real financial transactions.