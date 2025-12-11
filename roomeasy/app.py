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
    try:
        response = supabase.table('rooms').select("*").eq('status', 'available').execute()
        rooms = response.data
    except Exception as e:
        rooms = []
        print(f"Error fetching rooms: {e}")
        
    return render_template('index.html', rooms=rooms)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        profile_image = request.form.get('profile_image_url')

        try:
            # 1. Check if email already exists
            existing_user = supabase.table('user_profiles').select("*").eq('email', email).execute()
            
            if existing_user.data:
                flash("Email already registered. Please login.", "error")
                return redirect(url_for('login'))

            # 2. Manual Insert into user_profiles
            new_user_data = {
                "full_name": full_name,
                "email": email,
                "password": password, 
                "role": "user",
                "profile_image_url": profile_image if profile_image else ""
            }
            
            supabase.table('user_profiles').insert(new_user_data).execute()
            
            flash("Signup successful! You can now login.", "success")
            return redirect(url_for('login'))
                
        except Exception as e:
            flash(f"Signup Error: {str(e)}", "error")
            
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            # 1. Manual Query: Match Email AND Password
            response = supabase.table('user_profiles').select("*").eq('email', email).eq('password', password).execute()
            
            # 2. Check if a user was found
            if response.data and len(response.data) > 0:
                user = response.data[0]
                
                # 3. Set Session
                session['user'] = user['id']
                session['name'] = user['full_name']
                session['role'] = user['role']
                # Store profile image in session for header access
                session['profile_image'] = user.get('profile_image_url')
                
                flash(f"Welcome back, {user['full_name']}!", "success")
                return redirect(url_for('index'))
            else:
                flash("Invalid email or password", "error")

        except Exception as e:
            flash(f"Login Error: {str(e)}", "error")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    user_id = session['user']
    try:
        # Fetch user details
        user_response = supabase.table('user_profiles').select("*").eq('id', user_id).single().execute()
        user = user_response.data
        
        # Fetch rooms posted by this user
        rooms_response = supabase.table('rooms').select("*").eq('owner_id', user_id).execute()
        user_rooms = rooms_response.data
        
        return render_template('profile.html', user=user, rooms=user_rooms)
    except Exception as e:
        flash(f"Error fetching profile: {e}", "error")
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
        
        full_rent = float(room['price_per_month'])
        lock_amount = round(full_rent * 0.05, 2)
        visit_fee = 50 
        
        return render_template('room_details.html', room=room, lock_amount=lock_amount, visit_fee=visit_fee)
    except Exception as e:
        flash("Room not found.", "error")
        return redirect(url_for('index'))

@app.route('/book/<int:room_id>', methods=['POST'])
@login_required
def book_room(room_id):
    booking_type = request.form.get('booking_type')
    amount = request.form.get('amount')
    
    booking_data = {
        "user_id": session['user'],
        "room_id": room_id,
        "booking_type": booking_type,
        "amount_paid": float(amount) if amount else 0
    }
    
    try:
        supabase.table('bookings').insert(booking_data).execute()
        
        if booking_type in ['full', 'lock']:
             supabase.table('rooms').update({"status": "booked"}).eq("id", room_id).execute()
             
        flash(f"Booking Successful! Type: {booking_type}", "success")
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"Booking failed: {e}", "error")
        return redirect(url_for('room_details', room_id=room_id))

if __name__ == '__main__':
    app.run(debug=True)