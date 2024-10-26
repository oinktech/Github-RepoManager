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

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    # 处理搜索
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 5  # 每页显示的仓库数量
    repos_query = Repository.query.filter(Repository.name.like(f'%{search_query}%'))
    total_repos = repos_query.count()
    repos = repos_query.paginate(page, per_page, False)

    return render_template('dashboard.html', repos=repos.items, search_query=search_query, total_repos=total_repos, per_page=per_page)

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
        # 获取用户信息以提取用户名
        user_info_response = requests.get("https://api.github.com/user", headers={'Authorization': f'token {session["access_token"]}'})
        if user_info_response.status_code == 200:
            user_info = user_info_response.json()
            session['github_username'] = user_info['login']  # 将用户名存入 session
            fetch_repositories()
            flash('登入成功！', 'success')
        else:
            flash('無法獲取用戶信息，請重試。', 'danger')
            return redirect(url_for('login'))
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
        # 从 GitHub 删除仓库
        headers = {'Authorization': f'token {session["access_token"]}'}
        delete_url = f"https://api.github.com/repos/{session['github_username']}/{repo.name}"
        
        response = requests.delete(delete_url, headers=headers)

        if response.status_code == 204:  # 204 No Content
            db.session.delete(repo)
            db.session.commit()
            flash('倉庫刪除成功。', 'success')
        else:
            flash('刪除倉庫失敗，請檢查權限或倉庫名稱。', 'danger')
    else:
        flash('倉庫未找到。', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/rename_repo/<int:repo_id>', methods=['POST'])
def rename_repo(repo_id):
    new_name = request.form.get('new_name')
    repo = Repository.query.get(repo_id)
    if repo and new_name:
        # 使用 GitHub API 重命名仓库
        headers = {'Authorization': f'token {session["access_token"]}'}
        rename_url = f"https://api.github.com/repos/{session['github_username']}/{repo.name}"
        data = {"name": new_name}

        response = requests.patch(rename_url, json=data, headers=headers)

        if response.status_code == 200:  # 200 OK
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
