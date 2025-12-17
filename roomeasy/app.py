import os
import random
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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
    search_query = request.args.get('q', '').strip()
    
    # Initialize lists
    featured_rooms = []
    recently_viewed_rooms = []
    recommended_rooms = []
    all_rooms = []
    
    try:
        # 1. FETCH ALL AVAILABLE ROOMS (Base Dataset)
        base_query = supabase.table('rooms').select("*").eq('status', 'available')
        
        if search_query:
            # Store location in session for future recommendations
            session['user_location'] = search_query

            # SEARCH MODE: Filter by address OR title
            filter_condition = f"address.ilike.%{search_query}%,title.ilike.%{search_query}%"
            response = base_query.or_(filter_condition).execute()
            all_rooms = response.data
            
            # If no results, show recommendations instead of empty page
            if not all_rooms:
                response = supabase.table('rooms').select("*").eq('status', 'available').limit(12).execute()
                recommended_rooms = response.data
        else:
            # HOME PAGE MODE
            response = base_query.execute()
            all_rooms = response.data
            
            # A. HERO SLIDESHOW (Featured)
            # Pick 5 random rooms for the main slider
            if len(all_rooms) > 0:
                featured_rooms = random.sample(all_rooms, min(len(all_rooms), 5))
            
            # B. RECENTLY VIEWED (From Session)
            recent_ids = session.get('recently_viewed', [])
            if recent_ids:
                # Fetch rooms and preserve order
                recently_viewed_rooms = [r for r in all_rooms if r['id'] in recent_ids]
                # Sort to ensure they appear in the order they were viewed (most recent first)
                recently_viewed_rooms.sort(key=lambda r: recent_ids.index(r['id']))

            # C. RECOMMENDED / LOCATION BASED
            # Logic: If user has viewed rooms, recommend others in the SAME location.
            
            recent_location_keywords = []
            
            # 1. Extract location from most recent view
            if recently_viewed_rooms:
                last_room = recently_viewed_rooms[0] # Index 0 is most recent
                if last_room.get('address'):
                    # Assume typical format "Street, Area, City" -> take last part
                    parts = last_room['address'].split(',')
                    if parts:
                        recent_location_keywords.append(parts[-1].strip().lower())
                    # Also consider the part before (e.g., specific area)
                    if len(parts) > 1:
                        recent_location_keywords.append(parts[-2].strip().lower())

            # 2. Filter all_rooms based on these keywords
            if recent_location_keywords:
                viewed_ids = set(r['id'] for r in recently_viewed_rooms)
                
                # Find matches
                for room in all_rooms:
                    # Skip if already viewed
                    if room['id'] in viewed_ids:
                        continue
                        
                    # Check if room address matches recent location
                    address_lower = room.get('address', '').lower()
                    if any(kw in address_lower for kw in recent_location_keywords):
                        recommended_rooms.append(room)
                
                # If we found matches, great! If not enough, fill with others.
                if len(recommended_rooms) < 5:
                    # Find random rooms not already recommended or viewed
                    remaining = [r for r in all_rooms if r['id'] not in viewed_ids and r not in recommended_rooms]
                    if remaining:
                        recommended_rooms.extend(random.sample(remaining, min(len(remaining), 5 - len(recommended_rooms))))
            else:
                # No history? Try to use session location from previous searches
                user_loc = session.get('user_location')
                if user_loc:
                    # Filter by stored location
                    for room in all_rooms:
                        if user_loc.lower() in room.get('address', '').lower():
                            recommended_rooms.append(room)
                    
                    # If not enough matches, fill with random
                    if len(recommended_rooms) < 5:
                         remaining = [r for r in all_rooms if r not in recommended_rooms]
                         if remaining:
                            recommended_rooms.extend(random.sample(remaining, min(len(remaining), 5 - len(recommended_rooms))))
                else:
                    # Totally new user? Just show a diverse mix
                    if len(all_rooms) > 0:
                        recommended_rooms = random.sample(all_rooms, min(len(all_rooms), 8))

        # Check liked rooms for the heart icon
        liked_room_ids = []
        if 'user' in session:
            user_id = session['user']
            wishlist_res = supabase.table('wishlist').select('room_id').eq('user_id', user_id).execute()
            liked_room_ids = [item['room_id'] for item in wishlist_res.data]

    except Exception as e:
        print(f"Error fetching rooms: {e}")
        all_rooms = []

    return render_template('index.html', 
                         rooms=all_rooms,
                         featured_rooms=featured_rooms,
                         recently_viewed_rooms=recently_viewed_rooms,
                         recommended_rooms=recommended_rooms,
                         liked_room_ids=liked_room_ids, 
                         search_query=search_query)

