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
    filter_type = request.args.get('filter', '').strip()
    
    featured_buildings = []
    recommended_buildings = []
    all_buildings = []
    
    try:
        base_query = supabase.table('buildings').select("*")
        
        if search_query:
            session['user_location'] = search_query
            filter_condition = f"address.ilike.%{search_query}%,title.ilike.%{search_query}%,city.ilike.%{search_query}%"
            response = base_query.or_(filter_condition).execute()
            all_buildings = response.data
        else:
            response = base_query.execute()
            all_buildings = response.data
            
            if len(all_buildings) > 0:
                featured_buildings = random.sample(all_buildings, min(len(all_buildings), 5))
                remaining = [b for b in all_buildings if b not in featured_buildings]
                if remaining:
                    recommended_buildings = random.sample(remaining, min(len(remaining), 8))
                else:
                    recommended_buildings = all_buildings[:8]

    except Exception as e:
        print(f"Error fetching buildings: {e}")
        all_buildings = []

    return render_template('index.html', 
                           buildings=all_buildings, 
                           featured_buildings=featured_buildings,
                           recommended_buildings=recommended_buildings,
                           search_query=search_query)

@app.route('/building/<int:building_id>')
def building_details(building_id):
    try:
        b_res = supabase.table('buildings').select("*").eq('id', building_id).single().execute()
        building = b_res.data
        r_res = supabase.table('rooms').select("*").eq('building_id', building_id).eq('status', 'available').execute()
        rooms = r_res.data
        return render_template('building_details.html', building=building, rooms=rooms)
    except Exception as e:
        print(f"Error: {e}")
        flash("Building not found", "error")
        return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        title = request.form.get('title')
        desc = request.form.get('description')
        image_url = request.form.get('image_url')
        state = request.form.get('state')
        city = request.form.get('city')
        nearby_location = request.form.get('nearby_location')
        full_address = f"{nearby_location}, {city}, {state}"

        data = {
            "owner_id": session['user'],
            "title": title,
            "address": full_address,
            "state": state,
            "city": city,
            "nearby_location": nearby_location,
            "description": desc,
            "image_url": image_url
        }
        try:
            res = supabase.table('buildings').insert(data).execute()
            if res.data:
                new_id = res.data[0]['id']
                flash("Building listed! Now add rooms to it.", "success")
                return redirect(url_for('building_details', building_id=new_id))
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Error uploading building: {e}", "error")

    return render_template('upload.html')

# --- Edit Building Route ---
@app.route('/edit_building/<int:building_id>', methods=['GET', 'POST'])
@login_required
def edit_building(building_id):
    try:
        response = supabase.table('buildings').select("*").eq('id', building_id).single().execute()
        building = response.data
    except Exception as e:
        flash("Building not found.", "error")
        return redirect(url_for('index'))

    if str(building['owner_id']) != str(session['user']):
        flash("You can only edit your own buildings.", "error")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title')
        desc = request.form.get('description')
        image_url = request.form.get('image_url')
        state = request.form.get('state')
        city = request.form.get('city')
        nearby_location = request.form.get('nearby_location')
        
        full_address = f"{nearby_location}, {city}, {state}"

        data = {
            "title": title,
            "address": full_address,
            "state": state,
            "city": city,
            "nearby_location": nearby_location,
            "description": desc,
            "image_url": image_url
        }
        try:
            supabase.table('buildings').update(data).eq('id', building_id).execute()
            flash("Building updated successfully!", "success")
            return redirect(url_for('building_details', building_id=building_id))
        except Exception as e:
            flash(f"Error updating building: {e}", "error")

    return render_template('edit_building.html', building=building)

@app.route('/add_room/<int:building_id>', methods=['GET', 'POST'])
@login_required
def add_room(building_id):
    try:
        b_res = supabase.table('buildings').select("*").eq('id', building_id).single().execute()
        building = b_res.data
        if building['owner_id'] != session['user']:
            flash("You can only add rooms to your own buildings.", "error")
            return redirect(url_for('index'))
    except:
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title')
        price = float(request.form.get('price'))
        desc = request.form.get('description')
        image_url = request.form.get('image_url')
        amenities = request.form.getlist('amenities')
        more_images = request.form.getlist('more_images')
        more_images = [img for img in more_images if img.strip()]

        if not image_url: 
            image_url = building['image_url']

        data = {
            "owner_id": session['user'],
            "building_id": building_id,
            "title": title,
            "address": building['address'], 
            "state": building['state'],
            "city": building['city'],
            "nearby_location": building['nearby_location'],
            "price_per_month": price,
            "description": desc,
            "image_url": image_url,
            "status": "available",
            "amenities": amenities,
            "more_images": more_images
        }
        try:
            supabase.table('rooms').insert(data).execute()
            flash("Room added successfully!", "success")
            return redirect(url_for('building_details', building_id=building_id))
        except Exception as e:
            flash(f"Error adding room: {e}", "error")

    return render_template('add_room.html', building=building)

