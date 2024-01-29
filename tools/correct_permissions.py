import os
import stat

path = os.path.join(os.path.expanduser('~'), 'DigitalOcean/src_damonlynch.net')

for dirpath, dirnames, filenames in os.walk(path):
    for name in dirnames:
        path = os.path.join(dirpath, name)
        if stat.filemode(os.stat(path).st_mode) != 'drwxr-xr-x':
            print(path)
            os.chmod(path, 0o755)
    for name in filenames:
        full_file_name = os.path.join(dirpath, name)
        if stat.filemode(os.stat(full_file_name).st_mode) != '-rw-r--r--':
            print(full_file_name)
            os.chmod(full_file_name, 0o644)
