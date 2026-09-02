import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.27.29.113', port=22, username='root', password='0915951a', timeout=10)

# Check credential helper is configured and test the credentials file format (mask token)
stdin, stdout, stderr = ssh.exec_command("git config --global credential.helper", timeout=10)
print("CRED_HELPER:", repr(stdout.read().decode().strip()))

stdin, stdout, stderr = ssh.exec_command("cat /root/.git-credentials | sed 's/[a-f0-9]\\{20,\\}/***TOKEN***/g'", timeout=10)
print("CRED_FILE(masked):", stdout.read().decode().strip())

# Test fetch with verbose to see if credentials are used
stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && GIT_TERMINAL_PROMPT=0 git ls-remote origin HEAD 2>&1 | head -3", timeout=30)
print("LS_REMOTE:", stdout.read().decode().strip())

ssh.close()
