from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
import json
import os
from datetime import datetime
import calendar as cal
import hashlib
from functools import wraps
import base64
import subprocess

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'

# File paths
EVENTS_FILE = 'events.json'
ADMINS_FILE = 'admins.json'
UPLOAD_FOLDER = 'uploads/temp'
BACKUP_DIR = 'backups'

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs('images', exist_ok=True)

# ==================== JSON File Handling ====================

def load_json(filename):
    """Load JSON file, create if doesn't exist"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except:
            return {} if filename == ADMINS_FILE else {"events": []}
    return {} if filename == ADMINS_FILE else {"events": []}

def save_json(data, filename):
    """Save JSON file with backup"""
    if os.path.exists(filename):
        backup_name = f"{BACKUP_DIR}/{os.path.basename(filename)}.backup"
        with open(filename, 'r') as f:
            backup_data = f.read()
        with open(backup_name, 'w') as f:
            f.write(backup_data)

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def initialize_files():
    """Initialize JSON files if they don't exist"""
    if not os.path.exists(EVENTS_FILE):
        save_json({"events": []}, EVENTS_FILE)

    if not os.path.exists(ADMINS_FILE):
        admins = {
            "admins": [
                {
                    "username": "ankit",
                    "password": hashlib.sha256("ankit".encode()).hexdigest(),
                    "email": "ankit.sharma@pega.com"
                }
            ]
        }
        save_json(admins, ADMINS_FILE)

# ==================== Authentication ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        admins_data = load_json(ADMINS_FILE)
        for admin in admins_data.get('admins', []):
            if admin['username'] == username and admin['password'] == hashlib.sha256(password.encode()).hexdigest():
                session['username'] = username
                return redirect(url_for('dashboard'))

        return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# ==================== Dashboard ====================

@app.route('/')
@login_required
def dashboard():
    """Main dashboard - upcoming and recent events"""
    events_data = load_json(EVENTS_FILE)
    events = events_data.get('events', [])

    events.sort(key=lambda x: x['event_date'], reverse=False)

    today = datetime.now().strftime('%Y-%m-%d')
    upcoming = [e for e in events if e['event_date'] >= today]
    past = [e for e in events if e['event_date'] < today]

    return render_template('dashboard.html',
                         upcoming_events=upcoming[:5],
                         past_events=past[:5],
                         total_events=len(events),
                         username=session.get('username'))

# ==================== Calendar ====================

@app.route('/calendar')
@login_required
def calendar_view():
    """Monthly calendar view"""
    events_data = load_json(EVENTS_FILE)
    events = events_data.get('events', [])

    today = datetime.now()
    year = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))

    month_calendar = cal.monthcalendar(year, month)

    events_by_date = {}
    for event in events:
        date = event['event_date']
        if events_by_date.get(date):
            events_by_date[date].append(event)
        else:
            events_by_date[date] = [event]

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    month_name = cal.month_name[month]

    return render_template('calendar.html',
                         year=year,
                         month=month,
                         month_name=month_name,
                         calendar=month_calendar,
                         events_by_date=events_by_date,
                         prev_year=prev_year,
                         prev_month=prev_month,
                         next_year=next_year,
                         next_month=next_month,
                         username=session.get('username'))

# ==================== Events CRUD ====================