# --- Edit Room Route ---
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
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            title = request.form.get('title')
            price = float(request.form.get('price'))
            desc = request.form.get('description')
            image_url = request.form.get('image_url')
            amenities = request.form.getlist('amenities')
            more_images = request.form.getlist('more_images')
            more_images = [img for img in more_images if img.strip()]

            update_data = {
                "title": title,
                "price_per_month": price,
                "description": desc,
                "image_url": image_url,
                "amenities": amenities,
                "more_images": more_images
            }
            supabase.table('rooms').update(update_data).eq('id', room_id).execute()
            flash("Room updated successfully!", "success")
            return redirect(url_for('room_details', room_id=room_id))
        except Exception as e:
            flash(f"Error updating room: {e}", "error")

    return render_template('edit_room.html', room=room)


@app.route('/room/<int:room_id>')
def room_details(room_id):
    try:
        response = supabase.table('rooms').select("*").eq('id', room_id).single().execute()
        room = response.data
        full_rent = float(room['price_per_month'])
        lock_amount = round(full_rent * 0.05, 2)
        visit_fee = 50
        
        all_images = [room['image_url']]
        if room.get('more_images'):
            all_images.extend(room['more_images'])
        
        host_name = "Host"
        host_joined_date = "2023"
        host_email = ""
        host_image = ""
        
        try:
            owner_id = room.get('owner_id')
            if owner_id:
                host_res = supabase.table('user_profiles').select("*").eq('id', owner_id).single().execute()
                if host_res.data:
                    host_data = host_res.data
                    host_name = host_data.get('full_name', 'Host')
                    host_email = host_data.get('email', '')
                    host_image = host_data.get('profile_image_url', '')
                    created_at = host_data.get('created_at', '')
                    if created_at and len(created_at) >= 4:
                        host_joined_date = created_at[:4]
        except Exception as e:
            pass

        return render_template('room_details.html', 
                               room=room, 
                               all_images=all_images,
                               lock_amount=lock_amount, 
                               visit_fee=visit_fee,
                               host_name=host_name,
                               host_joined_date=host_joined_date,
                               host_email=host_email,
                               host_image=host_image)
    except Exception as e:
        print(f"Room details error: {e}")
        flash("Room not found.", "error")
        return redirect(url_for('index'))

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
        return redirect(url_for('index'))

@app.route('/toggle_wishlist/<int:room_id>', methods=['POST'])
def toggle_wishlist(room_id):
    if 'user' not in session: return jsonify({'status': 'error', 'message': 'Login required'}), 401
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
            new_user_data = { "full_name": full_name, "email": email, "password": password, "role": "user", "profile_image_url": profile_image if profile_image else "" }
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
        buildings_response = supabase.table('buildings').select("*").eq('owner_id', user_id).order('created_at', desc=True).execute()
        buildings = buildings_response.data
        return render_template('profile.html', user=user, buildings=buildings)
    except Exception as e:
        flash(f"Error fetching profile: {e}", "error")
        return redirect(url_for('index'))

@app.route('/book/<int:room_id>', methods=['POST'])
@login_required
def book_room(room_id):
    booking_type = request.form.get('booking_type')
    amount = request.form.get('amount')
    booking_data = { "user_id": session['user'], "room_id": room_id, "booking_type": booking_type, "amount_paid": float(amount) if amount else 0 }
    try:
        supabase.table('bookings').insert(booking_data).execute()
        if booking_type in ['full', 'lock']: supabase.table('rooms').update({"status": "booked"}).eq("id", room_id).execute()
        flash(f"Booking Successful! Type: {booking_type}", "success")
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"Booking failed: {e}", "error")
        return redirect(url_for('room_details', room_id=room_id))

@app.route('/api/locations')
def get_locations():
    try:
        response = supabase.table('buildings').select('city, state, address').execute()
        locations = set()
        for row in response.data:
            if row.get('city'): locations.add(row['city'])
            if row.get('state'): locations.add(row['state'])
            if not row.get('city') and row.get('address'):
                parts = row['address'].split(',')
                if len(parts) >= 2:
                    locations.add(parts[-2].strip())
                    locations.add(parts[-1].strip())
        return jsonify(sorted(list(locations)))
    except Exception as e:
        return jsonify([])

@app.route('/delete_room/<int:room_id>', methods=['POST'])
@login_required
def delete_room(room_id):
    try:
        supabase.table('rooms').delete().eq('id', room_id).execute()
        flash("Room deleted", "info")
    except:
        flash("Error deleting", "error")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)