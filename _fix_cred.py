import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.27.29.113', port=22, username='root', password='0915951a', timeout=10)

# Configure credential helper globally
stdin, stdout, stderr = ssh.exec_command("git config --global credential.helper store", timeout=10)
print("CONFIG:", stdout.read().decode().strip() or "OK")

# Test fetch now
stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && GIT_TERMINAL_PROMPT=0 git ls-remote origin HEAD 2>&1 | head -2", timeout=30)
print("LS_REMOTE:", stdout.read().decode().strip())

# Full update
stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && git fetch origin 2>&1 && git reset --hard origin/main 2>&1 && git log --oneline -2", timeout=60)
print("UPDATE:")
print(stdout.read().decode())

ssh.close()
