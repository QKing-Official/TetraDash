from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from functools import wraps
import secrets
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class
class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin=False, groups=None):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin
        self.groups = groups if groups is not None else []

# In-memory user storage (replace with database in production)
users = {}

# Load users from JSON file or create if not exists
def load_users():
    if os.path.exists('users.json'):
        with open('users.json', 'r') as f:
            user_data = json.load(f)
            for user_id, user_info in user_data.items():
                users[user_id] = User(
                    user_id,
                    user_info['username'],
                    user_info['password_hash'],
                    user_info.get('is_admin', False),
                    user_info.get('groups', [])
                )
    else:
        # Create default admin user
        admin_id = '1'
        users[admin_id] = User(
            admin_id,
            'admin',
            generate_password_hash('admin123'),
            True
        )
        save_users()

def save_users():
    user_data = {}
    for user_id, user in users.items():
        user_data[user_id] = {
            'username': user.username,
            'password_hash': user.password_hash,
            'is_admin': user.is_admin,
            'groups': user.groups
        }
    with open('users.json', 'w') as f:
        json.dump(user_data, f, indent=4)

# Load users on startup
load_users()

@login_manager.user_loader
def load_user(user_id):
    return users.get(user_id)

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You need admin privileges to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Scan for apps
def get_apps():
    apps = []
    apps_dir = os.path.join(os.path.dirname(__file__), 'apps')

    if not os.path.exists(apps_dir):
        os.makedirs(apps_dir)

    for app_name in os.listdir(apps_dir):
        app_path = os.path.join(apps_dir, app_name)
        if os.path.isdir(app_path):
            # Check if this directory contains index.html
            if os.path.exists(os.path.join(app_path, 'index.html')):
                # Check if this app is admin-only
                is_admin_only = os.path.exists(os.path.join(app_path, '.admin'))

                # Check if this app is group-restricted
                is_group_restricted = False
                group_name = None
                for file in os.listdir(app_path):
                    if file.startswith('.') and file not in ['.admin', '.DS_Store']:
                        is_group_restricted = True
                        group_name = file[1:]
                        break

                # Skip this app if it's admin-only and the current user is not an admin
                if is_admin_only and (not current_user.is_authenticated or not current_user.is_admin):
                    continue

                # Skip this app if it's group-restricted and the current user is not in the group and not an admin
                if is_group_restricted and (not current_user.is_authenticated or (group_name not in current_user.groups and not current_user.is_admin)):
                    continue

                # Check for icon
                icon = 'default-icon.png'
                if os.path.exists(os.path.join(app_path, 'icon.png')):
                    icon = f'apps/{app_name}/icon.png'

                apps.append({
                    'name': app_name.replace('_', ' ').title(),
                    'url': app_name,
                    'icon': icon,
                    'is_admin_only': is_admin_only,
                    'is_group_restricted': is_group_restricted,
                    'group_name': group_name
                })

    return apps

# Register apps static folder
@app.route('/apps/<path:app_name>/<path:filename>')
def app_static(app_name, filename):
    apps_dir = os.path.join(os.path.dirname(__file__), 'apps')
    app_path = os.path.join(apps_dir, app_name)

    # Check if this app is admin-only
    if os.path.exists(os.path.join(app_path, '.admin')):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You need admin privileges to access this resource.', 'danger')
            return redirect(url_for('dashboard'))

    # Check if this app is group-restricted
    is_group_restricted = False
    group_name = None
    for file in os.listdir(app_path):
        if file.startswith('.') and file not in ['.admin', '.DS_Store']:
            is_group_restricted = True
            group_name = file[1:]
            break

    if is_group_restricted and (not current_user.is_authenticated or (group_name not in current_user.groups and not current_user.is_admin)):
        flash('You do not have access to this resource.', 'danger')
        return redirect(url_for('dashboard'))

    return send_from_directory(os.path.join(apps_dir, app_name), filename)

