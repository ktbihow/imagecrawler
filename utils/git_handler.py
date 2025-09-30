# utils/git_handler.py
import os
import subprocess
import requests
from datetime import datetime
from dotenv import load_dotenv
from .constants import BASE_DIR, ENV_FILE

load_dotenv(dotenv_path=ENV_FILE)

def git_push_changes():
    if os.getenv('GITHUB_ACTIONS') == 'true':
        print("Đang chạy trên GitHub Actions, bỏ qua git push.")
        return

    print("Đang chạy trên máy tính cục bộ, tiến hành push thay đổi lên GitHub...")
    try:
        os.chdir(BASE_DIR)
        subprocess.run(['git', 'add', '.'], check=True)
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not status_result.stdout.strip():
            print("Không có thay đổi nào để commit.")
            return
        branch_result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True, check=True)
        current_branch = branch_result.stdout.strip()
        commit_message = f"Auto-update crawled data at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(['git', 'commit', '--amend', '-m', commit_message], check=True)
        print(f"✅ Đã amend commit cuối cùng với message: '{commit_message}'")
        subprocess.run(['git', 'push', '--force', 'origin', current_branch], check=True)
        print("✅ Đã force push thành công các thay đổi lên GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Đã xảy ra lỗi khi thực thi lệnh Git:")
        print(f"   Lệnh: {' '.join(e.cmd)}")
        print(f"   Exit code: {e.returncode}")
        print(f"   Stderr: {e.stderr.decode('utf-8', errors='ignore').strip()}")
        print(f"   Stdout: {e.stdout.decode('utf-8', errors='ignore').strip()}")
    except Exception as e:
        print(f"❌ Đã xảy ra lỗi không xác định khi push: {e}")

def trigger_workflow_dispatch():
    pat = os.getenv('KTBHUB_PAT')
    if not pat: return
    print("🚀 Kích hoạt workflow 'new_image_available' trên repo ktbteam/ktb-image...")
    try:
        response = requests.post(
            "https://api.github.com/repos/ktbteam/ktb-image/dispatches",
            headers={"Accept": "application/vnd.github.v3+json", "Authorization": f"Bearer {pat}"},
            json={"event_type": "new_image_available"},
            timeout=15
        )
        if response.status_code == 204:
            print("✅ Đã gửi yêu cầu kích hoạt workflow thành công.")
        else:
            print(f"❌ Lỗi khi kích hoạt workflow: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối đến GitHub API: {e}")