@app.route('/wishlist')
@login_required
def wishlist():
    user_id = session['user']
    try:
        wishlist_res = supabase.table('wishlist').select('room_id').eq('user_id', user_id).execute()
        room_ids = [item['room_id'] for item in wishlist_res.data]
        
        if room_ids:
            rooms_res = supabase.table('rooms').select('*').in_('id', room_ids).execute()
            rooms = rooms_res.data
        else:
            rooms = []
            
        return render_template('wishlist.html', rooms=rooms)
    except Exception as e:
        print(f"Error fetching wishlist: {e}")
        flash("Could not load wishlist", "error")
        return redirect(url_for('index'))

@app.route('/toggle_wishlist/<int:room_id>', methods=['POST'])
def toggle_wishlist(room_id):
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Login required'}), 401
    
    user_id = session['user']
    try:
        existing = supabase.table('wishlist').select('*').eq('user_id', user_id).eq('room_id', room_id).execute()
        if existing.data:
            supabase.table('wishlist').delete().eq('user_id', user_id).eq('room_id', room_id).execute()
            return jsonify({'status': 'removed'})
        else:
            supabase.table('wishlist').insert({'user_id': user_id, 'room_id': room_id}).execute()
            return jsonify({'status': 'added'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        profile_image = request.form.get('profile_image_url')

        try:
            existing_user = supabase.table('user_profiles').select("*").eq('email', email).execute()
            if existing_user.data:
                flash("Email already registered. Please login.", "error")
                return redirect(url_for('login'))

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
            response = supabase.table('user_profiles').select("*").eq('email', email).eq('password', password).execute()
            if response.data and len(response.data) > 0:
                user = response.data[0]
                session['user'] = user['id']
                session['name'] = user['full_name']
                session['role'] = user['role']
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
        user_response = supabase.table('user_profiles').select("*").eq('id', user_id).single().execute()
        user = user_response.data
        
        # Order by created_at desc to show newest first
        rooms_response = supabase.table('rooms').select("*").eq('owner_id', user_id).order('created_at', desc=True).execute()
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

@app.route('/edit_room/<int:room_id>', methods=['GET', 'POST'])
@login_required
def edit_room(room_id):
    try:
        response = supabase.table('rooms').select("*").eq('id', room_id).single().execute()
        room = response.data
    except Exception as e:
        flash("Room not found.", "error")
        return redirect(url_for('profile'))

    if str(room['owner_id']) != str(session['user']):
        flash("You can only edit your own rooms.", "error")
        return redirect(url_for('profile'))

    if request.method == 'POST':
        try:
            update_data = {
                "title": request.form.get('title'),
                "address": request.form.get('address'),
                "price_per_month": float(request.form.get('price')),
                "description": request.form.get('description'),
                "image_url": request.form.get('image_url')
            }
            supabase.table('rooms').update(update_data).eq('id', room_id).execute()
            flash("Room updated successfully!", "success")
            return redirect(url_for('profile'))
        except Exception as e:
            flash(f"Error updating room: {e}", "error")

    return render_template('edit_room.html', room=room)

@app.route('/delete_room/<int:room_id>', methods=['POST'])
@login_required
def delete_room(room_id):
    try:
        response = supabase.table('rooms').select("*").eq('id', room_id).single().execute()
        room = response.data
        
        if str(room['owner_id']) != str(session['user']):
            flash("Unauthorized action.", "error")
            return redirect(url_for('profile'))

        supabase.table('bookings').delete().eq('room_id', room_id).execute()
        supabase.table('wishlist').delete().eq('room_id', room_id).execute()
        supabase.table('rooms').delete().eq('id', room_id).execute()
        
        flash("Room deleted successfully.", "info")
    except Exception as e:
        flash(f"Error deleting room: {e}", "error")
        
    return redirect(url_for('profile'))

@app.route('/room/<int:room_id>')
def room_details(room_id):
    try:
        response = supabase.table('rooms').select("*").eq('id', room_id).single().execute()
        room = response.data
        full_rent = float(room['price_per_month'])
        lock_amount = round(full_rent * 0.05, 2)
        visit_fee = 50
        
        viewed = session.get('recently_viewed', [])
        if room_id in viewed:
            viewed.remove(room_id)
        viewed.insert(0, room_id)
        viewed = viewed[:8]
        session['recently_viewed'] = viewed
        session.modified = True
        
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

# --- NEW API FOR AUTOCOMPLETE ---
@app.route('/api/locations')
def get_locations():
    """Returns a list of unique addresses/locations from the database for autocomplete."""
    try:
        response = supabase.table('rooms').select('address').execute()
        # Filter distinct addresses to prevent duplicates in the dropdown
        # Sort them for better user experience
        addresses = sorted(list(set(row['address'] for row in response.data if row.get('address'))))
        return jsonify(addresses)
    except Exception as e:
        print(f"Error fetching locations: {e}")
        return jsonify([])

if __name__ == '__main__':
    app.run(debug=True)