# Routes
@app.route('/')
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Import time if not already imported
    import time
    
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Initialize session variables for tracking login attempts if they don't exist
    if 'login_attempts' not in session:
        session['login_attempts'] = 0
        session['login_locked_until'] = 0
        session['captcha_failures'] = 0
    
    # Check if login is currently locked
    current_time = int(time.time())
    is_locked = False
    lock_remaining = 0
    
    if session['login_locked_until'] > current_time:
        is_locked = True
        lock_remaining = session['login_locked_until'] - current_time
        flash(f'Login temporarily disabled. Try again in {lock_remaining} seconds.', 'danger')
    
    if request.method == 'POST' and not is_locked:
        username = request.form.get('username')
        password = request.form.get('password')
        captcha_verified = request.form.get('captcha_verified') == 'true'
        
        # Check CAPTCHA first
        if not captcha_verified:
            session['captcha_failures'] += 1
            
            # Lock after repeated CAPTCHA failures (3 failures)
            if session['captcha_failures'] >= 4:
                session['login_locked_until'] = current_time + 300  # Lock for 5 minutes
                session['captcha_failures'] = 0
                flash('Too many failed verification attempts. Please try again in 5 minutes.', 'danger')
                is_locked = True
                lock_remaining = 300
            else:
                flash('Please complete the verification slider.', 'warning')
                return render_template('login.html', 
                                      login_locked=False,
                                      captcha_failed=True)
        
        # If CAPTCHA passed, reset CAPTCHA failure counter
        else:
            session['captcha_failures'] = 0
            
            # Now check username and password
            if not username or not password:
                flash('Please provide both username and password', 'warning')
                return render_template('login.html', login_locked=False)
            
            # Find user by username
            user_found = None
            for user in users.values():
                if user.username == username:
                    user_found = user
                    break
            
            # Check credentials
            if user_found and check_password_hash(user_found.password_hash, password):
                # Login successful - reset attempt counters
                session['login_attempts'] = 0
                session['captcha_failures'] = 0
                login_user(user_found)
                
                # Redirect to the page user wanted to access, or dashboard
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):  # Security check for open redirects
                    return redirect(next_page)
                return redirect(url_for('dashboard'))
            else:
                # Login failed - increment attempt counter
                session['login_attempts'] += 1
                
                # Lock account after 5 failed attempts for 5 minutes
                if session['login_attempts'] >= 5:
                    session['login_locked_until'] = current_time + 300  # Lock for 5 minutes
                    session['login_attempts'] = 0
                    flash('Too many failed login attempts. Please try again in 5 minutes.', 'danger')
                    is_locked = True
                    lock_remaining = 300
                else:
                    attempts_left = 5 - session['login_attempts']
                    flash(f'Invalid username or password. {attempts_left} attempts remaining.', 'danger')

    # GET request or failed POST
    return render_template('login.html', 
                          login_locked=is_locked,
                          lock_remaining=lock_remaining)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    apps_list = get_apps()
    return render_template('dashboard.html', apps=apps_list, user=current_user)

# Keep both routes for backward compatibility
@app.route('/new-user', methods=['GET', 'POST'])
@login_required
@admin_required
def new_user():
    return redirect(url_for('user_management'))

@app.route('/user-management', methods=['GET', 'POST'])
@login_required
@admin_required
def user_management():
    # Handle form submissions
    if request.method == 'POST':
        action = request.form.get('action')

        # Create new user
        if action == 'create_user':
            username = request.form.get('username')
            password = request.form.get('password')
            is_admin = 'is_admin' in request.form

            # Check if username already exists
            for user in users.values():
                if user.username == username:
                    flash('Username already exists', 'danger')
                    return redirect(url_for('user_management'))

            # Create new user
            user_id = str(max([int(uid) for uid in users.keys()]) + 1 if users else 1)
            users[user_id] = User(
                user_id,
                username,
                generate_password_hash(password),
                is_admin
            )
            save_users()
            flash(f'User {username} created successfully', 'success')

        # Delete user
        elif action == 'delete_user':
            user_id = request.form.get('user_id')
            if user_id in users:
                # Prevent admin from deleting themselves
                if user_id == current_user.id:
                    flash('You cannot delete your own account', 'danger')
                else:
                    username = users[user_id].username
                    del users[user_id]
                    save_users()
                    flash(f'User {username} deleted successfully', 'success')
            else:
                flash('User not found', 'danger')

        # Reset password
        elif action == 'reset_password':
            user_id = request.form.get('user_id')
            new_password = request.form.get('new_password')

            if user_id in users and new_password:
                users[user_id].password_hash = generate_password_hash(new_password)
                save_users()
                flash(f'Password for {users[user_id].username} reset successfully', 'success')
            else:
                flash('User not found or password empty', 'danger')

        # Toggle admin status
        elif action == 'toggle_admin':
            user_id = request.form.get('user_id')

            if user_id in users:
                # Prevent admin from removing their own admin status
                if user_id == current_user.id:
                    flash('You cannot change your own admin status', 'danger')
                else:
                    users[user_id].is_admin = not users[user_id].is_admin
                    status = "granted" if users[user_id].is_admin else "revoked"
                    save_users()
                    flash(f'Admin status {status} for {users[user_id].username}', 'success')
            else:
                flash('User not found', 'danger')

        return redirect(url_for('user_management'))

    # Sort users alphabetically by username for display
    sorted_users = sorted(users.values(), key=lambda x: x.username)
    apps_list = get_apps()
    return render_template('user_management.html', apps=apps_list, user=current_user, users=sorted_users)