@app.route('/event/new', methods=['GET', 'POST'])
@login_required
def new_event():
    """Create new event"""
    if request.method == 'POST':
        events_data = load_json(EVENTS_FILE)

        new_id = max([e['id'] for e in events_data.get('events', [])], default=0) + 1

        new_event = {
            'id': new_id,
            'client_name': request.form.get('client_name'),
            'event_date': request.form.get('event_date'),
            'location': request.form.get('location'),
            'experiences': request.form.get('experiences'),
            'status': request.form.get('status', 'tentative'),
            'created_by': session.get('username'),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        events_data['events'].append(new_event)
        save_json(events_data, EVENTS_FILE)

        return redirect(url_for('event_detail', event_id=new_id))

    return render_template('event_form.html', event=None, username=session.get('username'))

@app.route('/event/<int:event_id>')
@login_required
def event_detail(event_id):
    """View event details"""
    events_data = load_json(EVENTS_FILE)
    event = None

    for e in events_data.get('events', []):
        if e['id'] == event_id:
            event = e
            break

    if not event:
        return redirect(url_for('dashboard'))

    return render_template('event_detail.html',
                         event=event,
                         username=session.get('username'))

@app.route('/event/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    """Edit event"""
    events_data = load_json(EVENTS_FILE)
    event = None
    event_index = None

    for i, e in enumerate(events_data.get('events', [])):
        if e['id'] == event_id:
            event = e
            event_index = i
            break

    if not event:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        event['client_name'] = request.form.get('client_name')
        event['event_date'] = request.form.get('event_date')
        event['location'] = request.form.get('location')
        event['experiences'] = request.form.get('experiences')
        event['status'] = request.form.get('status')

        events_data['events'][event_index] = event
        save_json(events_data, EVENTS_FILE)

        return redirect(url_for('event_detail', event_id=event_id))

    return render_template('event_form.html',
                         event=event,
                         username=session.get('username'))

@app.route('/event/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    """Delete event"""
    events_data = load_json(EVENTS_FILE)
    events_data['events'] = [e for e in events_data['events'] if e['id'] != event_id]
    save_json(events_data, EVENTS_FILE)

    return redirect(url_for('dashboard'))

@app.route('/event/<int:event_id>/status', methods=['POST'])
@login_required
def update_status(event_id):
    """Update event status"""
    events_data = load_json(EVENTS_FILE)
    status = request.form.get('status')

    for event in events_data.get('events', []):
        if event['id'] == event_id:
            event['status'] = status
            break

    save_json(events_data, EVENTS_FILE)
    return redirect(url_for('event_detail', event_id=event_id))

# ==================== Debriefing Generator Routes ====================

@app.route('/debriefing')
@login_required
def debriefing_form():
    """Debriefing generator form"""
    debrief_event = session.get('debrief_event', {})
    return render_template('debriefing_form.html',
                         event=debrief_event,
                         username=session.get('username'))

@app.route('/generate-debriefing', methods=['POST'])
@login_required
def generate_debriefing():
    """Generate debriefing document"""
    try:
        # Get form data
        client_name = request.form.get('client_name', '').strip()
        client_industry = request.form.get('client_industry', '').strip()
        session_date = request.form.get('session_date', '').strip()

        if not client_name or not session_date:
            return jsonify({'error': 'Client name and date required'}), 400

        # Handle presentation file (PDF only)
        presentation_b64 = None
        if 'presentation' in request.files:
            file = request.files['presentation']
            if file.filename and file.filename.lower().endswith('.pdf'):
                filepath = os.path.join(UPLOAD_FOLDER, file.filename)
                file.save(filepath)

                # Read and encode PDF
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        presentation_b64 = base64.b64encode(f.read()).decode('utf-8')

        # Handle client logo
        logo_b64 = None
        if 'client_logo' in request.files and request.files['client_logo'].filename:
            logo_file = request.files['client_logo']
            logo_path = os.path.join(UPLOAD_FOLDER, logo_file.filename)
            logo_file.save(logo_path)
            with open(logo_path, 'rb') as f:
                logo_b64 = base64.b64encode(f.read()).decode('utf-8')
        else:
            # Try to load Pega logo from images folder
            for filename in ['pega_logo.png', 'pega.png', 'logo.png']:
                logo_path = os.path.join('images', filename)
                if os.path.exists(logo_path):
                    with open(logo_path, 'rb') as f:
                        logo_b64 = base64.b64encode(f.read()).decode('utf-8')
                    break

        # Handle event images
        images_b64 = []
        if 'event_images' in request.files:
            files = request.files.getlist('event_images')
            for file in files:
                if file.filename:
                    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
                    file.save(filepath)
                    with open(filepath, 'rb') as f:
                        img_b64 = base64.b64encode(f.read()).decode('utf-8')
                        ext = os.path.splitext(file.filename)[1].lower()
                        mime_type = 'image/jpeg' if ext in ['.jpg', '.jpeg'] else 'image/png'
                        images_b64.append({
                            'data': img_b64,
                            'name': file.filename,
                            'mime': mime_type
                        })

        # Generate HTML
        html_content = generate_html(
            client_name=client_name,
            client_industry=client_industry,
            session_date=session_date,
            logo_b64=logo_b64,
            presentation_b64=presentation_b64,
            images_b64=images_b64,
            client_info=request.form.get('client_info', '').strip(),
            session_objective=request.form.get('session_objective', '').strip(),
            topics_covered=request.form.get('topics_covered', '').strip(),
            audience_profile=request.form.get('audience_profile', '').strip(),
            client_overview=request.form.get('client_overview', '').strip(),
            engagement_context=request.form.get('engagement_context', '').strip(),
            recording_link=request.form.get('recording_link', '').strip(),
            what_went_well=request.form.get('what_went_well', '').strip(),
            delivery_observations=request.form.get('delivery_observations', '').strip(),
            areas_improvement=request.form.get('areas_improvement', '').strip(),
            audience_feedback=request.form.get('audience_feedback', '').strip(),
            action_items=request.form.get('action_items', '').strip(),
            lessons_learned=request.form.get('lessons_learned', '').strip(),
            recommendations=request.form.get('recommendations', '').strip()
        )

        return send_file(
            io.BytesIO(html_content.encode('utf-8')),
            mimetype='text/html',
            as_attachment=True,
            download_name=f"debriefing_{client_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.html"
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_html(**kwargs):
    """Generate professional HTML debriefing document"""
    logo_html = f'<img src="data:image/png;base64,{kwargs["logo_b64"]}" alt="Client Logo" style="max-width: 200px; max-height: 80px;">' if kwargs['logo_b64'] else ''

    presentation_html = f'<iframe src="data:application/pdf;base64,{kwargs["presentation_b64"]}" style="width: 100%; height: 600px; border: 2px solid #0066CC; border-radius: 8px;"></iframe>' if kwargs['presentation_b64'] else '<p style="color: #999;">No presentation available</p>'

    images_html = ''
    if kwargs['images_b64']:
        images_html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;" id="imageGallery">'
        for i, img in enumerate(kwargs['images_b64']):
            img_src = f"data:{img['mime']};base64,{img['data']}"
            images_html += f'<img src="{img_src}" alt="{img["name"]}" style="max-width: 100%; border-radius: 8px; cursor: pointer; transition: transform 0.2s;" class="gallery-img" data-index="{i}" onmouseover="this.style.transform=\'scale(1.05)\'" onmouseout="this.style.transform=\'scale(1)\'">'
        images_html += '</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Debriefing Report - {kwargs['client_name']}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 40px; }}
        header {{ background: linear-gradient(135deg, #0066CC 0%, #004B99 100%); color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; }}
        h1 {{ font-size: 2em; margin-bottom: 10px; }}
        h2 {{ color: #0066CC; margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid #00CCFF; padding-bottom: 10px; }}
        h3 {{ color: #004B99; margin-top: 20px; margin-bottom: 10px; }}
        section {{ margin-bottom: 30px; padding: 20px; background: #f9f9f9; border-radius: 8px; }}
        .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .meta-item {{ border-left: 4px solid #0066CC; padding-left: 15px; }}
        .meta-label {{ font-size: 0.9em; color: #666; margin-bottom: 5px; }}
        .meta-value {{ font-weight: 600; font-size: 1.1em; }}
        ul {{ margin-left: 20px; }}
        li {{ margin-bottom: 10px; }}
        .badge {{ display: inline-block; padding: 5px 12px; border-radius: 20px; font-size: 0.85em; font-weight: 600; }}
        .badge-confirmed {{ background: #d4edda; color: #155724; }}
        .badge-tentative {{ background: #fff3cd; color: #856404; }}
        footer {{ text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 0.9em; }}

        /* Image Modal Styles */
        .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.8); }}
        .modal.active {{ display: flex; justify-content: center; align-items: center; }}
        .modal-content {{ position: relative; max-width: 90%; max-height: 90vh; }}
        .modal-content img {{ max-width: 100%; max-height: 90vh; border-radius: 8px; }}
        .close-modal {{ position: absolute; top: 20px; right: 30px; color: white; font-size: 40px; font-weight: bold; cursor: pointer; background: rgba(0,0,0,0.5); width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; border-radius: 50%; }}
        .close-modal:hover {{ background: rgba(0,0,0,0.8); }}
        .prev-modal, .next-modal {{ position: absolute; top: 50%; transform: translateY(-50%); color: white; font-size: 30px; font-weight: bold; cursor: pointer; background: rgba(0,0,0,0.5); padding: 15px 20px; border-radius: 4px; user-select: none; }}
        .prev-modal:hover, .next-modal:hover {{ background: rgba(0,0,0,0.8); }}
        .prev-modal {{ left: 20px; }}
        .next-modal {{ right: 20px; }}

        @media print {{ body {{ background: white; }} .container {{ padding: 0; }} .modal {{ display: none !important; }} }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>📄 Debriefing Report</h1>
                <p>{kwargs['client_name']} | {kwargs['session_date']}</p>
            </div>
            {logo_html}
        </header>

        <section>
            <h2>Session Information</h2>
            <div class="meta">
                <div class="meta-item">
                    <div class="meta-label">Client Name</div>
                    <div class="meta-value">{kwargs['client_name']}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Industry</div>
                    <div class="meta-value">{kwargs['client_industry'] or 'Not specified'}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Session Date</div>
                    <div class="meta-value">{kwargs['session_date']}</div>
                </div>
            </div>
        </section>

        {'<section><h2>Presentation Slides</h2>' + presentation_html + '</section>' if kwargs['presentation_b64'] else ''}

        {'<section><h2>Event Images</h2>' + images_html + '</section>' if images_html else ''}

        {f'<section><h2>Session Overview</h2><h3>Client Information</h3><p>{kwargs["client_info"]}</p></section>' if kwargs['client_info'] else ''}
        {f'<section><h3>Session Objective</h3><p>{kwargs["session_objective"]}</p></section>' if kwargs['session_objective'] else ''}
        {f'<section><h3>Topics Covered</h3><p style="white-space: pre-wrap;">{kwargs["topics_covered"]}</p></section>' if kwargs['topics_covered'] else ''}
        {f'<section><h3>Audience Profile</h3><p>{kwargs["audience_profile"]}</p></section>' if kwargs['audience_profile'] else ''}

        {f'<section><h2>Client Background</h2><h3>Client Overview</h3><p>{kwargs["client_overview"]}</p></section>' if kwargs['client_overview'] else ''}
        {f'<section><h3>Engagement Context</h3><p>{kwargs["engagement_context"]}</p></section>' if kwargs['engagement_context'] else ''}

        {f'<section><h2>Session Materials</h2><p><strong>Recording Link:</strong> <a href="{kwargs["recording_link"]}">{kwargs["recording_link"]}</a></p></section>' if kwargs['recording_link'] else ''}

        {f'<section><h2>What Went Well</h2><p>{kwargs["what_went_well"]}</p></section>' if kwargs['what_went_well'] else ''}
        {f'<section><h2>Delivery Observations</h2><p>{kwargs["delivery_observations"]}</p></section>' if kwargs['delivery_observations'] else ''}
        {f'<section><h2>Areas for Improvement</h2><p>{kwargs["areas_improvement"]}</p></section>' if kwargs['areas_improvement'] else ''}
        {f'<section><h2>Audience Feedback</h2><p>{kwargs["audience_feedback"]}</p></section>' if kwargs['audience_feedback'] else ''}
        {f'<section><h2>Action Items & Next Steps</h2><p style="white-space: pre-wrap;">{kwargs["action_items"]}</p></section>' if kwargs['action_items'] else ''}
        {f'<section><h2>Lessons Learned</h2><p>{kwargs["lessons_learned"]}</p></section>' if kwargs['lessons_learned'] else ''}
        {f'<section><h2>Recommendations for Future Sessions</h2><p>{kwargs["recommendations"]}</p></section>' if kwargs['recommendations'] else ''}

        <footer>
            <p>🔷 Pega Debriefing Report | Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}</p>
            <p>© 2026 Pegasystems Inc. All rights reserved.</p>
        </footer>
    </div>

    <!-- Image Modal -->
    <div id="imageModal" class="modal">
        <div class="modal-content">
            <span class="close-modal" onclick="closeImageModal()">&times;</span>
            <span class="prev-modal" onclick="prevImage()">&#10094;</span>
            <img id="modalImage" src="" alt="Event Image">
            <span class="next-modal" onclick="nextImage()">&#10095;</span>
        </div>
    </div>

    <script>
        let currentImageIndex = 0;
        let galleryImages = [];

        // Initialize gallery
        document.addEventListener('DOMContentLoaded', function() {{
            const gallery = document.getElementById('imageGallery');
            if (gallery) {{
                const imgs = gallery.querySelectorAll('.gallery-img');
                galleryImages = Array.from(imgs).map(img => img.src);

                // Add click handlers
                imgs.forEach((img, index) => {{
                    img.addEventListener('click', function() {{
                        openImageModal(index);
                    }});
                }});
            }}
        }});

        function openImageModal(index) {{
            if (galleryImages.length > 0) {{
                currentImageIndex = index;
                document.getElementById('modalImage').src = galleryImages[index];
                document.getElementById('imageModal').classList.add('active');
            }}
        }}

        function closeImageModal() {{
            document.getElementById('imageModal').classList.remove('active');
        }}

        function nextImage() {{
            if (galleryImages.length > 0) {{
                currentImageIndex = (currentImageIndex + 1) % galleryImages.length;
                document.getElementById('modalImage').src = galleryImages[currentImageIndex];
            }}
        }}

        function prevImage() {{
            if (galleryImages.length > 0) {{
                currentImageIndex = (currentImageIndex - 1 + galleryImages.length) % galleryImages.length;
                document.getElementById('modalImage').src = galleryImages[currentImageIndex];
            }}
        }}

        // Close modal on outside click
        const modal = document.getElementById('imageModal');
        if (modal) {{
            modal.addEventListener('click', function(e) {{
                if (e.target === this) {{
                    closeImageModal();
                }}
            }});
        }}

        // Keyboard navigation
        document.addEventListener('keydown', function(e) {{
            if (document.getElementById('imageModal').classList.contains('active')) {{
                if (e.key === 'ArrowRight') nextImage();
                if (e.key === 'ArrowLeft') prevImage();
                if (e.key === 'Escape') closeImageModal();
            }}
        }});
    </script>
</body>
</html>"""
    return html

# ==================== Admin Management ====================

@app.route('/admin')
@login_required
def admin_panel():
    """Admin panel for managing admins"""
    admins_data = load_json(ADMINS_FILE)
    admins = admins_data.get('admins', [])

    return render_template('admin.html',
                         admins=admins,
                         username=session.get('username'))

@app.route('/admin/add', methods=['POST'])
@login_required
def add_admin():
    """Add new admin"""
    admins_data = load_json(ADMINS_FILE)

    new_admin = {
        'username': request.form.get('username'),
        'password': hashlib.sha256(request.form.get('password').encode()).hexdigest(),
        'email': request.form.get('email')
    }

    for admin in admins_data.get('admins', []):
        if admin['username'] == new_admin['username']:
            return jsonify({'error': 'Username already exists'}), 400

    admins_data['admins'].append(new_admin)
    save_json(admins_data, ADMINS_FILE)

    return redirect(url_for('admin_panel'))

@app.route('/admin/<username>/delete', methods=['POST'])
@login_required
def delete_admin(username):
    """Delete admin"""
    if username == session.get('username'):
        return jsonify({'error': 'Cannot delete yourself'}), 400

    admins_data = load_json(ADMINS_FILE)
    admins_data['admins'] = [a for a in admins_data['admins'] if a['username'] != username]
    save_json(admins_data, ADMINS_FILE)

    return redirect(url_for('admin_panel'))

# ==================== Error Handling ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500

# ==================== App Initialization ====================

if __name__ == '__main__':
    import io
    initialize_files()
    app.run(debug=True, port=5000)
