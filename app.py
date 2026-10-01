"""Python server for the Ninth Dimension invitation."""
import json
import os
import secrets
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import URLError
from flask import Flask, jsonify, render_template, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4096
# Set a persistent SECRET_KEY in production; the local fallback expires on restart.
signer = URLSafeTimedSerializer(os.environ.get('SECRET_KEY') or secrets.token_hex(32))
lock = threading.Lock()
recent = []
ROLES = {'маг', 'лицар', 'монстр'}

@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

@app.get('/')
def index():
    token = signer.dumps({'id': secrets.token_hex(16)})
    return render_template('index.html', token=token)

@app.get('/health')
def health():
    return {'ok': True}

def send_email(role, visit_id):
    key = os.environ.get('RESEND_API_KEY', '')
    if not key:
        raise RuntimeError('mail_not_configured')
    payload = {
        'from': os.environ.get('MAIL_FROM', 'Дев’ятий вимір <onboarding@resend.dev>'),
        'to': [os.environ.get('MAIL_TO', 'st.mariaj@gmail.com')],
        'subject': 'Дев’ятий вимір — вибір персонажа',
        'text': f'Гравець підтвердив вибір: {role}.\nІсторія: Дев’ятий вимір.\nКод проходження: {visit_id}',
    }
    req = Request('https://api.resend.com/emails', data=json.dumps(payload).encode(), method='POST', headers={
        'Authorization': f'Bearer {key}', 'Content-Type': 'application/json',
        'Idempotency-Key': f'ninth-dimension/{visit_id}', 'User-Agent': 'NinthDimension/1.0',
    })
    with urlopen(req, timeout=15) as response:
        result = json.load(response)
    if not result.get('id'):
        raise RuntimeError('mail_not_accepted')

@app.post('/api/confirm')
def confirm():
    if request.headers.get('Sec-Fetch-Site') == 'cross-site':
        return jsonify(ok=False, error='Онови сторінку й спробуй ще раз.'), 403
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(ok=False, error='Некоректний запит.'), 400
    role, word, token = data.get('character'), data.get('word'), data.get('token')
    if not isinstance(role, str) or role not in ROLES or not isinstance(word, str) or word.strip().casefold() != 'бурмалда':
        return jsonify(ok=False, error='помилка... введи слово «бурмалда»...'), 400
    if not isinstance(token, str):
        return jsonify(ok=False, error='Онови сторінку.'), 403
    try:
        visit = signer.loads(token, max_age=7200)
    except (BadSignature, SignatureExpired):
        return jsonify(ok=False, error='Час порталу минув... онови сторінку.'), 403
    # Global abuse cap for a small private invitation. Use one worker.
    with lock:
        now = time.monotonic()
        recent[:] = [t for t in recent if now - t < 60]
        if len(recent) >= 10:
            return jsonify(ok=False, error='Портал зайнятий... спробуй за хвилину.'), 429
        recent.append(now)
    try:
        send_email(role, visit['id'])
    except (URLError, TimeoutError, OSError, ValueError, RuntimeError):
        app.logger.warning('Email submission unavailable; no secrets logged.')
        return jsonify(ok=False, error='Портал не відповідає... спробуй підтвердити ще раз.'), 503
    return jsonify(ok=True)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '8000')), debug=False)