@app.route('/changelog/<int:week>/<int:year>')
def changelog(week, year):
    filename = f'weekly-{week}-{year}.pdf'
    directory = os.path.join(app.root_path, 'static', 'changelogs')
    url = f'/static/changelogs/{filename}'
    return render_template('renderer.html', url=url)

@app.route('/group-management', methods=['GET', 'POST'])
@login_required
@admin_required
def group_management():
    groups_dir = os.path.join(os.path.dirname(__file__), 'groups')
    if not os.path.exists(groups_dir):
        os.makedirs(groups_dir)

    groups = [f for f in os.listdir(groups_dir) if os.path.isfile(os.path.join(groups_dir, f))]

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create_group':
            group_name = request.form.get('group_name')
            if group_name:
                group_file = os.path.join(groups_dir, f'.{group_name}')
                if not os.path.exists(group_file):
                    with open(group_file, 'w') as f:
                        f.write('')
                    flash(f'Group {group_name} created successfully', 'success')
                else:
                    flash('Group already exists', 'danger')
            else:
                flash('Group name cannot be empty', 'danger')

        elif action == 'delete_group':
            group_name = request.form.get('group_name')
            if group_name:
                group_file = os.path.join(groups_dir, f'.{group_name}')
                if os.path.exists(group_file):
                    os.remove(group_file)
                    flash(f'Group {group_name} deleted successfully', 'success')
                else:
                    flash('Group not found', 'danger')
            else:
                flash('Group name cannot be empty', 'danger')

        elif action == 'add_user_to_group':
            group_name = request.form.get('group_name')
            user_id = request.form.get('user_id')
            if group_name and user_id in users:
                if group_name not in users[user_id].groups:
                    users[user_id].groups.append(group_name)
                    save_users()
                    flash(f'User {users[user_id].username} added to group {group_name}', 'success')
                else:
                    flash('User is already in the group', 'danger')
            else:
                flash('Invalid group or user', 'danger')

        elif action == 'remove_user_from_group':
            group_name = request.form.get('group_name')
            user_id = request.form.get('user_id')
            if group_name and user_id in users:
                if group_name in users[user_id].groups:
                    users[user_id].groups.remove(group_name)
                    save_users()
                    flash(f'User {users[user_id].username} removed from group {group_name}', 'success')
                else:
                    flash('User is not in the group', 'danger')
            else:
                flash('Invalid group or user', 'danger')

        elif action == 'update_apps_for_group':
            group_name = request.form.get('group_name')
            app_names = request.form.getlist('app_name')
            if group_name:
                apps_dir = os.path.join(os.path.dirname(__file__), 'apps')
                for app_name in os.listdir(apps_dir):
                    app_path = os.path.join(apps_dir, app_name)
                    group_file = os.path.join(app_path, f'.{group_name}')
                    if app_name in app_names:
                        if not os.path.exists(group_file):
                            with open(group_file, 'w') as f:
                                f.write('')
                    else:
                        if os.path.exists(group_file):
                            os.remove(group_file)
                flash(f'Apps for group {group_name} updated successfully', 'success')
            else:
                flash('Group name cannot be empty', 'danger')

        # Store the active tab in session
        active_tab = request.form.get('active_tab')
        if active_tab:
            session['active_tab'] = active_tab

        return redirect(url_for('group_management'))

    # Get the active tab from session
    active_tab = session.get('active_tab', 'create')

    return render_template('group_management.html', groups=groups, users=users.values(), apps=get_apps(), active_tab=active_tab)

