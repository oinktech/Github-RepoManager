from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask_sqlalchemy import SQLAlchemy
import requests
import os
from dotenv import load_dotenv
from math import ceil

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///repos.db'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
db = SQLAlchemy(app)

class Repository(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(200), nullable=False)

# 创建数据库表，使用应用上下文
with app.app_context():
    db.create_all()

@app.route('/')
def login():
    github_auth_url = f"https://github.com/login/oauth/authorize?client_id={os.getenv('GITHUB_CLIENT_ID')}&scope=repo,user,notifications,gist,read:org,admin:org,admin:repo_hook,delete_repo,read:repo_hook,write:repo_hook,workflow"
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
        user_info_response = requests.get("https://api.github.com/user", headers={'Authorization': f'token {session["access_token"]}'})
        if user_info_response.status_code == 200:
            user_info = user_info_response.json()
            session['github_username'] = user_info['login']
            fetch_repositories()
            flash('登入成功！', 'success')
        else:
            flash('無法獲取用戶信息，請重試。', 'danger')
            return redirect(url_for('login'))
    else:
        flash('登入失敗，請重試。', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/proxy_repo')
def proxy_repo():
    repo_url = request.args.get('url')
    if not repo_url:
        return "缺少 URL", 400

    response = requests.get(repo_url)
    return (response.content, response.status_code, response.headers.items())

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'access_token' not in session:
        return redirect(url_for('/'))

    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10

    repos_query = Repository.query.filter(Repository.name.like(f'%{search_query}%'))
    repos = repos_query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template('dashboard.html', repos=repos.items, search_query=search_query,
                           total_repos=repos.total, per_page=per_page, ceil=ceil)

def fetch_repositories():
    headers = {'Authorization': f'token {session["access_token"]}'}
    repos = []
    page = 1
    per_page = 100

    while True:
        response = requests.get(f"https://api.github.com/user/repos?per_page={per_page}&page={page}", headers=headers)
        
        if response.status_code != 200:
            flash('無法獲取倉庫，請檢查訪問令牌。', 'danger')
            return
        
        current_page_repos = response.json()
        repos.extend(current_page_repos)
        
        if len(current_page_repos) < per_page:
            break
        
        page += 1

    for repo in repos:
        if not Repository.query.filter_by(name=repo['name']).first():
            new_repo = Repository(name=repo['name'], url=repo['html_url'])
            db.session.add(new_repo)
    db.session.commit()

@app.route('/delete_repo/<int:repo_id>', methods=['POST'])
def delete_repo(repo_id):
    repo = Repository.query.get(repo_id)
    if repo:
        if not check_repo_permission(repo.name):
            flash('刪除失敗，無法訪問該倉庫。', 'danger')
            return redirect(url_for('dashboard'))

        headers = {'Authorization': f'token {session["access_token"]}'}
        delete_url = f"https://api.github.com/repos/{session['github_username']}/{repo.name}"

        response = requests.delete(delete_url, headers=headers)

        if response.status_code == 204:
            db.session.delete(repo)
            db.session.commit()
            flash('倉庫刪除成功。', 'success')
        else:
            error_message = response.json().get('message', '未知錯誤')
            flash(f'刪除倉庫失敗，請檢查權限或倉庫名稱：{error_message}', 'danger')
    else:
        flash('倉庫未找到。', 'danger')
    return redirect(url_for('dashboard'))

def check_repo_permission(repo_name):
    headers = {'Authorization': f'token {session["access_token"]}'}
    check_url = f"https://api.github.com/repos/{session['github_username']}/{repo_name}"
    response = requests.get(check_url, headers=headers)

    if response.status_code == 200:
        repo_data = response.json()
        if repo_data['owner']['login'] == session['github_username']:
            return True
        else:
            flash('您無權刪除該倉庫。', 'danger')
            return False
    else:
        return False

@app.route('/rename_repo/<int:repo_id>', methods=['POST'])
def rename_repo(repo_id):
    new_name = request.form.get('new_name')
    repo = Repository.query.get(repo_id)
    if repo and new_name:
        headers = {'Authorization': f'token {session["access_token"]}'}
        rename_url = f"https://api.github.com/repos/{session['github_username']}/{repo.name}"
        data = {"name": new_name}

        response = requests.patch(rename_url, json=data, headers=headers)

        if response.status_code == 200:
            repo.name = new_name
            db.session.commit()
            flash('倉庫重命名成功。', 'success')
        else:
            flash('重命名失敗，請檢查權限或倉庫名稱。', 'danger')
    else:
        flash('重命名失敗，請確保輸入有效的名稱。', 'danger')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=10000, host='0.0.0.0')
