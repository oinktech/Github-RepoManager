from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_sqlalchemy import SQLAlchemy
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///repos.db'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
db = SQLAlchemy(app)

class Repository(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(200), nullable=False)

db.create_all()

@app.route('/dashboard')
def dashboard():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    repos = Repository.query.all()
    return render_template('dashboard.html', repos=repos)

@app.route('/')
def login():
    github_auth_url = f"https://github.com/login/oauth/authorize?client_id={os.getenv('GITHUB_CLIENT_ID')}&scope=repo"
    return redirect(github_auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_url = "https://github.com/login/oauth/access_token"
    payload = {
        'client_id': os.getenv('GITHUB_CLIENT_ID'),
        'client_secret': os.getenv('GITHUB_CLIENT_SECRET'),
        'code': code
    }
    headers = {'Accept': 'application/json'}
    response = requests.post(token_url, json=payload, headers=headers)
    
    if response.status_code != 200:
        flash('獲取訪問令牌失敗，請重試。', 'danger')
        return redirect(url_for('login'))
    
    data = response.json()
    session['access_token'] = data.get('access_token')
    if session['access_token']:
        fetch_repositories()
        flash('登入成功！', 'success')
    else:
        flash('登入失敗，請重試。', 'danger')
    return redirect(url_for('dashboard'))

def fetch_repositories():
    headers = {'Authorization': f'token {session["access_token"]}'}
    response = requests.get("https://api.github.com/user/repos", headers=headers)
    
    if response.status_code != 200:
        flash('無法獲取倉庫，請檢查訪問令牌。', 'danger')
        return
    
    repos = response.json()
    for repo in repos:
        if not Repository.query.filter_by(name=repo['name']).first():
            new_repo = Repository(name=repo['name'], url=repo['html_url'])
            db.session.add(new_repo)
    db.session.commit()

@app.route('/delete_repo/<int:repo_id>', methods=['POST'])
def delete_repo(repo_id):
    repo = Repository.query.get(repo_id)
    if repo:
        db.session.delete(repo)
        db.session.commit()
        flash('倉庫刪除成功。', 'success')
    else:
        flash('倉庫未找到。', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/rename_repo/<int:repo_id>', methods=['POST'])
def rename_repo(repo_id):
    new_name = request.form.get('new_name')
    repo = Repository.query.get(repo_id)
    if repo and new_name:
        repo.name = new_name
        db.session.commit()
        flash('倉庫重命名成功。', 'success')
    else:
        flash('重命名失敗，請確保輸入有效的名稱。', 'danger')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=10000, host='0.0.0.0')