@app.route('/get_apps_for_group')
@login_required
@admin_required
def get_apps_for_group():
    group_name = request.args.get('group_name')
    if group_name:
        apps = get_apps()
        for app in apps:
            app['is_group_restricted'] = os.path.exists(os.path.join(os.path.dirname(__file__), 'apps', app['url'], f'.{group_name}'))
        return jsonify({'apps': apps})
    return jsonify({'apps': []})

@app.route('/get_users_for_group')
@login_required
@admin_required
def get_users_for_group():
    group_name = request.args.get('group_name')
    if group_name:
        users_in_group = [{'id': user.id, 'username': user.username} for user in users.values() if group_name in user.groups]
        return jsonify({'users': users_in_group})
    return jsonify({'users': []})

@app.route('/app/<app_name>')
@login_required
def serve_app(app_name):
    app_path = os.path.join(app.root_path, 'apps', app_name)
    if not os.path.exists(os.path.join(app_path, 'index.html')):
        flash(f'App {app_name} not found', 'danger')
        return redirect(url_for('dashboard'))

    # Check if this app is admin-only
    if os.path.exists(os.path.join(app_path, '.admin')):
        if not current_user.is_admin:
            flash('You need admin privileges to access this app.', 'danger')
            return redirect(url_for('dashboard'))

    # Check if this app is group-restricted
    is_group_restricted = False
    group_name = None
    for file in os.listdir(app_path):
        if file.startswith('.') and file not in ['.admin', '.DS_Store']:
            is_group_restricted = True
            group_name = file[1:]
            break

    if is_group_restricted and (not current_user.is_admin and group_name not in current_user.groups):
        flash('You do not have access to this app.', 'danger')
        return redirect(url_for('dashboard'))

    # Read the app's index.html file
    with open(os.path.join(app_path, 'index.html'), 'r') as f:
        app_content = f.read()

    apps_list = get_apps()
    # Render the base template with the app content
    return render_template('app_wrapper.html',
                          apps=apps_list,
                          user=current_user,
                          app_name=app_name,
                          app_content=app_content)

if __name__ == '__main__':
    # Create apps directory if it doesn't exist
    apps_dir = os.path.join(os.path.dirname(__file__), 'apps')
    if not os.path.exists(apps_dir):
        os.makedirs(apps_dir)

        # Create a sample app
        sample_app_dir = os.path.join(apps_dir, 'sample_app')
        os.makedirs(sample_app_dir, exist_ok=True)

        with open(os.path.join(sample_app_dir, 'index.html'), 'w') as f:
            f.write("""
<h1>Sample App</h1>
<div class="container mt-4">
    <div class="card">
        <div class="card-body">
            <h5 class="card-title">Sample App</h5>
            <p class="card-text">This is a sample app. You can replace this with your own content.</p>
            <a href="#" class="btn btn-primary">Sample Button</a>
        </div>
    </div>
</div>
            """)

        # Create an icon for the sample app
        with open(os.path.join(sample_app_dir, 'icon.png'), 'wb') as f:
            # This is a placeholder - in reality you'd add an actual icon file
            f.write(b'')

        # Create an admin-only sample app
        admin_app_dir = os.path.join(apps_dir, 'admin_only_app')
        os.makedirs(admin_app_dir, exist_ok=True)

        # Create .admin file to mark this as admin-only
        with open(os.path.join(admin_app_dir, '.admin'), 'w') as f:
            f.write('This app is only visible to admin users')

        with open(os.path.join(admin_app_dir, 'index.html'), 'w') as f:
            f.write("""
<h1>Admin Only App</h1>
<div class="container mt-4">
    <div class="card">
        <div class="card-body">
            <h5 class="card-title">Admin Only App</h5>
            <p class="card-text">This app is only visible to users with admin privileges.</p>
            <a href="#" class="btn btn-danger">Admin Action</a>
        </div>
    </div>
</div>
            """)

    # Make sure we have a default icon in static folder
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
        # Create a simple default icon (1x1 pixel transparent PNG)
        with open(os.path.join(static_dir, 'default-icon.png'), 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xcc\xe7\xe6\x00\x00\x00\x00IEND\xaeB`\x82')

    app.run(host='0.0.0.0', port=80)