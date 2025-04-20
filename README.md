# TetraDash

A universal dashboard with admin and client functions, featuring dynamic app updating without the need to add another endpoint.

## Features

- **User Authentication and Management**:
  - Users can log in and log out.
  - Admins can create, delete, and manage user accounts, including resetting passwords and toggling admin status.

- **App Management**:
  - Admins can create and manage apps.
  - Apps can be restricted to admin users or specific groups.

- **Group Management**:
  - Admins can create and manage groups.
  - Users can be added to or removed from groups.
  - Apps can be restricted to specific groups.

- **Dynamic App Updating**:
  - Apps are dynamically loaded from the `apps` directory.
  - No need to add new endpoints for new apps.

- **Security Features**:
  - Login attempts are tracked, and accounts are temporarily locked after multiple failed attempts.
  - CAPTCHA verification is required after multiple failed login attempts.

## Components

### Flask and Flask-Login

The application uses Flask for the web framework and Flask-Login for user session management.

### User Class

The `User` class represents a user with attributes like `id`, `username`, `password_hash`, `is_admin`, and `groups`.

### In-memory User Storage

Users are stored in a JSON file (`users.json`). In a production environment, this should be replaced with a database.

### Routes

- `/`: Redirects to the dashboard.
- `/login`: Handles user login.
- `/logout`: Handles user logout.
- `/dashboard`: Displays the dashboard with a list of apps.
- `/new-user` and `/user-management`: Allows admins to manage users.
- `/group-management`: Allows admins to manage groups.
- `/changelog/<int:week>/<int:year>`: Displays a changelog PDF.
- `/app/<app_name>`: Serves the app content.

### Templates

- `login.html`: Login page.
- `dashboard.html`: Dashboard page.
- `user_management.html`: User management page.
- `group_management.html`: Group management page.
- `app_wrapper.html`: Wrapper for serving app content.

### Static Files

- Apps are stored in the `apps` directory.
- Each app can have an `index.html` file and an optional `icon.png` file.
- Apps can be restricted to admin users by creating a `.admin` file in the app directory.
- Apps can be restricted to specific groups by creating a `.groupname` file in the app directory.

## License

The software is published under the [QKOL license v3](https://github.com/QKing-Official/QKOL/blob/main/v3.0/QKING_OPEN_LICENSE_v3.0).

## Running the Application

To run the application, ensure you have Flask installed and then execute the script. The application will be accessible at `http://localhost:80`.

```bash
pip install flask flask-login
python app.py.py
