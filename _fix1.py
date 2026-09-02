import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('2.27.29.113', port=22, username='root', password='0915951a', timeout=10)

# Run fetch and reset with full output
stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && git fetch origin 2>&1; echo 'FETCH_EXIT:' $?", timeout=60)
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && git reset --hard origin/main 2>&1; echo 'RESET_EXIT:' $?", timeout=30)
print(stdout.read().decode())

stdin, stdout, stderr = ssh.exec_command("cd /root/Telegram-Group-Manager && git log --oneline -2", timeout=15)
print("NOW:", stdout.read().decode())

ssh.close()
