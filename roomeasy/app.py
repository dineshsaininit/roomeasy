import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = "super_secret_key_change_this"

# Initialize Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY in .env file")

supabase: Client = create_client(url, key)

# --- Authentication Decorator ---
def login_required(f):
    def wrap(*args, **kwargs):
        if 'user' not in session:
            flash("You need to login first!", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# --- Routes ---

@app.route('/')
def index():
    # Fetch all available rooms from Supabase
    try:
        response = supabase.table('rooms').select("*").eq('status', 'available').execute()
        rooms = response.data
    except Exception as e:
        rooms = []
        print(f"Error fetching rooms: {e}")
        
    return render_template('index.html', rooms=rooms)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        action = request.form.get('action') # 'login' or 'signup'

        try:
            if action == 'signup':
                # Supabase Auth Sign Up
                res = supabase.auth.sign_up({"email": email, "password": password})
                flash("Signup successful! Please check your email or log in.", "success")
            else:
                # Supabase Auth Sign In
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                session['user'] = res.user.id
                session['email'] = res.user.email
                flash("Logged in successfully!", "success")
                return redirect(url_for('index'))
        except Exception as e:
            flash(str(e), "error")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    supabase.auth.sign_out()
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        title = request.form.get('title')
        address = request.form.get('address')
        price = float(request.form.get('price'))
        desc = request.form.get('description')
        image_url = request.form.get('image_url')

        data = {
            "owner_id": session['user'],
            "title": title,
            "address": address,
            "price_per_month": price,
            "description": desc,
            "image_url": image_url,
            "status": "available"
        }

        try:
            supabase.table('rooms').insert(data).execute()
            flash("Room uploaded successfully!", "success")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Error uploading: {e}", "error")

    return render_template('upload.html')

@app.route('/room/<int:room_id>')
def room_details(room_id):
    try:
        response = supabase.table('rooms').select("*").eq('id', room_id).single().execute()
        room = response.data
        
        # Calculate costs logic
        full_rent = float(room['price_per_month'])
        lock_amount = round(full_rent * 0.05, 2) # 5% of rent
        visit_fee = 50 
        
        return render_template('room_details.html', room=room, lock_amount=lock_amount, visit_fee=visit_fee)
    except Exception as e:
        flash("Room not found or error loading details.", "error")
        return redirect(url_for('index'))

@app.route('/book/<int:room_id>', methods=['POST'])
@login_required
def book_room(room_id):
    booking_type = request.form.get('booking_type') # 'lock', 'full', 'visit'
    amount = request.form.get('amount')
    
    # Save booking to Supabase
    booking_data = {
        "user_id": session['user'],
        "room_id": room_id,
        "booking_type": booking_type,
        "amount_paid": float(amount) if amount else 0
    }
    
    try:
        supabase.table('bookings').insert(booking_data).execute()
        
        # If full rent or lock, mark room as unavailable
        if booking_type in ['full', 'lock']:
             supabase.table('rooms').update({"status": "booked"}).eq("id", room_id).execute()
             
        flash(f"Payment Successful! You selected: {booking_type}", "success")
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"Booking failed: {e}", "error")
        return redirect(url_for('room_details', room_id=room_id))

if __name__ == '__main__':
    app.run(debug=True)