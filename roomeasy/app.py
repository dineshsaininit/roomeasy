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

# --- Authentication Decorators ---

def login_required(f):
    def wrap(*args, **kwargs):
        if 'user' not in session:
            flash("You need to login first!", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

def verified_required(f):
    """Requires the user to be logged in AND verified by admin."""
    def wrap(*args, **kwargs):
        if 'user' not in session:
            flash("You need to login first!", "error")
            return redirect(url_for('login'))
        if not session.get('is_verified'):
            flash("You need to verify your identity before performing this action.", "error")
            return redirect(url_for('verification_pending'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

def admin_required(f):
    """Requires the user to be logged in AND have admin role."""
    def wrap(*args, **kwargs):
        if 'user' not in session:
            flash("Admin login required.", "error")
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash("Access denied. Admins only.", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# --- Routes ---

@app.route('/')
def index():
    search_query = request.args.get('q', '').strip()
    
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
@verified_required
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
@verified_required
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
@verified_required
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
@verified_required
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
            new_user_data = {
                "full_name": full_name,
                "email": email,
                "password": password,
                "role": "user",
                "is_verified": False,
                "verification_status": "none",
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
                session['is_verified'] = user.get('is_verified', False)
                session['verification_status'] = user.get('verification_status', 'none')
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
        
        rooms_res = supabase.table('rooms').select("*").eq('owner_id', user_id).order('created_at', desc=True).execute()
        my_rooms = rooms_res.data
        
        if my_rooms:
            for room in my_rooms:
                if room['status'] == 'booked':
                    b_res = supabase.table('bookings').select("*").eq('room_id', room['id']).order('created_at', desc=True).limit(1).execute()
                    if b_res.data:
                        booking = b_res.data[0]
                        renter_res = supabase.table('user_profiles').select("*").eq('id', booking['user_id']).single().execute()
                        if renter_res.data:
                            renter = renter_res.data
                            room['renter_name'] = renter.get('full_name', 'Unknown')
                            room['renter_email'] = renter.get('email', 'Unknown')
                            room['renter_phone'] = "Not Available"
                            room['booking_type'] = booking.get('booking_type', 'standard')

        bookings_res = supabase.table('bookings').select("*").eq('user_id', user_id).order('created_at', desc=True).execute()
        my_bookings = bookings_res.data
        
        if my_bookings:
            room_ids = [b['room_id'] for b in my_bookings]
            if room_ids:
                r_res = supabase.table('rooms').select("*").in_('id', room_ids).execute()
                rooms_map = {r['id']: r for r in r_res.data}
                
                for b in my_bookings:
                    r = rooms_map.get(b['room_id'])
                    if r:
                        b['room_title'] = r['title']
                        b['room_image'] = r['image_url']
                        b['room_address'] = r['address']
                        b['next_rent_amount'] = r['price_per_month']
                        b['remaining_amount'] = r['price_per_month'] - b.get('amount_paid', 0)
                        b['host_email'] = "Contact Support"
                        b['start_date'] = b['created_at'][:10] 
                        b['months_stayed'] = 1 
                        b['next_due_date'] = "5th of next month"
                        b['type'] = b['booking_type']

        wishlist_items = []
        w_res = supabase.table('wishlist').select('room_id').eq('user_id', user_id).execute()
        if w_res.data:
            w_ids = [w['room_id'] for w in w_res.data]
            if w_ids:
                w_rooms_res = supabase.table('rooms').select("*").in_('id', w_ids).execute()
                wishlist_items = w_rooms_res.data

        # Fetch latest verification request if exists
        verification_req = None
        try:
            v_res = supabase.table('verification_requests').select("*").eq('user_id', user_id).order('created_at', desc=True).limit(1).execute()
            if v_res.data:
                verification_req = v_res.data[0]
        except:
            pass

        return render_template('profile.html', 
                               user=user, 
                               my_rooms=my_rooms, 
                               my_bookings=my_bookings, 
                               wishlist_items=wishlist_items,
                               verification_req=verification_req)
                               
    except Exception as e:
        print(f"Profile error: {e}")
        flash(f"Error fetching profile: {e}", "error")
        return redirect(url_for('index'))


# --- Verification Routes ---

@app.route('/request-verification', methods=['GET', 'POST'])
@login_required
def request_verification():
    user_id = session['user']
    
    # If already verified, go home
    if session.get('is_verified'):
        flash("Your account is already verified!", "success")
        return redirect(url_for('index'))
    
    # Check if there's already a pending request
    try:
        existing = supabase.table('verification_requests').select("*").eq('user_id', user_id).eq('status', 'pending').execute()
        if existing.data:
            flash("You already have a pending verification request.", "info")
            return redirect(url_for('verification_pending'))
    except:
        pass

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        address = request.form.get('address')
        aadhar_number = request.form.get('aadhar_number')
        aadhar_image_url = request.form.get('aadhar_image_url')
        pan_number = request.form.get('pan_number')
        pan_image_url = request.form.get('pan_image_url')
        selfie_url = request.form.get('selfie_url')
        property_proof_url = request.form.get('property_proof_url')
        additional_notes = request.form.get('additional_notes', '')

        # Basic validation
        if not all([full_name, address, aadhar_number, aadhar_image_url, pan_number, selfie_url]):
            flash("Please fill in all required fields.", "error")
            return render_template('verification_request.html')

        try:
            # Insert verification request
            v_data = {
                "user_id": user_id,
                "full_name": full_name,
                "address": address,
                "aadhar_number": aadhar_number,
                "aadhar_image_url": aadhar_image_url,
                "pan_number": pan_number,
                "pan_image_url": pan_image_url,
                "selfie_url": selfie_url,
                "property_proof_url": property_proof_url,
                "additional_notes": additional_notes,
                "status": "pending"
            }
            supabase.table('verification_requests').insert(v_data).execute()
            
            # Update user's verification_status
            supabase.table('user_profiles').update({
                "verification_status": "pending"
            }).eq('id', user_id).execute()
            
            # Update session
            session['verification_status'] = 'pending'
            
            flash("Verification request submitted successfully! We'll review your documents shortly.", "success")
            return redirect(url_for('verification_pending'))
        except Exception as e:
            flash(f"Error submitting verification: {str(e)}", "error")

    # Pre-fill form with existing profile data
    try:
        user_res = supabase.table('user_profiles').select("*").eq('id', user_id).single().execute()
        user_data = user_res.data
    except:
        user_data = {}

    return render_template('verification_request.html', user=user_data)


@app.route('/verification-pending')
@login_required
def verification_pending():
    user_id = session['user']
    
    # If already verified, redirect home
    if session.get('is_verified'):
        return redirect(url_for('index'))
    
    # Fetch latest verification request
    verification_req = None
    try:
        v_res = supabase.table('verification_requests').select("*").eq('user_id', user_id).order('created_at', desc=True).limit(1).execute()
        if v_res.data:
            verification_req = v_res.data[0]
    except:
        pass
    
    # If no request submitted yet, redirect to form
    status = session.get('verification_status', 'none')
    if status == 'none' and not verification_req:
        return redirect(url_for('request_verification'))
    
    return render_template('verification_pending.html', 
                           verification_req=verification_req,
                           status=status)


# --- Admin Routes ---

@app.route('/admin')
@admin_required
def admin_dashboard():
    try:
        users_res = supabase.table('user_profiles').select("*", count='exact').execute()
        total_users = len(users_res.data) if users_res.data else 0
        
        pending_res = supabase.table('verification_requests').select("*").eq('status', 'pending').execute()
        pending_count = len(pending_res.data) if pending_res.data else 0
        
        rooms_res = supabase.table('rooms').select("*", count='exact').execute()
        total_rooms = len(rooms_res.data) if rooms_res.data else 0
        
        buildings_res = supabase.table('buildings').select("*", count='exact').execute()
        total_buildings = len(buildings_res.data) if buildings_res.data else 0
        
        bookings_res = supabase.table('bookings').select("*", count='exact').execute()
        total_bookings = len(bookings_res.data) if bookings_res.data else 0
        
        # Recent verification requests (last 5)
        recent_verifications = supabase.table('verification_requests').select("*").order('created_at', desc=True).limit(5).execute()
        
    except Exception as e:
        print(f"Admin dashboard error: {e}")
        flash(f"Error loading dashboard: {e}", "error")
        total_users = pending_count = total_rooms = total_buildings = total_bookings = 0
        recent_verifications = type('obj', (object,), {'data': []})()
    
    return render_template('admin_dashboard.html',
                           total_users=total_users,
                           pending_count=pending_count,
                           total_rooms=total_rooms,
                           total_buildings=total_buildings,
                           total_bookings=total_bookings,
                           recent_verifications=recent_verifications.data)


@app.route('/admin/verifications')
@admin_required
def admin_verifications():
    status_filter = request.args.get('status', 'all')
    try:
        query = supabase.table('verification_requests').select("*").order('created_at', desc=True)
        if status_filter != 'all':
            query = query.eq('status', status_filter)
        verifications_res = query.execute()
        verifications = verifications_res.data
        
        # Enrich with user emails
        if verifications:
            user_ids = [v['user_id'] for v in verifications]
            users_res = supabase.table('user_profiles').select("id, full_name, email").in_('id', user_ids).execute()
            users_map = {u['id']: u for u in users_res.data}
            for v in verifications:
                u = users_map.get(v['user_id'], {})
                v['user_email'] = u.get('email', 'N/A')
                v['user_full_name'] = u.get('full_name', 'N/A')
                
    except Exception as e:
        flash(f"Error loading verifications: {e}", "error")
        verifications = []
    
    return render_template('admin_verifications.html', 
                           verifications=verifications,
                           status_filter=status_filter)


@app.route('/admin/verify/<int:req_id>', methods=['POST'])
@admin_required
def admin_verify(req_id):
    action = request.form.get('action')  # 'approve' or 'reject'
    admin_note = request.form.get('admin_note', '')
    
    if action not in ['approve', 'reject']:
        flash("Invalid action.", "error")
        return redirect(url_for('admin_verifications'))
    
    try:
        # Get the verification request to find user_id
        v_res = supabase.table('verification_requests').select("*").eq('id', req_id).single().execute()
        v_req = v_res.data
        
        if not v_req:
            flash("Verification request not found.", "error")
            return redirect(url_for('admin_verifications'))
        
        user_id = v_req['user_id']
        new_status = 'approved' if action == 'approve' else 'rejected'
        
        # Update verification request
        from datetime import datetime
        supabase.table('verification_requests').update({
            "status": new_status,
            "admin_note": admin_note,
            "reviewed_at": datetime.utcnow().isoformat()
        }).eq('id', req_id).execute()
        
        # Update user profile
        user_update = {
            "verification_status": new_status,
            "is_verified": (action == 'approve')
        }
        supabase.table('user_profiles').update(user_update).eq('id', user_id).execute()
        
        flash(f"User has been {'approved' if action == 'approve' else 'rejected'} successfully.", "success")
        
    except Exception as e:
        flash(f"Error processing verification: {e}", "error")
    
    return redirect(url_for('admin_verifications'))


@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        users_res = supabase.table('user_profiles').select("*").order('created_at', desc=True).execute()
        users = users_res.data
    except Exception as e:
        flash(f"Error loading users: {e}", "error")
        users = []
    
    return render_template('admin_users.html', users=users)


@app.route('/admin/toggle-role/<user_id>', methods=['POST'])
@admin_required
def admin_toggle_role(user_id):
    """Toggle a user between 'user' and 'admin' role."""
    try:
        u_res = supabase.table('user_profiles').select("role").eq('id', user_id).single().execute()
        current_role = u_res.data.get('role', 'user')
        new_role = 'admin' if current_role == 'user' else 'user'
        supabase.table('user_profiles').update({"role": new_role}).eq('id', user_id).execute()
        flash(f"User role changed to {new_role}.", "success")
    except Exception as e:
        flash(f"Error changing role: {e}", "error")
    return redirect(url_for('admin_users'))


@app.route('/book/<int:room_id>', methods=['POST'])
@verified_required
def book_room(room_id):
    # Check if user is the owner
    try:
        room_res = supabase.table('rooms').select("owner_id").eq('id', room_id).single().execute()
        if room_res.data and str(room_res.data['owner_id']) == str(session['user']):
            flash("You cannot book your own property!", "error")
            return redirect(url_for('room_details', room_id=room_id))
    except Exception as e:
        print(f"Error checking ownership: {e}")

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

@app.route('/pay_remainder/<int:booking_id>', methods=['POST'])
@login_required
def pay_remainder(booking_id):
    try:
        b_res = supabase.table('bookings').select("*").eq('id', booking_id).single().execute()
        booking = b_res.data
        
        if not booking:
            flash("Booking not found.", "error")
            return redirect(url_for('profile'))
            
        if str(booking['user_id']) != str(session['user']):
            flash("Unauthorized request.", "error")
            return redirect(url_for('profile'))
            
        r_res = supabase.table('rooms').select("price_per_month").eq('id', booking['room_id']).single().execute()
        room_data = r_res.data
        full_price = room_data['price_per_month']
        
        supabase.table('bookings').update({
            "amount_paid": full_price,
            "booking_type": "full"
        }).eq('id', booking_id).execute()
        
        flash("Payment successful via Razorpay! Your booking is now fully paid.", "success")
        return redirect(url_for('profile'))
        
    except Exception as e:
        flash(f"Payment Error: {str(e)}", "error")
        return redirect(url_for('profile'))

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